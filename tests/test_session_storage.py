"""Offline regression coverage for session isolation, concurrency and maintenance."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from langgraph.graph import END, StateGraph

from utils.artifacts import save_artifacts
from utils.memory import _sqlite_checkpointer, get_checkpointer, close_checkpointer
from utils.session_runtime import SessionGraph, checkpoint_id
from utils.sessions import list_sessions, rename_session, export_session, delete_session
from utils.state import ResearchState
from utils.storage import output_dir, session_lock, StaleSessionError


class SessionStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"RESEARCH_AGENT_CACHE_DIR": str(self.root / "cache"),
                                     "RESEARCH_AGENT_AUTOSAVE_DIR": str(self.root / "outputs")})
        env.start()
        self.addCleanup(env.stop)
        self.saver = _sqlite_checkpointer(f"sqlite:///{self.root / 'checkpoints.sqlite'}")
        self.addCleanup(self.saver.conn.close)

    def graph(self):
        builder = StateGraph(ResearchState)
        builder.add_node("question", lambda state: {"messages": [{"role": "assistant", "content": "question"}]})
        builder.add_node("human", lambda state: {})
        builder.add_node("finish", lambda state: {"core_modification": state["human_feedback"]})
        builder.set_entry_point("question")
        builder.add_edge("question", "human")
        builder.add_edge("human", "finish")
        builder.add_edge("finish", END)
        return SessionGraph(builder.compile(checkpointer=self.saver, interrupt_before=["human"]))

    @staticmethod
    def config(sid="one"):
        return {"configurable": {"thread_id": sid}}

    def test_outputs_are_isolated_atomic_and_retryable(self):
        first = {"session_id": "one", "research_proposal": "first", "core_modification": "old", "metadata": {"integration_prompt": "instructions"}}
        second = {"session_id": "two", "research_proposal": "second"}
        self.assertFalse(save_artifacts(first)["failed"])
        save_artifacts(second)
        self.assertIn("first", (output_dir("one") / "research_proposal.md").read_text())
        self.assertIn("second", (output_dir("two") / "research_proposal.md").read_text())
        from utils.storage import atomic_write_text
        def failing(path, text):
            if path.name == "core_algorithm.py":
                raise PermissionError("disk unavailable")
            atomic_write_text(path, text)
        with patch("utils.artifacts.atomic_write_text", side_effect=failing):
            report = save_artifacts({**first, "core_modification": "new"})
        self.assertEqual(len(report["failed"]), 1)
        self.assertEqual(len(report["saved"]), 3)
        self.assertIn("old", (output_dir("one") / "core_algorithm.py").read_text())
        self.assertFalse(save_artifacts({**first, "core_modification": "new"})["failed"])
        self.assertIn("new", (output_dir("one") / "core_algorithm.py").read_text())
        self.assertNotIn("..", output_dir("../../outside").name)

    def test_process_lock_rejects_same_session_but_allows_other_sessions(self):
        code = ("from utils.storage import session_lock, SessionBusyError\n"
                "import sys\ntry:\n with session_lock(sys.argv[1]): print('acquired')\n"
                "except SessionBusyError:\n sys.exit(7)\n")
        with session_lock("one"):
            same = subprocess.run([sys.executable, "-c", code, "one"], capture_output=True, timeout=10)
            other = subprocess.run([sys.executable, "-c", code, "two"], capture_output=True, timeout=10)
            with session_lock("one"):
                pass  # Owning-thread reentry remains valid.
        self.assertEqual(same.returncode, 7, same.stderr)
        self.assertEqual(other.returncode, 0, other.stderr)
        with session_lock("one"):
            pass

    def test_stale_submission_never_overwrites_newer_answer(self):
        graph, config = self.graph(), self.config()
        graph.invoke({"topic": "research"}, config)
        token = checkpoint_id(graph.get_state(config))
        list(graph.submit(config, {"human_feedback": "new answer"}, token))
        with self.assertRaises(StaleSessionError):
            list(graph.submit(config, {"human_feedback": "stale answer"}, token))
        self.assertEqual(graph.get_state(config).values["core_modification"], "new answer")

    def test_legacy_migration_preserves_pending_gate_and_messages(self):
        graph, config = self.graph(), self.config()
        graph._graph.invoke({"topic": "legacy", "selected_direction": {"name": "chosen"}}, config)
        old = graph._graph.get_state(config)
        migrated = graph.get_state(config)
        self.assertEqual(migrated.next, old.next)
        self.assertEqual(migrated.values["schema_version"], 1)
        self.assertEqual(migrated.values["selected_direction"], {"name": "chosen"})
        self.assertEqual(len(migrated.values["messages"]), len(old.values["messages"]))
        token = checkpoint_id(migrated)
        list(graph.submit(config, {"human_feedback": "resume"}, token))
        self.assertEqual(graph.get_state(config).values["core_modification"], "resume")

    def test_loading_legacy_failed_task_keeps_its_cached_response_and_retry_id(self):
        from agents.orchestrator import _tracked_node
        from utils.llm_client import _RetryingLLM
        from langchain_core.messages import AIMessage
        from types import SimpleNamespace
        model = SimpleNamespace(invoke=Mock(return_value=AIMessage(content="cached response")))
        llm = _RetryingLLM(model, "fake", 0, "model")
        attempts = []
        def work(state):
            attempts.append(1)
            response = llm.invoke("question")
            if len(attempts) == 1:
                raise RuntimeError("interrupted after response")
            return {"core_modification": response.content}
        builder = StateGraph(ResearchState)
        builder.add_node("start", lambda state: {"topic": "old session"})
        builder.add_node("work", _tracked_node("work", work))
        builder.set_entry_point("start")
        builder.add_edge("start", "work")
        builder.add_edge("work", END)
        graph = SessionGraph(builder.compile(checkpointer=self.saver))
        config = self.config()
        with self.assertRaisesRegex(RuntimeError, "interrupted after response"):
            graph._graph.invoke({"topic": "legacy"}, config)
        before = graph._graph.get_state(config)
        viewed = graph.get_state(config)
        self.assertEqual(checkpoint_id(before), checkpoint_id(viewed))
        self.assertEqual(viewed.next, ("work",))
        result = graph.invoke(None, config)
        self.assertEqual(result["core_modification"], "cached response")
        self.assertEqual(result["last_node_attempt"], 2)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(model.invoke.call_count, 1)

    def test_future_state_version_is_rejected(self):
        graph, config = self.graph(), self.config()
        graph._graph.invoke({"topic": "future", "schema_version": 999}, config)
        with self.assertRaisesRegex(ValueError, "newer than supported"):
            graph.get_state(config)
        with self.assertRaises(ValueError):
            graph.update_state(config, {"topic": "overwrite"})

    def test_history_rename_export_and_recoverable_delete(self):
        graph = self.graph()
        for sid in ("one", "two"):
            graph.invoke({"topic": "topic " + sid, "metadata": {"integration_prompt": "retained"}}, self.config(sid))
        rename_session(graph, "one", "My study")
        self.assertEqual(len(list_sessions(graph)), 2)
        self.assertEqual(next(s["title"] for s in list_sessions(graph) if s["session_id"] == "one"), "My study")
        bundle = export_session(graph, "one")
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            state = json.loads(archive.read("session.json"))
            self.assertEqual(state["next"], ["human"])
            self.assertEqual(state["state"]["metadata"]["integration_prompt"], "retained")
        save_artifacts(graph.get_state(self.config()).values)
        recovery = delete_session(graph, "one")
        self.assertTrue((recovery / "session.zip").exists())
        self.assertTrue((recovery / "checkpoints.bin").exists())
        self.assertTrue((recovery / "outputs" / "research_state.json").exists())
        self.assertFalse(output_dir("one").exists())
        self.assertFalse(graph.get_state(self.config()).values)
        self.assertTrue(graph.get_state(self.config("two")).values)

    def test_cache_cleanup_preserves_failed_tasks(self):
        from utils.operations import task_attempt, save_result, load_result, clean_cache, delete_session_cache
        def config(sid):
            return {"configurable": {"thread_id": sid}, "metadata": {"langgraph_checkpoint_ns": "work:task"}}
        with patch("utils.operations.time.time", return_value=0):
            with task_attempt("work", config("one")):
                save_result("done", "response")
            with self.assertRaises(RuntimeError), task_attempt("work", config("two")):
                save_result("retry", "response")
                raise RuntimeError("crashed")
            save_result("search", [])
        with patch("utils.operations.time.time", return_value=40 * 86400):
            self.assertEqual(clean_cache(30), 3)
        self.assertFalse(load_result("done")[0])
        self.assertFalse(load_result("search")[0])
        self.assertTrue(load_result("retry")[0])
        delete_session_cache("two")
        self.assertFalse(load_result("retry")[0])

    def test_cache_cleanup_skips_locked_session(self):
        import threading
        from utils.operations import task_attempt, save_result, load_result, clean_cache
        config = {"configurable": {"thread_id": "one"}, "metadata": {"langgraph_checkpoint_ns": "task:one"}}
        with patch("utils.operations.time.time", return_value=0), task_attempt("work", config):
            save_result("busy", "response")
        acquired, release = threading.Event(), threading.Event()
        def holder():
            with session_lock("one"):
                acquired.set()
                release.wait(5)
        worker = threading.Thread(target=holder)
        worker.start()
        try:
            self.assertTrue(acquired.wait(5))
            with patch("utils.operations.time.time", return_value=40 * 86400):
                self.assertEqual(clean_cache(30), 0)
            self.assertTrue(load_result("busy")[0])
        finally:
            release.set()
            worker.join(5)

    def test_management_cli_needs_no_model_keys(self):
        graph = self.graph()
        graph.invoke({"topic": "offline study"}, self.config())
        environment = {key: value for key, value in os.environ.items() if not key.endswith("API_KEY")}
        environment["DATABASE_URL"] = f"sqlite:///{self.root / 'checkpoints.sqlite'}"
        script = str(Path(__file__).resolve().parents[1] / "main.py")
        for arguments in (["--list-sessions"], ["--rename", "one", "Offline name"],
                          ["--export", "one", "--export-path", str(self.root / "export.zip")],
                          ["--retry-save", "one"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, script, *arguments], cwd=self.root,
                                        env=environment, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.root / "export.zip").exists())
        self.assertTrue((output_dir("one") / "research_state.json").exists())
        self.assertEqual(list_sessions(graph)[0]["title"], "Offline name")

    def test_postgres_context_is_entered_setup_and_closed_once(self):
        from types import SimpleNamespace
        saver = SimpleNamespace(setup=Mock())
        manager = Mock()
        manager.__enter__ = Mock(return_value=saver)
        manager.__exit__ = Mock(return_value=False)
        module = SimpleNamespace(PostgresSaver=SimpleNamespace(from_conn_string=Mock(return_value=manager)))
        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": module}), patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}), patch("utils.memory.atexit.register"):
            self.assertIs(get_checkpointer(), saver)
            saver.setup.assert_called_once()
            close_checkpointer(saver)
            close_checkpointer(saver)
            manager.__enter__.assert_called_once()
            manager.__exit__.assert_called_once()

    def test_postgres_setup_failure_closes_context(self):
        from types import SimpleNamespace
        saver = SimpleNamespace(setup=Mock(side_effect=RuntimeError("setup failed")))
        manager = Mock()
        manager.__enter__ = Mock(return_value=saver)
        manager.__exit__ = Mock(return_value=False)
        module = SimpleNamespace(PostgresSaver=SimpleNamespace(from_conn_string=Mock(return_value=manager)))
        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": module}), patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}):
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                get_checkpointer()
        manager.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()

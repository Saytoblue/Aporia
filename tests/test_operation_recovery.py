import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph
from pypdf import PdfWriter
import requests

from agents.orchestrator import _tracked_node
from main import _atomic_write_text
from tools.literature_tools import download_pdf, search_arxiv_recent, search_semantic_scholar
from utils.llm_client import _RetryingLLM
from utils.memory import _sqlite_checkpointer
from utils.state import ResearchState


class OperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {
            "RESEARCH_AGENT_CACHE_DIR": self.tmp.name,
            "RESEARCH_AGENT_SEARCH_CACHE_TTL": "60",
            "RESEARCH_AGENT_LLM_RETRY_MAX": "0",
        })
        env.start()
        self.addCleanup(env.stop)

    def test_resumed_task_reuses_model_results_after_node_failure(self):
        provider_calls, upstream_calls, node_calls = [], [], []

        class Model:
            def invoke(self, messages):
                provider_calls.append(messages)
                return AIMessage(content=f"answer-{len(provider_calls)}")

        def upstream(state):
            upstream_calls.append(1)
            return {"topic": "persisted"}

        def work(state):
            node_calls.append(1)
            llm = _RetryingLLM(Model(), "fake", 0.5, "test-model")
            # Identical requests intentionally made twice must remain distinct.
            first = llm.invoke([HumanMessage(content="question")])
            second = llm.invoke([HumanMessage(content="question")])
            if len(node_calls) == 1:
                raise RuntimeError("crash after model response, before node checkpoint")
            return {"core_modification": first.content + "/" + second.content}

        def build(saver):
            builder = StateGraph(ResearchState)
            builder.add_node("upstream", _tracked_node("upstream", upstream))
            builder.add_node("work", _tracked_node("work", work))
            builder.set_entry_point("upstream")
            builder.add_edge("upstream", "work")
            builder.add_edge("work", END)
            return builder.compile(checkpointer=saver)

        db_url = f"sqlite:///{self.tmp.name}/checkpoints.sqlite"
        config = {"configurable": {"thread_id": "crash-test"}}
        saver = _sqlite_checkpointer(db_url)
        try:
            graph = build(saver)
            with self.assertRaisesRegex(RuntimeError, "crash after"):
                graph.invoke({"topic": "initial"}, config)
            self.assertEqual(graph.get_state(config).next, ("work",))
        finally:
            saver.conn.close()

        # Recreate both graph and checkpoint connection as after an app restart.
        saver = _sqlite_checkpointer(db_url)
        try:
            graph = build(saver)
            result = graph.invoke(None, config)
            self.assertEqual(result["core_modification"], "answer-1/answer-2")
            self.assertEqual(len(provider_calls), 2)
            self.assertEqual(len(upstream_calls), 1)
            self.assertEqual(result["last_node_status"], "replayed")
            self.assertEqual(result["last_node_attempt"], 2)
            self.assertEqual(result["replayed_nodes"], ["work"])

            # A new run in the same session must get fresh model responses.
            fresh = graph.invoke({"topic": "new run"}, config)
            self.assertEqual(fresh["core_modification"], "answer-3/answer-4")
            self.assertEqual(fresh["last_node_attempt"], 1)
            graph.invoke({"topic": "other session"}, {"configurable": {"thread_id": "other"}})
            self.assertEqual(len(provider_calls), 6)
        finally:
            saver.conn.close()

    def test_failed_model_request_is_not_cached(self):
        from utils.operations import task_attempt

        calls = []

        class Model:
            def invoke(self, message):
                calls.append(message)
                if len(calls) == 1:
                    raise ValueError("provider rejected request")
                return AIMessage(content="success")

        config = {"configurable": {"thread_id": "failure"},
                  "metadata": {"langgraph_checkpoint_ns": "work:stable-task"}}
        llm = _RetryingLLM(Model(), "fake", 0, "test")
        with self.assertRaises(ValueError), task_attempt("work", config):
            llm.invoke("input")
        with task_attempt("work", config) as attempt:
            self.assertEqual(attempt, 2)
            self.assertEqual(llm.invoke("input").content, "success")
        self.assertEqual(len(calls), 2)

    def test_changed_model_or_input_does_not_reuse_old_response(self):
        from utils.operations import task_attempt

        calls = []

        class Model:
            model_name = "model-a"

            def invoke(self, message):
                calls.append((self.model_name, message))
                return AIMessage(content=f"response-{len(calls)}")

        model = Model()
        llm = _RetryingLLM(model, "fake", 0, None)
        config = {"configurable": {"thread_id": "settings"},
                  "metadata": {"langgraph_checkpoint_ns": "work:stable-task"}}
        with task_attempt("work", config):
            self.assertEqual(llm.invoke("input").content, "response-1")
        with task_attempt("work", config):
            self.assertEqual(llm.invoke("input").content, "response-1")
        model.model_name = "model-b"
        with task_attempt("work", config):
            self.assertEqual(llm.invoke("input").content, "response-2")
        with task_attempt("work", config):
            self.assertEqual(llm.invoke("changed input").content, "response-3")
        self.assertEqual(len(calls), 3)

    def test_search_cache_respects_ttl_and_request_parameters(self):
        response = Mock()
        response.json.return_value = {"data": [{"paperId": "p1", "title": "Paper", "citationCount": 5}]}
        with patch("requests.get", return_value=response) as get, patch("utils.operations.time.time", return_value=100) as clock:
            self.assertEqual(len(search_semantic_scholar("topic")), 1)
            clock.return_value = 125
            self.assertEqual(len(search_semantic_scholar("topic")), 1)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(search_semantic_scholar("topic", min_citation=10), [])
            self.assertEqual(get.call_count, 2)
            clock.return_value = 161
            search_semantic_scholar("topic")
            self.assertEqual(get.call_count, 3)

    def test_search_failure_is_retried_but_successful_empty_result_is_cached(self):
        response = Mock(content=b'<feed xmlns="http://www.w3.org/2005/Atom"/>')
        with patch("requests.get", side_effect=[requests.ConnectionError("offline"), response]) as get:
            self.assertEqual(search_arxiv_recent("topic"), [])
            self.assertEqual(search_arxiv_recent("topic"), [])
            self.assertEqual(search_arxiv_recent("topic"), [])
            self.assertEqual(get.call_count, 2)

    def test_pdf_cache_validates_content_and_recovers_corruption(self):
        pdf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf)
        good = Mock(status_code=200, content=pdf.getvalue())
        bad = Mock(status_code=200, content=b"<html>download failed</html>")
        root = Path(self.tmp.name) / "pdfs"
        with patch("requests.get", side_effect=[bad, good, good]) as get:
            self.assertIsNone(download_pdf("https://example.test/p.pdf", root, "../../unsafe/id"))
            self.assertEqual(list(root.iterdir()), [])
            path = download_pdf("https://example.test/p.pdf", root, "../../unsafe/id")
            self.assertEqual(path.parent, root)
            self.assertEqual(download_pdf("https://example.test/p.pdf", root, "../../unsafe/id"), path)
            self.assertEqual(get.call_count, 2)
            path.write_bytes(b"%PDF-truncated")
            self.assertEqual(download_pdf("https://example.test/p.pdf", root, "../../unsafe/id"), path)
            self.assertEqual(path.read_bytes(), good.content)
            self.assertEqual(get.call_count, 3)
            self.assertEqual(list(root.glob(".*")), [])

    def test_failed_atomic_replace_preserves_previous_output(self):
        path = Path(self.tmp.name) / "output.txt"
        _atomic_write_text(path, "previous")
        with patch("main.os.replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                _atomic_write_text(path, "new")
        self.assertEqual(path.read_text(), "previous")
        self.assertEqual(list(path.parent.glob(".*")), [])


if __name__ == "__main__":
    unittest.main()

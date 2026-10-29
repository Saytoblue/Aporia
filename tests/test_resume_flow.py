import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents import orchestrator
from main import _pending_interaction, _stream_until_pause
from main import _atomic_write_text, _write_if_changed
from utils.memory import _sqlite_checkpointer
from utils.state import ResearchState
from utils.web_session import build_web_checkpoint_graph, load_web_state, save_web_state


class ResumeFlowTests(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.TemporaryDirectory()
        self.addCleanup(self.cache.cleanup)
        cache_env = patch.dict(os.environ, {"RESEARCH_AGENT_CACHE_DIR": self.cache.name,
                                          "RESEARCH_AGENT_AUTOSAVE_DIR": str(Path(self.cache.name) / "outputs")})
        cache_env.start()
        self.addCleanup(cache_env.stop)
        try:
            import streamlit as st
        except ImportError:
            pass
        else:
            st.cache_resource.clear()
            self.addCleanup(st.cache_resource.clear)

    def test_normal_dialogue_loop_is_not_replay(self):
        calls = []

        def tracked_node(state):
            calls.append(1)
            return {**state, "topic": "tracked"}

        with patch.object(orchestrator, "elicit_node", tracked_node):
            graph = orchestrator.build_graph(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "metadata-test"}}
            list(graph.stream({"topic": "initial", "dialogue_turns": 2}, config, stream_mode="values"))
            # A new human reply creates a legitimate new task, not a retry.
            graph.update_state(config, {"human_feedback": "more context"})
            list(graph.stream(None, config, stream_mode="values"))
            state = graph.get_state(config).values
            self.assertGreaterEqual(state["node_runs"]["elicit"], 2)
            self.assertNotIn("elicit", state["replayed_nodes"])
            self.assertEqual(state["last_node_attempt"], 1)

    def test_output_writes_are_atomic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            _write_if_changed(str(path), '{"ok": true}\n')
            first_mtime = path.stat().st_mtime_ns
            _write_if_changed(str(path), '{"ok": true}\n')
            self.assertEqual(path.read_text(encoding="utf-8"), '{"ok": true}\n')
            self.assertEqual(path.stat().st_mtime_ns, first_mtime)
            _atomic_write_text(path, '{"ok": false}\n')
            self.assertEqual(path.read_text(encoding="utf-8"), '{"ok": false}\n')
            self.assertEqual(list(Path(tmp).glob(".*")), [])

    def test_pending_interaction_matches_each_checkpoint(self):
        self.assertEqual(
            _pending_interaction({}, ("human_elicit_continue",)),
            "elicit_continue",
        )
        self.assertEqual(
            _pending_interaction({"candidate_directions": [{"name": "d1"}]}, ("human_direction_select",)),
            "direction_select",
        )
        self.assertEqual(
            _pending_interaction({"research_proposal": "proposal"}, ("human_proposal_review",)),
            "proposal_review",
        )
        self.assertEqual(
            _pending_interaction({"core_modification": "def solve(): pass"}, ()),
            "done",
        )

    def test_stream_resumes_after_human_checkpoint(self):
        def produce_question(state: ResearchState) -> ResearchState:
            return {**state, "messages": [{"role": "assistant", "content": "question"}]}

        def human_gate(state: ResearchState) -> ResearchState:
            return state

        def finish(state: ResearchState) -> ResearchState:
            return {**state, "core_modification": "done"}

        graph_builder = StateGraph(ResearchState)
        graph_builder.add_node("produce_question", produce_question)
        graph_builder.add_node("human_gate", human_gate)
        graph_builder.add_node("finish", finish)
        graph_builder.set_entry_point("produce_question")
        graph_builder.add_edge("produce_question", "human_gate")
        graph_builder.add_edge("human_gate", "finish")
        graph_builder.add_edge("finish", END)
        graph = graph_builder.compile(
            checkpointer=MemorySaver(),
            interrupt_before=["human_gate"],
        )
        config = {"configurable": {"thread_id": "resume-test"}}

        for _ in graph.stream({}, config, stream_mode="values"):
            pass
        self.assertEqual(graph.get_state(config).next, ("human_gate",))

        graph.update_state(config, {"human_feedback": "continue", "ui_phase": "graph_elicit"})
        self.assertEqual(graph.get_state(config).next, ("human_gate",))
        with patch("main._save_outputs"), patch("main._autosave_from_graph"):
            _stream_until_pause(graph, config, "question")
        snapshot = graph.get_state(config)
        self.assertEqual(snapshot.values["core_modification"], "done")
        self.assertEqual(snapshot.next, ())

    def test_sqlite_checkpoint_survives_new_saver(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "checkpoints.sqlite"
            first = _sqlite_checkpointer(str(db_path))
            graph_builder = StateGraph(ResearchState)
            graph_builder.add_node("save", lambda state: {**state, "topic": "persisted"})
            graph_builder.set_entry_point("save")
            graph_builder.add_edge("save", END)
            graph = graph_builder.compile(checkpointer=first)
            config = {"configurable": {"thread_id": "sqlite-test"}}
            for _ in graph.stream({}, config, stream_mode="values"):
                pass

            second = _sqlite_checkpointer(str(db_path))
            restored_graph = graph_builder.compile(checkpointer=second)
            restored = restored_graph.get_state(config)
            self.assertEqual(restored.values["topic"], "persisted")

    def test_resume_session_rejects_unknown_id(self):
        class EmptyGraph:
            def get_state(self, config):
                return type("Snapshot", (), {"values": {}})()

        original = orchestrator.build_graph
        try:
            orchestrator.build_graph = lambda: EmptyGraph()
            with self.assertRaises(ValueError):
                orchestrator.resume_session("missing-session")
        finally:
            orchestrator.build_graph = original

    def test_direction_selection_does_not_approve_proposal(self):
        self.assertEqual(
            orchestrator.route_after_proposal({
                "research_proposal": "draft",
                "human_feedback": "",
            }),
            "human_proposal_review",
        )
        self.assertEqual(
            orchestrator.route_after_proposal({
                "research_proposal": "draft",
                "human_feedback": "approved",
            }),
            "generate_core_code",
        )

    def test_proposal_review_routes_approval_or_revision(self):
        self.assertEqual(
            orchestrator.route_after_proposal_review({"human_feedback": "approved"}),
            "paper_expand_post_proposal",
        )
        self.assertEqual(
            orchestrator.route_after_proposal_review({"human_feedback": "add an ablation"}),
            "proposal_revision",
        )

    def test_full_orchestrator_flow_with_proposal_revision(self):
        """Exercise the real graph topology without making network LLM calls."""
        def fake_elicit(state):
            turns = state.get("dialogue_turns", 0)
            if turns < 2:
                return {
                    **state,
                    "dialogue_turns": turns + 1,
                    "messages": [{"role": "assistant", "content": "question"}],
                }
            return {
                **state,
                "dialogue_turns": turns + 1,
                "friction_points": ["baseline misses the key constraint"],
                "human_feedback": "",
                "messages": [{"role": "assistant", "content": "profile ready"}],
            }

        def fake_idea(state):
            return {
                **state,
                "candidate_directions": [{
                    "name": "direction A",
                    "broken_assumption": "assumption A",
                    "one_line": "test direction",
                }],
            }

        def fake_paper_expand(state):
            return state

        def fake_refine(state):
            return {**state, "selected_idea": "refined idea"}

        def fake_assumption(state):
            return {**state, "assumption_analysis": "analysis"}

        def fake_reframe(state):
            return {**state, "reframed_problem": "reframed"}

        def fake_story(state):
            return {**state, "story_arc": "story"}

        def fake_necessity(state):
            return {**state, "method_necessity_check": "necessary"}

        def fake_proposal(state):
            return {**state, "research_proposal": "initial proposal"}

        def fake_revision(state):
            return {
                **state,
                "research_proposal": "revised proposal: " + state.get("human_feedback", ""),
                "proposal_revision_count": state.get("proposal_revision_count", 0) + 1,
                "human_feedback": "",
            }

        def fake_code(state):
            return {**state, "core_modification": "def solve(): pass"}

        replacements = {
            "elicit_node": fake_elicit,
            "idea_node": fake_idea,
            "paper_expand_node": fake_paper_expand,
            "idea_refine_node": fake_refine,
            "assumption_breaking_node": fake_assumption,
            "problem_reframing_node": fake_reframe,
            "story_arc_node": fake_story,
            "necessity_check_node": fake_necessity,
            "proposal_node": fake_proposal,
            "proposal_revision_node": fake_revision,
            "generate_core_code_node": fake_code,
        }

        with patch.multiple(orchestrator, **replacements):
            graph = orchestrator.build_graph(checkpointer=MemorySaver())
            config = {"configurable": {"thread_id": "e2e-test"}}
            initial = {
                "topic": "test topic",
                "dialogue_turns": 0,
                "workflow": "orchestrator",
            }

            list(graph.stream(initial, config, stream_mode="values"))
            self.assertEqual(graph.get_state(config).next, ("human_elicit_continue",))

            graph.update_state(config, {
                "human_feedback": "concrete friction",
                "messages": [{"role": "user", "content": "concrete friction"}],
            })
            list(graph.stream(None, config, stream_mode="values"))
            self.assertEqual(graph.get_state(config).next, ("human_elicit_continue",))

            graph.update_state(config, {
                "human_feedback": "impact is measurable in the target benchmark",
                "messages": [{
                    "role": "user",
                    "content": "impact is measurable in the target benchmark",
                }],
            })
            list(graph.stream(None, config, stream_mode="values"))
            self.assertEqual(graph.get_state(config).next, ("human_direction_select",))

            graph.update_state(config, {
                "selected_direction": {"name": "direction A"},
                "human_feedback": "",
            })
            list(graph.stream(None, config, stream_mode="values"))
            self.assertEqual(graph.get_state(config).next, ("human_proposal_review",))

            graph.update_state(config, {"human_feedback": "add an ablation"})
            list(graph.stream(None, config, stream_mode="values"))
            revised = graph.get_state(config)
            self.assertEqual(revised.next, ("human_proposal_review",))
            self.assertEqual(revised.values["proposal_revision_count"], 1)
            self.assertIn("add an ablation", revised.values["research_proposal"])

            graph.update_state(config, {"human_feedback": "approved"})
            list(graph.stream(None, config, stream_mode="values"))
            completed = graph.get_state(config)
            self.assertEqual(completed.next, ())
            self.assertEqual(completed.values["core_modification"], "def solve(): pass")

    def test_web_state_round_trips_with_ui_phase(self):
        graph = build_web_checkpoint_graph(checkpointer=MemorySaver())
        save_web_state(
            graph,
            "web-session-test",
            {"topic": "persisted topic", "selected_direction": {"name": "direction"}},
            "idea_select",
        )

        state, phase = load_web_state(graph, "web-session-test")
        self.assertEqual(state["topic"], "persisted topic")
        self.assertEqual(state["selected_direction"]["name"], "direction")
        self.assertEqual(phase, "idea_select")

    def test_web_app_reports_unknown_session_without_exception(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Streamlit testing API is unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            old_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp) / 'web.sqlite'}"
            try:
                app = AppTest.from_file("app.py").run(timeout=30)
                app.text_input(key="resume_session_input").set_value("missing-session")
                next(button for button in app.button if button.label == "Load session").click().run(timeout=30)
                self.assertFalse(app.exception)
                self.assertTrue(any("missing-session" in warning.value for warning in app.warning))
                self.assertEqual(app.session_state["phase"], "input")
            finally:
                if old_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = old_url

    def test_web_app_loads_persisted_session(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Streamlit testing API is unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            old_url = os.environ.get("DATABASE_URL")
            db_url = f"sqlite:///{Path(tmp) / 'web.sqlite'}"
            os.environ["DATABASE_URL"] = db_url
            try:
                persisted = build_web_checkpoint_graph()
                save_web_state(
                    persisted,
                    "web-ui-session",
                    {"topic": "persisted web topic"},
                    "input",
                )
                app = AppTest.from_file("app.py").run(timeout=30)
                app.text_input(key="resume_session_input").set_value("web-ui-session")
                next(button for button in app.button if button.label == "Load session").click().run(timeout=30)
                self.assertFalse(app.exception)
                self.assertIn("web-ui-session", app.code[0].value)
                self.assertEqual(app.session_state["session_id"], "web-ui-session")
                self.assertEqual(app.session_state["phase"], "input")
            finally:
                if old_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = old_url


if __name__ == "__main__":
    unittest.main()

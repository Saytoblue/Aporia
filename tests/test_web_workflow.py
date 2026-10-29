"""Exercise persisted shared-graph gates through actual Streamlit widgets."""
from collections import Counter
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agents import orchestrator
from utils.memory import _sqlite_checkpointer


class WebStartUXTests(unittest.TestCase):
    def setUp(self):
        try:
            import streamlit as st
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Streamlit testing API is unavailable")
        from langgraph.checkpoint.memory import MemorySaver

        self.st = st
        self.AppTest = AppTest
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "RESEARCH_AGENT_CACHE_DIR": tmp.name,
            "RESEARCH_AGENT_AUTOSAVE_DIR": str(Path(tmp.name) / "outputs"),
            "RESEARCH_AGENT_LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "",
            "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "",
        })
        env.start()
        self.addCleanup(env.stop)
        # Tests must not load the developer's real .env credentials.
        dotenv = patch("dotenv.load_dotenv", return_value=False)
        dotenv.start()
        self.addCleanup(dotenv.stop)
        self.saver = MemorySaver()
        saver_factory = patch.object(orchestrator, "get_checkpointer", return_value=self.saver)
        saver_factory.start()
        self.addCleanup(saver_factory.stop)
        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)

    def app(self):
        app = self.AppTest.from_file("app.py").run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def start(self, app):
        return next(b for b in app.button if b.label == "Start")

    def fill(self, app, topic="topic", insight="initial hypothesis"):
        next(w for w in app.text_area if w.label == "Research direction").set_value(topic)
        next(w for w in app.text_area if w.label == "Your intuition / experience").set_value(insight)

    def test_start_explains_all_missing_fields_and_updates_without_running(self):
        app = self.app()
        self.assertFalse(self.start(app).disabled)
        self.assertFalse(app.error)
        with patch.object(orchestrator, "start_dialogue") as start_dialogue:
            self.start(app).click().run(timeout=30)
            error = "\n".join(item.value for item in app.error)
            self.assertIn("Research direction:", error)
            self.assertIn("Your intuition / experience:", error)
            self.assertIn("API Key:", error)
            self.assertIn("Configuration → Model settings", error)
            self.fill(app)
            app.run(timeout=30)
            error = "\n".join(item.value for item in app.error)
            self.assertNotIn("Research direction:", error)
            self.assertNotIn("Your intuition / experience:", error)
            self.assertIn("API Key:", error)
            start_dialogue.assert_not_called()
        self.assertEqual(app.session_state["phase"], "input")

    def test_whitespace_and_placeholder_key_do_not_start(self):
        os.environ["DEEPSEEK_API_KEY"] = "your-key"
        app = self.app()
        self.fill(app, "   ", "\n\t")
        with patch.object(orchestrator, "start_dialogue") as start_dialogue:
            self.start(app).click().run(timeout=30)
            start_dialogue.assert_not_called()
        error = "\n".join(item.value for item in app.error)
        for label in ("Research direction:", "Your intuition / experience:", "API Key:"):
            self.assertIn(label, error)

    def test_environment_key_requires_explicit_selection_before_starting(self):
        secret = "test-environment-key-not-a-real-key"
        os.environ["DEEPSEEK_API_KEY"] = secret
        app = self.app()
        self.assertEqual(app.text_input(key="settings_deepseek_api_key").value, "")
        self.assertFalse(app.success)
        self.assertFalse(app.checkbox(key="settings_use_configured_deepseek_key").value)
        self.assertTrue(any("has not been selected" in w.value for w in app.warning))
        visible_text = "\n".join(w.value for kind in (app.markdown, app.caption, app.success, app.warning) for w in kind)
        self.assertNotIn(secret, visible_text)
        self.fill(app, "  topic  ", "  initial hypothesis  ")
        with patch.object(orchestrator, "start_dialogue") as start_dialogue:
            self.start(app).click().run(timeout=30)
            self.assertTrue(any("API Key:" in e.value for e in app.error))
            start_dialogue.assert_not_called()
            app.checkbox(key="settings_use_configured_deepseek_key").check().run(timeout=30)
            self.assertFalse(app.error)
            start_dialogue.assert_not_called()
        self.assertTrue(any("explicitly selected" in w.value for w in app.success))

        def elicit(state):
            # The loading container must already exist before any model work.
            self.assertTrue(start_status.called)
            self.assertIn("Starting research", start_status.call_args.args[0])
            return {"messages": [{"role": "assistant", "content": "What limitation matters most?"}],
                    "dialogue_turns": 1, "friction_points": []}

        with patch.object(self.st, "status", wraps=self.st.status) as start_status, patch.object(orchestrator, "elicit_node", elicit):
            self.start(app).click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["phase"], "graph_elicit")
        self.assertEqual(app.session_state["state"]["topic"], "topic")
        self.assertEqual(app.session_state["state"]["user_insight"], "initial hypothesis")
        self.assertTrue(any("Research started successfully" in w.value for w in app.success))
        visible_text = "\n".join(w.value for kind in (app.markdown, app.caption, app.success, app.warning) for w in kind)
        self.assertNotIn(secret, visible_text)

    def test_sidebar_key_starts_with_visible_progress_and_success(self):
        app = self.app()
        app.text_input(key="settings_deepseek_api_key").set_value("test-sidebar-key").run(timeout=30)
        self.fill(app)

        def elicit(state):
            self.assertTrue(start_status.called)
            return {"messages": [{"role": "assistant", "content": "What limitation matters most?"}],
                    "dialogue_turns": 1, "friction_points": []}

        with patch.object(self.st, "status", wraps=self.st.status) as start_status, patch.object(orchestrator, "elicit_node", elicit):
            self.start(app).click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["phase"], "graph_elicit")
        self.assertTrue(any("Research started successfully" in w.value for w in app.success))

    def test_start_failure_shows_error_status_without_success(self):
        app = self.app()
        app.text_input(key="settings_deepseek_api_key").set_value("test-sidebar-key").run(timeout=30)
        self.fill(app)
        with patch.object(orchestrator, "start_dialogue", side_effect=RuntimeError("model request timed out")):
            self.start(app).click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["phase"], "input")
        self.assertTrue(any("model request timed out" in w.value for w in app.error))
        statuses = app.get("status")
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].state, "error")
        self.assertIn("could not start", statuses[0].label)
        self.assertFalse(any("Research started successfully" in w.value for w in app.success))

    def test_sidebar_prioritizes_expanded_settings_and_checks_selected_provider(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-key"
        app = self.app()
        self.assertEqual(
            app.selectbox(key="settings_provider").options,
            ["DeepSeek", "Gemini", "OpenAI", "Anthropic"],
        )
        expanders = list(app.sidebar.expander)
        self.assertEqual(expanders[0].label, "Model settings")
        self.assertTrue(expanders[0].proto.expanded)
        sessions = next(e for e in expanders if e.label == "Sessions and recovery")
        self.assertFalse(sessions.proto.expanded)
        self.assertTrue(any(w.label == "Load another session" for w in sessions.text_input))
        app.selectbox(key="settings_provider").set_value("openai").run(timeout=30)
        self.fill(app)
        with patch.object(orchestrator, "start_dialogue") as start_dialogue:
            self.start(app).click().run(timeout=30)
            start_dialogue.assert_not_called()
        self.assertTrue(any("OPENAI_API_KEY" in e.value for e in app.error))
        app.text_input(key="settings_openai_api_key").set_value("test-sidebar-key").run(timeout=30)
        self.assertFalse(app.error)
        self.assertEqual(app.session_state["phase"], "input")
        self.assertTrue(any("the sidebar" in w.value for w in app.success))


class WebWorkflowTests(unittest.TestCase):
    def test_restore_direction_select_revise_and_approve(self):
        try:
            import streamlit as st
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Streamlit testing API is unavailable")

        calls = Counter()

        def elicit(state):
            calls["elicit"] += 1
            return {"friction_points": ["limited labels"], "dialogue_turns": 2}

        def idea(state):
            calls["idea"] += 1
            return {"candidate_directions": [{"name": "Direction A"}, {"name": "Direction B"}]}

        def proposal(state):
            calls["proposal"] += 1
            return {"research_proposal": "Proposal for " + state["selected_direction"]["name"]}

        def revision(state):
            calls["revision"] += 1
            return {"research_proposal": "Revised: " + state["human_feedback"],
                    "proposal_revision_count": state.get("proposal_revision_count", 0) + 1,
                    "human_feedback": ""}

        def code(state):
            calls["code"] += 1
            return {"core_modification": "def solve(): pass"}

        replacements = {name: (lambda state: {}) for name in (
            "paper_expand_node", "idea_refine_node", "assumption_breaking_node",
            "problem_reframing_node", "story_arc_node", "necessity_check_node",
        )}
        replacements.update(elicit_node=elicit, idea_node=idea, proposal_node=proposal,
                            proposal_revision_node=revision, generate_core_code_node=code)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "RESEARCH_AGENT_CACHE_DIR": tmp, "RESEARCH_AGENT_AUTOSAVE_DIR": str(Path(tmp) / "outputs"),
        }):
            db_url = f"sqlite:///{Path(tmp) / 'web.sqlite'}"
            savers = []

            def saver_factory():
                saver = _sqlite_checkpointer(db_url)
                savers.append(saver)
                return saver

            st.cache_resource.clear()
            try:
                with patch.multiple(orchestrator, **replacements), patch.object(orchestrator, "get_checkpointer", saver_factory):
                    saver = _sqlite_checkpointer(db_url)
                    try:
                        graph = orchestrator.build_graph(checkpointer=saver)
                        config = {"configurable": {"thread_id": "web-shared-flow"}}
                        graph.invoke({"topic": "topic", "workflow": "orchestrator",
                                      "ui_phase": "graph_elicit"}, config)
                        self.assertEqual(graph.get_state(config).next, ("human_direction_select",))
                    finally:
                        saver.conn.close()

                    app = AppTest.from_file("app.py").run(timeout=30)
                    app.text_input(key="resume_session_input").set_value("web-shared-flow")
                    next(b for b in app.button if b.label == "Load session").click().run(timeout=30)
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    # The graph checkpoint wins over the outdated UI phase.
                    self.assertEqual(app.session_state["phase"], "graph_direction")
                    self.assertEqual(calls["elicit"], 1)
                    self.assertEqual(calls["idea"], 1)

                    stale_tab = AppTest.from_file("app.py")
                    stale_tab.query_params["session_id"] = "web-shared-flow"
                    stale_tab.run(timeout=30)
                    self.assertEqual(stale_tab.session_state["phase"], "graph_direction")

                    app.radio(key="graph_direction_idx").set_value(1)
                    with patch("utils.artifacts.atomic_write_text", side_effect=OSError("disk quota exceeded")):
                        next(b for b in app.button if b.label == "Confirm direction").click().run(timeout=30)
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    self.assertEqual(app.session_state["state"]["selected_direction"]["name"], "Direction B")
                    self.assertEqual(app.session_state["phase"], "graph_proposal")
                    self.assertEqual(calls["code"], 0)
                    self.assertTrue(any("disk quota exceeded" in warning.value for warning in app.warning))
                    calls_before_retry = calls.copy()
                    next(b for b in app.button if b.label == "Retry saving outputs").click().run(timeout=30)
                    self.assertFalse(app.exception)
                    self.assertEqual(calls, calls_before_retry)
                    self.assertFalse(app.session_state["_artifact_save_error"])
                    self.assertTrue((Path(tmp) / "outputs" / "web-shared-flow" / "research_proposal.md").exists())

                    next(b for b in stale_tab.button if b.label == "Confirm direction").click().run(timeout=30)
                    self.assertFalse(stale_tab.exception)
                    self.assertTrue(any("another page or process" in error.value for error in stale_tab.error))
                    self.assertEqual(calls, calls_before_retry)

                    # Open the saved URL in a fresh UI session at the next gate.
                    # This also avoids AppTest retaining widgets from st.rerun's
                    # previous page that Streamlit has already removed from state.
                    app = AppTest.from_file("app.py")
                    app.query_params["session_id"] = "web-shared-flow"
                    app.run(timeout=30)
                    self.assertEqual(app.session_state["phase"], "graph_proposal")
                    self.assertEqual(app.session_state["state"]["selected_direction"]["name"], "Direction B")
                    app.text_area(key="graph_proposal_feedback").set_value("add an ablation")
                    next(b for b in app.button if b.label == "Submit proposal review").click().run(timeout=30)
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    self.assertEqual(app.session_state["phase"], "graph_proposal")
                    self.assertEqual(app.session_state["state"]["proposal_revision_count"], 1)
                    self.assertIn("add an ablation", app.session_state["state"]["research_proposal"])
                    self.assertEqual(calls["code"], 0)

                    app.text_area(key="graph_proposal_feedback").set_value("approved")
                    next(b for b in app.button if b.label == "Submit proposal review").click().run(timeout=30)
                    self.assertFalse(app.exception)
                    self.assertFalse(app.error)
                    self.assertEqual(app.session_state["phase"], "graph_done")
                    self.assertEqual(calls, Counter(elicit=1, idea=1, proposal=1, revision=1, code=1))
            finally:
                st.cache_resource.clear()
                for saver in savers:
                    saver.conn.close()


if __name__ == "__main__":
    unittest.main()

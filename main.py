# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Aporia — CLI
"""

import os, sys, json, argparse
import tempfile
from utils.artifacts import save_artifacts, save_failure_message
from utils.session_runtime import checkpoint_id
from utils.storage import output_dir, SessionBusyError, StaleSessionError
from pathlib import Path
from datetime import datetime, timezone

UI = {
    "you": "You",
    "topic_prompt": "What research direction are you thinking about? (Ctrl+C to exit at any time)",
    "intro": "Let's start with what you're trying to do. It doesn't need to be clear yet.",
    "exit_hint": "(Press Ctrl+C at any time to save progress and exit)",
    "searching": "Searching papers + mining assumptions...",
    "direction_pick": "Which direction do you pick? (1/2/3, or describe your own idea)",
    "papers_header": "Candidate papers (title/abstract). Full text is skipped by default; pick only if needed:",
    "pick_fulltext": "Which papers should we read full text for (PDF only)? e.g., 1,3 / all / Enter to skip",
    "pick_fulltext_before_code": "Before generating core code, which papers should we read full text for? e.g., 2,5 / all / Enter to skip",
    "proposal_ready": "A research proposal draft is ready.",
    "proposal_hint": "(Type anything to approve, or describe what to change.)",
    "building_story": "Building the story arc...",
    "generating_code": "Generating core algorithm code...",
    "done_files": "✅  Done! Files saved:",
    "direction_selected": "✓ Selected direction: {name}",
    "need_llm_config": "❌ Configure at least one LLM provider: GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY",
    "rate_limit_wait": "❌ LLM rate-limited/quota exceeded: wait about {s:.0f}s and retry.",
    "rate_limit_generic": "❌ LLM rate-limited/quota exceeded: retry later or switch model/key.",
    "resume_hint": "   You can run with --resume {sid} to continue the same session.",
    "session_id": "   Session ID: {sid}",
    "directions_found": "Found 3 candidate directions (each breaks a different assumption):",
    "broken_assumption": "Broken assumption: {v}",
    "one_line": "One-liner: {v}",
    "file_core": "  · core_algorithm.py    ← hand to Cursor / Claude Code",
    "file_proposal": "  · research_proposal.md ← story + checks + proposal",
    "file_cursor": "  · cursor_prompt.txt    ← paste into Cursor",
    "file_state": "  · research_state.json  ← resume state",
}


def _is_internal_marker(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if s.startswith("[") and s.endswith("]"):
        low = s.lower()
        if ("researcher profile" in low) or ("idea discovery" in low):
            return True
    return False


def _safe_json_state(state: dict) -> dict:
    if not isinstance(state, dict):
        return {}
    def _coerce(x):
        if isinstance(x, (str, int, float, bool, type(None))):
            return x
        if isinstance(x, dict):
            out = {}
            for kk, vv in x.items():
                if kk == "metadata":
                    continue
                out[str(kk)] = _coerce(vv)
            return out
        if isinstance(x, (list, tuple)):
            return [_coerce(i) for i in x]
        msg_type = getattr(x, "type", None)
        content = getattr(x, "content", None)
        if msg_type is not None and content is not None:
            return {"type": str(msg_type), "content": str(content)}
        role = getattr(x, "role", None)
        if role is not None and content is not None:
            return {"role": str(role), "content": str(content)}
        return str(x)

    clean = {k: _coerce(v) for k, v in state.items() if k != "metadata"}
    clean["_autosaved_at_utc"] = datetime.now(timezone.utc).isoformat()
    return clean


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _autosave_root() -> Path:
    base = (os.environ.get("RESEARCH_AGENT_AUTOSAVE_DIR") or "outputs").strip()
    return Path(base)


def _snapshot_write(session_id: str, kind: str, ext: str, content: str) -> None:
    try:
        if not content:
            return
        sid = (session_id or "unknown").strip() or "unknown"
        out_dir = output_dir(sid)
        out_dir.mkdir(parents=True, exist_ok=True)

        pattern = f"*_{kind}.{ext}"
        latest = None
        for p in sorted(out_dir.glob(pattern)):
            latest = p
        if latest and latest.exists():
            try:
                if latest.read_text(encoding="utf-8") == content:
                    return
            except Exception:
                pass

        name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{kind}.{ext}"
        _atomic_write_text(out_dir / name, content)
    except Exception as exc:
        print(f"Snapshot save failed: {exc}", file=sys.stderr)


def _atomic_write_text(path: str | Path, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, p)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _write_if_changed(path: str, content: str) -> None:
    p = Path(path)
    if p.exists() and p.read_text(encoding="utf-8") == content:
        return
    _atomic_write_text(p, content)


def _autosave_partial(state: dict) -> None:
    report = save_artifacts(state)
    if report["failed"]:
        print(save_failure_message(report), file=sys.stderr)
    return report


def _autosave_from_graph(graph, config) -> None:
    try:
        from utils.storage import session_lock
        with session_lock(config["configurable"]["thread_id"]):
            st = graph.get_state(config).values
            st = {**st, "session_id": config["configurable"]["thread_id"]}
            _autosave_partial(st)
    except Exception as exc:
        print(f"Cannot read checkpoint for output saving: {exc}", file=sys.stderr)


def _has_real_key(v: str | None) -> bool:
    if not v:
        return False
    s = v.strip()
    if not s:
        return False
    low = s.lower()
    if "your-key" in low or "your key" in low:
        return False
    if low in ("changeme", "replace-me", "replace_with_your_key", "todo"):
        return False
    return True


def _handle_rate_limit_error(err: Exception, config: dict | None = None) -> bool:
    msg = str(err)
    low = msg.lower()
    if ("resource_exhausted" not in low) and ("too many requests" not in low) and (" 429 " not in f" {low} ") and ("quota exceeded" not in low):
        return False
    import re, time
    retry_s = None
    m = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
    if m:
        try:
            retry_s = float(m.group(1))
        except Exception:
            retry_s = None
    if retry_s is None:
        m = re.search(r"retryDelay['\"]?\s*:\s*['\"]([0-9]+)s['\"]", msg)
        if m:
            try:
                retry_s = float(m.group(1))
            except Exception:
                retry_s = None
    sid = None
    if isinstance(config, dict):
        sid = (config.get("configurable") or {}).get("thread_id")
    if retry_s:
        print("\n" + UI["rate_limit_wait"].format(s=retry_s))
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        time.sleep(min(120.0, retry_s + 0.5))
    else:
        print("\n" + UI["rate_limit_generic"])
        if sid:
            print(UI["resume_hint"].format(sid=sid))
    return True


def _is_approved(v: str | None) -> bool:
    return (v or "").strip().lower() in ("approved", "yes", "ok")


def _handle_llm_config_error(err: Exception, config: dict | None = None) -> bool:
    msg = str(err or "")
    if not msg:
        return False
    low = msg.lower()
    sid = None
    if isinstance(config, dict):
        sid = (config.get("configurable") or {}).get("thread_id")
    if "invalid gemini_api_key" in low:
        print("\n❌ Invalid GEMINI_API_KEY. Update GEMINI_API_KEY in your environment (or .env) and retry.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "invalid openai_api_key" in low:
        print("\n❌ Invalid OPENAI_API_KEY. Update OPENAI_API_KEY in your environment (or .env) and retry.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "invalid anthropic_api_key" in low:
        print("\n❌ Invalid ANTHROPIC_API_KEY. Update ANTHROPIC_API_KEY in your environment (or .env) and retry.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "gemini_api_key is required" in low:
        print("\n❌ GEMINI_API_KEY is required when provider=gemini. Set it and retry, or unset RESEARCH_AGENT_LLM_PROVIDER to auto-pick another provider.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "openai_api_key is required" in low:
        print("\n❌ OPENAI_API_KEY is required when provider=openai. Set it and retry, or switch provider.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "anthropic_api_key is required" in low:
        print("\n❌ ANTHROPIC_API_KEY is required when provider=anthropic. Set it and retry, or switch provider.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "ollama is not reachable" in low:
        print("\n❌ " + msg)
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "no llm provider available" in low or "missing dependency" in low:
        print("\n❌ " + msg)
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if "network error while calling llm provider" in low:
        print("\n❌ " + msg)
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if (
        "server disconnected without sending a response" in low
        or "remoteprotocolerror" in low
        or "readtimeout" in low
        or "connecttimeout" in low
        or "timed out" in low
    ):
        print("\n❌ Network error while calling the LLM provider. Please retry.")
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    if ("not_found" in low or "not found" in low) and "model" in low:
        print("\n❌ " + msg)
        if sid:
            print(UI["resume_hint"].format(sid=sid))
        return True
    return False


def check_env():
    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv(".env", override=True)
        elif Path(".env.example").exists():
            load_dotenv(".env.example", override=False)
    except Exception:
        pass

    provider = (os.environ.get("RESEARCH_AGENT_LLM_PROVIDER") or "").strip().lower()
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if provider in ("gemini", "google") and not _has_real_key(gemini_key):
        print("❌ GEMINI_API_KEY is required when provider=gemini. Set a valid key in .env or your shell.")
        sys.exit(1)
    if provider in ("openai",) and not _has_real_key(openai_key):
        print("❌ OPENAI_API_KEY is required when provider=openai. Set a valid key in .env or your shell.")
        sys.exit(1)
    if provider in ("anthropic", "claude") and not _has_real_key(anthropic_key):
        print("❌ ANTHROPIC_API_KEY is required when provider=anthropic. Set a valid key in .env or your shell.")
        sys.exit(1)

    has_any_key = any(
        _has_real_key(os.environ.get(k))
        for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    )
    if not has_any_key and not provider:
        print("❌ Configure at least one LLM provider: GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY")
        sys.exit(1)


def _get_snapshot(graph, config):
    snapshot = graph.get_state(config)
    values = getattr(snapshot, "values", None) or {}
    next_nodes = tuple(getattr(snapshot, "next", None) or ())
    return snapshot, values, next_nodes


def _last_assistant_message(state: dict) -> str:
    for message in reversed(state.get("messages", []) or []):
        if isinstance(message, dict):
            if message.get("role") == "assistant":
                return str(message.get("content", "") or "")
            continue
        if getattr(message, "type", "") == "ai":
            return str(getattr(message, "content", "") or "")
    return ""


def _pending_interaction(state: dict, next_nodes: tuple[str, ...]) -> str | None:
    next_set = set(next_nodes)
    if "human_direction_select" in next_set:
        return "direction_select"
    if "human_proposal_review" in next_set:
        return "proposal_review"
    if "human_elicit_continue" in next_set:
        return "elicit_continue"
    if state.get("candidate_directions") and not state.get("selected_direction"):
        return "direction_select"
    if (
        state.get("research_proposal")
        and not state.get("core_modification")
        and not _is_approved(state.get("human_feedback"))
    ):
        return "proposal_review"
    if not next_set and state.get("core_modification"):
        return "done"
    return None


def _stream_until_pause(graph, config, last_ai: str):
    """Advance the graph and return (latest assistant text, should_continue)."""
    while True:
        try:
            for event in graph.stream(None, config, stream_mode="values"):
                for message in reversed(event.get("messages", []) or []):
                    if isinstance(message, dict):
                        if message.get("role") != "assistant":
                            continue
                        content = str(message.get("content", "") or "")
                    elif getattr(message, "type", "") == "ai":
                        content = str(getattr(message, "content", "") or "")
                    else:
                        continue
                    if content and content != last_ai and not _is_internal_marker(content):
                        print(f"\nAI: {content}\n")
                        last_ai = content
                    break

                if event.get("friction_points") and not event.get("candidate_directions"):
                    print(f"\n{UI['searching']}\n")
                if event.get("core_modification"):
                    _save_outputs(event)
                _autosave_from_graph(graph, config)
            return last_ai, True
        except Exception as e:
            _autosave_from_graph(graph, config)
            if _handle_rate_limit_error(e, config=config):
                continue
            if _handle_llm_config_error(e, config=config):
                return last_ai, False
            raise


def _handle_direction_selection(graph, config) -> bool:
    state = graph.get_state(config).values
    directions = state.get("candidate_directions", []) or []
    _print_directions(directions)
    choice = input("\n" + UI["direction_pick"] + "\n> ").strip()
    if choice in ("1", "2", "3") and len(directions) >= int(choice):
        selected = directions[int(choice) - 1]
    else:
        selected = {
            "name": choice,
            "broken_assumption": choice,
            "one_line": choice,
            "rationale": "",
            "reframed_problem": "",
        }

    raw_papers = state.get("raw_papers", []) or []
    if raw_papers:
        _print_papers(raw_papers[:10])
        pick = input("\n" + UI["pick_fulltext"] + "\n> ").strip()
        paper_ids = _parse_paper_picks(pick, raw_papers[:10])
    else:
        paper_ids = []

    changes = {
        "selected_direction": selected,
        "paper_fulltext_request": paper_ids,
        # Choosing a direction is distinct from approving the later proposal.
        # Keep this empty so route_after_proposal reaches its review gate.
        "human_feedback": "",
    }
    print("\n" + UI["direction_selected"].format(name=selected.get("name", choice)))
    print(UI["building_story"] + "\n")
    return changes


def _handle_proposal_review(graph, config) -> bool:
    state = graph.get_state(config).values
    print("\n" + "─" * 50)
    print(UI["proposal_ready"] + "\n")
    print((state.get("research_proposal") or "")[:800])
    print("\n" + UI["proposal_hint"])

    raw_papers = state.get("raw_papers", []) or []
    if raw_papers:
        _print_papers(raw_papers[:10])
        pick = input("\n" + UI["pick_fulltext_before_code"] + "\n> ").strip()
        paper_ids = _parse_paper_picks(pick, raw_papers[:10])
    else:
        paper_ids = []
    feedback = input(f"{UI['you']}: ").strip() or "approved"
    changes = {
        "human_feedback": feedback,
        "paper_fulltext_request": paper_ids,
    }
    if _is_approved(feedback):
        print("\n" + UI["generating_code"] + "\n")
    else:
        print("\nRevising the proposal from your feedback...\n")
    return changes


def run(resume_session_id: str | None = None):
    print("\n" + "="*58)
    print("  Aporia")
    print("  Your Phase-0 AI research partner: turn vague instincts into core algorithms")
    print("="*58)
    print(f"\n{UI['intro']}")
    print(f"{UI['exit_hint']}\n")
    provider = (os.environ.get("RESEARCH_AGENT_LLM_PROVIDER") or "").strip().lower() or "auto"
    model = (os.environ.get("GEMINI_MODEL") or os.environ.get("OPENAI_MODEL") or os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OLLAMA_MODEL") or "").strip()
    if model:
        print(f"LLM: provider={provider} model={model}\n")

    from agents.orchestrator import resume_session, start_dialogue

    if resume_session_id:
        try:
            graph, config = resume_session(resume_session_id)
            snapshot, state, next_nodes = _get_snapshot(graph, config)
            expected = checkpoint_id(snapshot)
        except Exception as e:
            print(f"\n❌ Unable to resume session: {e}")
            return
        sid = (config.get("configurable") or {}).get("thread_id", resume_session_id)
        print(f"\nResuming session: {sid}")
        print(f"Phase: {state.get('phase', 'unknown')}")
        if next_nodes:
            print(f"Next checkpoint: {', '.join(next_nodes)}")
        last_ai = _last_assistant_message(state)
        if last_ai:
            print(f"\nAI: {last_ai}\n")
        _autosave_from_graph(graph, config)
    else:
        topic = input(UI["topic_prompt"] + "\n> ").strip() or "TBD"
        try:
            graph, config, q = start_dialogue(topic, user_language="Auto")
        except Exception as e:
            if _handle_llm_config_error(e):
                return
            raise
        _autosave_from_graph(graph, config)
        sid = (config.get("configurable") or {}).get("thread_id")
        if sid:
            print(UI["session_id"].format(sid=sid))
        print(f"\nAI: {q}\n")
        last_ai = q or ""

    while True:
        try:
            snapshot, state, next_nodes = _get_snapshot(graph, config)
            expected = checkpoint_id(snapshot)
            pending = _pending_interaction(state, next_nodes)

            if pending == "done":
                with graph.session(config, expected_checkpoint=expected):
                    _save_outputs(state)
                print("Session is already complete.")
                break

            if pending == "direction_select":
                changes = _handle_direction_selection(graph, config)
            elif pending == "proposal_review":
                changes = _handle_proposal_review(graph, config)
            elif pending == "elicit_continue":
                ans = input(f"{UI['you']}: ").strip()
                if not ans:
                    continue
                changes = {
                    "human_feedback": ans,
                    "messages": [{"role": "user", "content": ans}],
                }
            else:
                # A crash may have happened between checkpoints. Continue the
                # persisted graph until it reaches its next human gate.
                with graph.session(config, expected_checkpoint=expected):
                    last_ai, should_continue = _stream_until_pause(graph, config, last_ai)
                if not should_continue:
                    return
                continue

            with graph.session(config, expected_checkpoint=expected):
                graph.update_state(config, changes)
                _autosave_from_graph(graph, config)
                last_ai, should_continue = _stream_until_pause(graph, config, last_ai)
            if not should_continue:
                return
        except (SessionBusyError, StaleSessionError) as exc:
            print(str(exc), file=sys.stderr)
            return
        except KeyboardInterrupt:
            _autosave_from_graph(graph, config)
            print("\n")
            break
        except Exception as e:
            _autosave_from_graph(graph, config)
            if _handle_llm_config_error(e, config=config):
                return
            raise



def _print_directions(directions):
    print("\n" + "─"*50)
    print(UI["directions_found"] + "\n")
    for i, d in enumerate(directions, 1):
        print(f"{i}. {d.get('name', f'Direction {i}')}") 
        print("   " + UI["broken_assumption"].format(v=d.get("broken_assumption", "")))
        print("   " + UI["one_line"].format(v=d.get("one_line", "")) + "\n")

def _print_papers(papers):
    print("\n" + "─"*50)
    print(UI["papers_header"] + "\n")
    for i, p in enumerate(papers, 1):
        title = p.get("title", "")
        year = p.get("year", "")
        src = p.get("source", "")
        pdf_mark = " PDF" if p.get("pdf_url") else ""
        score = p.get("relevance_score", None)
        reason = (p.get("relevance_reason", "") or "").strip()
        score_txt = f" | score={score}" if score is not None else ""
        print(f"{i}. [{year}] {title} ({src}{pdf_mark}{score_txt})")
        if reason:
            print(f"   reason: {reason}")


def _parse_paper_picks(text: str, papers: list[dict]) -> list[str]:
    if not text:
        return []
    t = text.strip().lower()
    if t in ("all", "*"):
        picks = []
        for p in papers:
            if not p.get("pdf_url"):
                continue
            pid = p.get("paper_id")
            if pid:
                picks.append(pid)
        return picks
    items = [x.strip() for x in text.split(",") if x.strip()]
    picks = []
    for it in items:
        if it.isdigit():
            idx = int(it)
            if 1 <= idx <= len(papers):
                pid = papers[idx - 1].get("paper_id")
                if pid:
                    picks.append(pid)
    return picks


def _jsonify(v):
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, dict):
        out = {}
        for k, vv in v.items():
            try:
                kk = str(k)
            except Exception:
                kk = repr(k)
            out[kk] = _jsonify(vv)
        return out
    if isinstance(v, (list, tuple, set)):
        return [_jsonify(x) for x in v]
    try:
        model_dump = getattr(v, "model_dump", None)
        if callable(model_dump):
            return _jsonify(model_dump())
    except Exception:
        pass
    try:
        to_dict = getattr(v, "dict", None)
        if callable(to_dict):
            return _jsonify(to_dict())
    except Exception:
        pass
    try:
        return {"__type__": type(v).__name__, "__repr__": repr(v)}
    except Exception:
        return {"__type__": type(v).__name__}


def _save_outputs(state: dict):
    report = _autosave_partial(state)
    for path in report["saved"]:
        print(f"Saved: {path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compress-pdfs", action="store_true")
    parser.add_argument("--pdf-dir", default=".")
    parser.add_argument("--resume", help="Resume session ID")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--rename", nargs=2, metavar=("SESSION_ID", "NAME"))
    parser.add_argument("--export", metavar="SESSION_ID")
    parser.add_argument("--export-path", help="ZIP destination")
    parser.add_argument("--delete", metavar="SESSION_ID", help="Delete session after creating recovery backup")
    parser.add_argument("--retry-save", metavar="SESSION_ID", help="Save checkpoint outputs without model calls")
    parser.add_argument("--clean-cache", action="store_true")
    parser.add_argument("--cache-days", type=int, default=30)
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv(".env", override=True)
        elif Path(".env.example").exists():
            load_dotenv(".env.example", override=False)
    except Exception:
        pass

    if args.compress_pdfs:
        from scripts.compress_pdfs import compress_and_zip
        compress_and_zip(input_dir=args.pdf_dir)
        sys.exit(0)

    if args.clean_cache:
        from utils.operations import clean_cache
        print(f"Removed {clean_cache(args.cache_days)} expired cache records.")
        sys.exit(0)
    if args.list_sessions or args.rename or args.export or args.delete or args.retry_save:
        from agents.orchestrator import build_graph
        from utils.sessions import list_sessions, rename_session, export_session, delete_session
        from utils.memory import close_checkpointer
        from utils.storage import atomic_write_bytes
        graph = build_graph()
        try:
            if args.list_sessions:
                for item in list_sessions(graph):
                    print(f"{item['session_id']}\t{item['title']}\t{item['updated']}")
            if args.rename:
                rename_session(graph, *args.rename)
            if args.export:
                path = Path(args.export_path) if args.export_path else output_dir(args.export) / "session.zip"
                atomic_write_bytes(path, export_session(graph, args.export))
                print(f"Exported: {path}")
            if args.delete:
                print(f"Session deleted; recovery files: {delete_session(graph, args.delete)}")
            if args.retry_save:
                config = {"configurable": {"thread_id": args.retry_save}}
                state = graph.get_state(config).values
                if not state:
                    raise ValueError("Session not found.")
                report = _save_outputs({**state, "session_id": args.retry_save})
                if report["failed"]:
                    sys.exit(1)
        finally:
            close_checkpointer(graph.checkpointer)
        sys.exit(0)

    check_env()
    run(args.resume)

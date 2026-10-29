"""Per-session deliverables with explicit, independently retryable save results."""
from utils.storage import atomic_write_text, json_text, output_dir, session_lock


def artifact_contents(state, *, include_state=True):
    files = {"research_state.json": json_text(state)} if include_state else {}
    parts = [state.get(key, "") or "" for key in (
        "story_arc", "method_necessity_check", "research_proposal",
    )]
    if any(part.strip() for part in parts):
        files["research_proposal.md"] = "\n\n---\n\n".join(part.strip() for part in parts if part.strip()) + "\n"
        if state.get("evidence_catalog") or state.get("evidence_warnings"):
            from utils.evidence import evidence_appendix
            files["research_proposal.md"] += "\n\n" + evidence_appendix(state) + "\n"
    if state.get("core_modification"):
        files["core_algorithm.py"] = (
            "# Aporia — Core Algorithm\n"
            f"# Direction: {(state.get('selected_direction') or {}).get('name', '')}\n"
            f"# Broken assumption: {state.get('broken_assumption', '')}\n\n"
            + state["core_modification"]
        )
    integration = (state.get("metadata") or {}).get("integration_prompt")
    if integration:
        files["cursor_prompt.txt"] = integration
    for key, filename in (("paper_outline", "paper_outline.md"), ("full_draft", "paper_draft.md"),
                          ("ablation_plan", "ablation_plan.md")):
        if state.get(key):
            files[filename] = state[key]
    if state.get("evidence_catalog") or state.get("evidence_warnings"):
        files["evidence.json"] = json_text({key: state.get(key, []) for key in (
            "evidence_catalog", "claim_evidence", "evidence_warnings",
        )})
    return files


def save_artifacts(state, session_id=None):
    sid = str(session_id or state.get("session_id") or "")
    report = {"saved": [], "failed": {}}
    try:
        directory = output_dir(sid)
        payload = {**state, "session_id": sid}
        contents = artifact_contents(payload, include_state=False)
        with session_lock(sid):
            try:
                contents = {"research_state.json": json_text(payload), **contents}
            except Exception as exc:
                report["failed"][str(directory / "research_state.json")] = str(exc)
            for name, text in contents.items():
                path = directory / name
                try:
                    atomic_write_text(path, text)
                    report["saved"].append(str(path))
                except Exception as exc:
                    report["failed"][str(path)] = str(exc)
    except Exception as exc:
        report["failed"][f"session {sid or '(missing ID)'}"] = str(exc)
    return report


def save_failure_message(report):
    if not report["failed"]:
        return ""
    details = "; ".join(f"{path}: {error}" for path, error in report["failed"].items())
    return (f"Output save failed: {details}. Saved files: {len(report['saved'])}. "
            "Retry saving outputs from the saved checkpoint; model execution is not required.")

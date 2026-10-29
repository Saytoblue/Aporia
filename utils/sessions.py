"""Session history, portable data exports and recoverable deletion."""
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import sqlite3
import uuid
import zipfile

from utils.artifacts import artifact_contents
from utils.storage import (cache_root, session_lock, output_dir, session_slug,
                           json_text, atomic_write_bytes)


@contextmanager
def _metadata():
    root = cache_root()
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(root / "sessions.sqlite"), timeout=30)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS session_info (session_id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        yield conn
    finally:
        conn.close()


def list_sessions(graph):
    """Read latest checkpoints, including sessions predating this module."""
    latest = {}
    for item in graph.checkpointer.list(None):
        sid = str(item.config["configurable"]["thread_id"])
        checkpoint = item.checkpoint
        if sid not in latest or checkpoint["id"] > latest[sid]["checkpoint_id"]:
            state = checkpoint.get("channel_values", {})
            latest[sid] = {"session_id": sid, "checkpoint_id": checkpoint["id"],
                           "topic": state.get("topic", ""), "updated": checkpoint.get("ts", ""),
                           "phase": state.get("phase", ""), "title": state.get("topic", "") or sid}
    with _metadata() as conn:
        titles = dict(conn.execute("SELECT session_id,title FROM session_info"))
    for sid, item in latest.items():
        item["title"] = titles.get(sid, item["title"])
    return sorted(latest.values(), key=lambda item: item["updated"], reverse=True)


def rename_session(graph, session_id, title):
    title = title.strip()
    if not title or len(title) > 200:
        raise ValueError("A session name must contain 1–200 characters.")
    with session_lock(session_id):
        _snapshot(graph, session_id)
        with _metadata() as conn, conn:
            conn.execute("INSERT OR REPLACE INTO session_info VALUES (?,?)", (session_id, title))


def _snapshot(graph, sid):
    snapshot = graph.get_state({"configurable": {"thread_id": sid}})
    if not snapshot.values:
        raise ValueError(f"Session {sid!r} was not found.")
    return snapshot


def export_session(graph, session_id):
    """Export latest state and outputs; this is not an importable checkpoint DB."""
    with session_lock(session_id):
        snapshot = _snapshot(graph, session_id)
        with _metadata() as conn:
            row = conn.execute("SELECT title FROM session_info WHERE session_id=?", (session_id,)).fetchone()
        files = artifact_contents(snapshot.values)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("session.json", json_text({
                "format_version": 1, "session_id": session_id, "title": row[0] if row else "",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "next": snapshot.next, "state": snapshot.values,
                "checkpoint_config": snapshot.config,
            }))
            for name, content in files.items():
                archive.writestr("outputs/" + name, content)
            directory = output_dir(session_id)
            if directory.exists():
                for path in directory.iterdir():
                    if path.is_file() and not path.is_symlink() and path.name not in files and path.suffix.lower() != ".zip":
                        archive.write(path, "outputs/" + path.name)
        return buffer.getvalue()


def delete_session(graph, session_id):
    """Back up checkpoint history before deleting; return the recovery directory."""
    with session_lock(session_id):
        bundle = export_session(graph, session_id)
        recovery = cache_root() / ".trash" / (session_slug(session_id) + "-" + uuid.uuid4().hex)
        atomic_write_bytes(recovery / "session.zip", bundle)
        # Keep full saver records, including pending writes, for manual recovery.
        records = list(graph.checkpointer.list({"configurable": {"thread_id": session_id}}))
        kind, history = graph.checkpointer.serde.dumps_typed(records)
        atomic_write_bytes(recovery / "checkpoints.bin", history)
        atomic_write_bytes(recovery / "checkpoint_encoding.txt", kind.encode())
        try:
            graph.checkpointer.delete_thread(session_id)
            directory = output_dir(session_id)
            if directory.exists():
                directory.rename(recovery / "outputs")
            from utils.operations import delete_session_cache
            delete_session_cache(session_id)
            with _metadata() as conn, conn:
                conn.execute("DELETE FROM session_info WHERE session_id=?", (session_id,))
        except Exception as exc:
            raise RuntimeError(f"Deletion was incomplete. Recovery files: {recovery}. {exc}") from exc
        return recovery

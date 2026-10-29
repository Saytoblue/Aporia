# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Persistence / checkpoint selection.

SQLite is the local default so a session survives process restarts. MemorySaver
is available only as an explicit development fallback.
"""
import os
import atexit
import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sqlite_path(db_url: str) -> str:
    raw = db_url.removeprefix("sqlite:///").strip()
    if not raw:
        raw = ".aporia/checkpoints.sqlite"
    if raw != ":memory:":
        path = Path(raw).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    return raw


def _sqlite_checkpointer(db_url: str):
    from langgraph.checkpoint.sqlite import SqliteSaver

    # Construct the saver with a live connection rather than returning the
    # context manager produced by from_conn_string().
    conn = sqlite3.connect(_sqlite_path(db_url), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
    except Exception:
        conn.close()
        raise
    return saver


def close_checkpointer(saver):
    """Close owned resources; safe to call repeatedly for managed PostgreSQL."""
    manager = getattr(saver, "_aporia_context", None)
    if manager is not None:
        saver._aporia_context = None
        manager.__exit__(None, None, None)
    elif getattr(saver, "conn", None) is not None and isinstance(saver.conn, sqlite3.Connection):
        saver.conn.close()

def get_checkpointer():
    """
    Pick a checkpointer based on environment variables.
    Uses a local SQLite database when DATABASE_URL is not set.
    """
    db_url = (os.environ.get("DATABASE_URL") or "sqlite:///.aporia/checkpoints.sqlite").strip()
    if db_url.startswith("sqlite"):
        try:
            return _sqlite_checkpointer(db_url)
        except ImportError as exc:
            if not _truthy(os.environ.get("APORIA_ALLOW_MEMORY_CHECKPOINTS")):
                raise RuntimeError(
                    "SQLite checkpoint support is unavailable. Install "
                    "langgraph-checkpoint-sqlite or set "
                    "APORIA_ALLOW_MEMORY_CHECKPOINTS=1 for development."
                ) from exc
    if db_url.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            manager = PostgresSaver.from_conn_string(db_url)
            saver = manager.__enter__()
            try:
                saver.setup()
            except Exception:
                manager.__exit__(*__import__("sys").exc_info())
                raise
            saver._aporia_context = manager
            atexit.register(close_checkpointer, saver)
            return saver
        except ImportError as exc:
            if not _truthy(os.environ.get("APORIA_ALLOW_MEMORY_CHECKPOINTS")):
                raise RuntimeError(
                    "PostgreSQL checkpoint support is unavailable. Install "
                    "langgraph-checkpoint-postgres or set "
                    "APORIA_ALLOW_MEMORY_CHECKPOINTS=1 for development."
                ) from exc
    if _truthy(os.environ.get("APORIA_ALLOW_MEMORY_CHECKPOINTS")):
        return MemorySaver()
    raise ValueError(
        "Unsupported DATABASE_URL. Use sqlite:///path/to/checkpoints.sqlite "
        "or postgresql://... ."
    )

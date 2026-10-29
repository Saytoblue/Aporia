"""Durable task attempts and successful request results for graph recovery.

The journal is separate from graph checkpoints: a returned model response can
survive a node failure before its state update is checkpointed. It does not
provide exactly-once execution at the remote provider.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


_serde = JsonPlusSerializer()


def request_key(value):
    """Hash JSON-compatible inputs without storing prompts or credentials."""
    def encode(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        raise TypeError(f"Unsupported request input: {type(obj).__name__}")

    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=encode)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@contextmanager
def _database():
    root = Path(os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache"))
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(root / "operations.sqlite"), timeout=30)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS attempts (
                task TEXT PRIMARY KEY, count INTEGER NOT NULL, status TEXT NOT NULL,
                updated REAL NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS results (
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, data BLOB NOT NULL,
                created REAL NOT NULL)""")
            for table in ("attempts", "results"):
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if "session_id" not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN session_id TEXT")
        yield conn
    finally:
        conn.close()


def load_result(key, max_age=None):
    with _database() as conn:
        row = conn.execute("SELECT kind, data, created FROM results WHERE key = ?", (key,)).fetchone()
    if row is None or (max_age is not None and time.time() - row[2] >= max_age):
        return False, None
    return True, _serde.loads_typed((row[0], row[1]))


def save_result(key, value):
    kind, data = _serde.dumps_typed(value)
    with _database() as conn, conn:
        task = _task.get()
        conn.execute("INSERT OR REPLACE INTO results (key,kind,data,created,session_id) VALUES (?, ?, ?, ?, ?)",
                     (key, kind, data, time.time(), task.session_id if task else None))


@dataclass
class _Task:
    key: str
    session_id: str
    request_index: int = 0


_task: ContextVar[_Task | None] = ContextVar("aporia_operation_task", default=None)


def model_request_key(identity, args, kwargs):
    task = _task.get()
    if task is None:
        return None  # No global model cache across sessions or user turns.
    index = task.request_index
    task.request_index += 1
    try:
        return request_key(["llm-v1", task.key, index, identity, args, kwargs])
    except (TypeError, ValueError):
        return None  # Custom nonserializable inputs retain normal invoke behavior.


@contextmanager
def task_attempt(name, config):
    configurable = config.get("configurable", {})
    # LangGraph exposes a namespace containing the task ID in node metadata.
    # It stays stable on resume; a legitimate loop creates a new task ID.
    namespace = config.get("metadata", {}).get("langgraph_checkpoint_ns")
    thread = configurable.get("thread_id")
    if thread is None or not namespace:
        yield 1
        return
    key = request_key(["task-v1", str(thread), name, namespace])
    with _database() as conn, conn:
        conn.execute("""INSERT INTO attempts (task,count,status,updated,session_id) VALUES (?, 1, 'running', ?, ?)
            ON CONFLICT(task) DO UPDATE SET count=count+1, status='running', updated=excluded.updated""",
                     (key, time.time(), str(thread)))
        count = conn.execute("SELECT count FROM attempts WHERE task = ?", (key,)).fetchone()[0]
    token = _task.set(_Task(key, str(thread)))
    status = "failed"
    try:
        yield count
        status = "completed"
    finally:
        _task.reset(token)
        with _database() as conn, conn:
            conn.execute("UPDATE attempts SET status = ?, updated = ? WHERE task = ?",
                         (status, time.time(), key))


def delete_session_cache(session_id):
    with _database() as conn, conn:
        for table in ("results", "attempts"):
            conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))


def clean_cache(days=30):
    """Expire shared search results and completed tasks; retain retry results."""
    if days < 1:
        raise ValueError("Cache retention must be at least one day.")
    from utils.storage import session_lock, SessionBusyError

    cutoff = time.time() - days * 86400
    removed = 0
    with _database() as conn:
        sessions = [r[0] for r in conn.execute(
            "SELECT DISTINCT session_id FROM attempts WHERE status='completed' AND updated < ? AND session_id IS NOT NULL", (cutoff,))]
        with conn:
            removed += conn.execute("DELETE FROM results WHERE session_id IS NULL AND created < ?", (cutoff,)).rowcount
    for sid in sessions:
        try:
            with session_lock(sid), _database() as conn, conn:
                # A failed node may need old successful calls when it retries.
                pending = conn.execute("SELECT 1 FROM attempts WHERE session_id=? AND status!='completed'", (sid,)).fetchone()
                if pending:
                    continue
                removed += conn.execute("DELETE FROM results WHERE session_id=? AND created < ?", (sid, cutoff)).rowcount
                removed += conn.execute("DELETE FROM attempts WHERE session_id=? AND updated < ? AND status='completed'", (sid, cutoff)).rowcount
        except SessionBusyError:
            continue
    return removed

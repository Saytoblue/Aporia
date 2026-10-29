"""Shared atomic storage, safe session paths and local process locks."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading


class SessionBusyError(RuntimeError):
    pass


class StaleSessionError(RuntimeError):
    pass


def cache_root():
    return Path(os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache"))


def session_slug(session_id):
    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("A session ID is required to save research outputs.")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", sid):
        return sid
    return "session-" + hashlib.sha256(sid.encode()).hexdigest()


def output_dir(session_id):
    root = Path(os.environ.get("RESEARCH_AGENT_AUTOSAVE_DIR") or "outputs").resolve()
    path = root / session_slug(session_id)
    if path.is_symlink():
        raise ValueError(f"Session output directory must not be a symlink: {path}")
    return path


def json_default(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Cannot export {type(value).__name__}")


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n"


def atomic_write_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_text(path, content):
    atomic_write_bytes(path, content.encode("utf-8"))


_held = threading.local()


@contextmanager
def named_lock(name, *, blocking=False):
    directory = cache_root() / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory.resolve() / (hashlib.sha256(name.encode()).hexdigest() + ".lock")
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = {}
    # Reentry is permitted only on the owning thread in the owning process.
    key = (os.getpid(), str(path))
    if key in held:
        yield
        return
    with path.open("a+b") as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise SessionBusyError("This session is running elsewhere. Wait for it to finish, then reload before submitting.") from exc
        held[key] = file
        try:
            yield
        finally:
            held.pop(key, None)
            fcntl.flock(file, fcntl.LOCK_UN)


def session_lock(session_id):
    session_slug(session_id)
    return named_lock("session:" + str(session_id))

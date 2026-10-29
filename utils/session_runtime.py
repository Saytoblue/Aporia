"""Serialize graph writes and reject stale submissions across CLI and Web."""
from contextlib import contextmanager

from utils.storage import session_lock, StaleSessionError


STATE_VERSION = 1
_UNSET = object()


def checkpoint_id(snapshot):
    return ((snapshot.config or {}).get("configurable") or {}).get("checkpoint_id")


def migration_patch(state):
    version = int(state.get("schema_version", 0))
    if version > STATE_VERSION:
        raise ValueError(f"Session state version {version} is newer than supported version {STATE_VERSION}.")
    if version == 0 and state:
        return {"schema_version": 1, "proposal_revision_count": state.get("proposal_revision_count", 0),
                "evidence_catalog": state.get("evidence_catalog", []),
                "claim_evidence": state.get("claim_evidence", []),
                "evidence_warnings": state.get("evidence_warnings", [])}
    return {}


class SessionGraph:
    def __init__(self, graph):
        self._graph = graph

    def __getattr__(self, name):
        if name in {"ainvoke", "astream", "astream_events", "aupdate_state", "bulk_update_state", "abulk_update_state"}:
            raise NotImplementedError("SessionGraph currently supports synchronous execution only.")
        return getattr(self._graph, name)

    @contextmanager
    def session(self, config, expected_checkpoint=_UNSET):
        sid = str(config.get("configurable", {}).get("thread_id") or "")
        with session_lock(sid):
            if expected_checkpoint is not _UNSET:
                current = checkpoint_id(self._graph.get_state(config))
                if current != expected_checkpoint:
                    raise StaleSessionError("This session changed in another page or process. Reload it before submitting again.")
            yield

    def get_state(self, config, **kwargs):
        snapshot = self._graph.get_state(config, **kwargs)
        changes = migration_patch(snapshot.values)
        if changes:
            # Migrate the view only. Writing a checkpoint while loading could
            # discard a failed task's pending writes and change its retry ID.
            # The next normal state write persists the new schema.
            return snapshot._replace(values={**snapshot.values, **changes})
        return snapshot

    def update_state(self, config, values, **kwargs):
        with self.session(config):
            snapshot = self._graph.get_state(config)
            changes = migration_patch(snapshot.values)
            return self._graph.update_state(config, {**changes, **values, "schema_version": STATE_VERSION}, **kwargs)

    def submit(self, config, values, expected_checkpoint, **kwargs):
        """Commit a human answer and run under one lock and version check."""
        with self.session(config, expected_checkpoint):
            if values:
                self.update_state(config, values)
            yield from self.stream(None, config, **kwargs)

    def invoke(self, input, config, **kwargs):
        with self.session(config):
            self.get_state(config)
            if input is not None:
                input = {**input, "schema_version": STATE_VERSION,
                         "session_id": config["configurable"]["thread_id"]}
            return self._graph.invoke(input, config, **kwargs)

    def stream(self, input, config, **kwargs):
        with self.session(config):
            self.get_state(config)
            if input is not None:
                input = {**input, "schema_version": STATE_VERSION,
                         "session_id": config["configurable"]["thread_id"]}
            yield from self._graph.stream(input, config, **kwargs)

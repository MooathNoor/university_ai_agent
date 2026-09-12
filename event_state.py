"""Persistent event and pending-action state for the University AI Agent.

This module is deliberately independent from Moodle and Telegram. It stores:
- events the agent has observed (new assignment, quiz, attendance opening...)
- future actions the student asked the agent to remember

Phase 3 also makes the store safe to *share* between the Telegram process and
monitor process. Each public read refreshes changed data from disk, while each
mutation acquires a tiny cross-process lock, reloads the newest state, writes to
an atomic temporary file, then replaces the real JSON file.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional


DEFAULT_EVENT_STATE_FILE = "agent_event_state.json"
LOCK_WAIT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05
STALE_LOCK_SECONDS = 30.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


@dataclass
class AgentEvent:
    id: str
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    acknowledged: bool = False


@dataclass
class PendingAction:
    id: str
    trigger_type: str
    filters: Dict[str, Any] = field(default_factory=dict)
    requested_action: str = "notify"
    notify: bool = True
    status: str = "active"
    created_at: str = field(default_factory=_utc_now)
    last_triggered_event_id: Optional[str] = None
    original_request: str = ""


class EventState:
    """Persistent state with structural matching and cross-process refresh."""

    def __init__(self, path: Optional[str] = None):
        self.path = (
            path
            or os.environ.get("AGENT_EVENT_STATE_FILE")
            or DEFAULT_EVENT_STATE_FILE
        )
        self._lock = threading.RLock()
        self._last_loaded_mtime_ns: Optional[int] = None
        self.events: List[Dict[str, Any]] = []
        self.pending_actions: List[Dict[str, Any]] = []
        self._load(force=True)

    @property
    def _lock_path(self) -> str:
        return f"{self.path}.lock"

    def _file_mtime_ns(self) -> Optional[int]:
        if not self.path:
            return None
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def _load(self, force: bool = False) -> None:
        """Load state if the backing file changed.

        A Telegram process may stay alive while monitor.py writes a new event.
        Refreshing by mtime lets that already-running Telegram process observe
        the monitor's changes on its next state access.
        """
        if not self.path:
            return

        mtime_ns = self._file_mtime_ns()
        if not force and mtime_ns == self._last_loaded_mtime_ns:
            return

        if mtime_ns is None:
            if force:
                self.events = []
                self.pending_actions = []
            self._last_loaded_mtime_ns = None
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return

            self.events = [
                x for x in data.get("events", [])
                if isinstance(x, dict)
            ]
            self.pending_actions = [
                x for x in data.get("pending_actions", [])
                if isinstance(x, dict)
            ]
            self._last_loaded_mtime_ns = mtime_ns
        except (json.JSONDecodeError, OSError):
            # A transient read failure must not stop the agent. The current
            # in-memory state is kept and the next access will try again.
            return

    @contextmanager
    def _cross_process_lock(self):
        """Small lock-file guard for writes from monitor + Telegram processes."""
        if not self.path:
            yield
            return

        lock_path = self._lock_path
        directory = os.path.dirname(os.path.abspath(lock_path))
        if directory:
            os.makedirs(directory, exist_ok=True)

        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        acquired = False

        while time.monotonic() < deadline:
            try:
                fd = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                try:
                    os.write(
                        fd,
                        f"{os.getpid()}|{time.time()}".encode("utf-8"),
                    )
                finally:
                    os.close(fd)
                acquired = True
                break
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(lock_path)
                    if age > STALE_LOCK_SECONDS:
                        os.remove(lock_path)
                        continue
                except OSError:
                    pass
                time.sleep(LOCK_POLL_SECONDS)

        if not acquired:
            raise TimeoutError(
                f"Could not acquire EventState lock: {lock_path}"
            )

        try:
            yield
        finally:
            try:
                os.remove(lock_path)
            except OSError:
                pass

    def _save_unlocked(self) -> None:
        if not self.path:
            return

        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)

        tmp = (
            f"{self.path}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        data = {
            "version": 2,
            "events": self.events[-200:],
            "pending_actions": self.pending_actions[-200:],
        }

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

        os.replace(tmp, self.path)
        self._last_loaded_mtime_ns = self._file_mtime_ns()

    def _mutate(self, callback):
        """Run one mutation against the newest state on disk."""
        with self._lock:
            with self._cross_process_lock():
                self._load(force=True)
                result = callback()
                self.events = self.events[-200:]
                self.pending_actions = self.pending_actions[-200:]
                self._save_unlocked()
                return result

    def reset(self) -> None:
        """Clear runtime event/action state. Intended for tests/admin use."""
        def operation():
            self.events = []
            self.pending_actions = []

        self._mutate(operation)

    def add_pending_action(
        self,
        trigger_type: str,
        filters: Optional[Dict[str, Any]] = None,
        requested_action: str = "notify",
        notify: bool = True,
        original_request: str = "",
    ) -> Dict[str, Any]:
        trigger_type = _norm(trigger_type).replace(" ", "_")
        if not trigger_type:
            raise ValueError("trigger_type is required")

        clean_filters = {
            str(k): v
            for k, v in (filters or {}).items()
            if v not in (None, "", [], {})
        }

        pending = PendingAction(
            id=f"pa_{uuid.uuid4().hex[:12]}",
            trigger_type=trigger_type,
            filters=clean_filters,
            requested_action=(
                _norm(requested_action).replace(" ", "_") or "notify"
            ),
            notify=bool(notify),
            original_request=str(original_request or "").strip(),
        )
        item = asdict(pending)

        def operation():
            self.pending_actions.append(item)
            return dict(item)

        return self._mutate(operation)

    @staticmethod
    def _filter_matches(
        payload: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> bool:
        for key, expected in filters.items():
            actual = payload.get(key)

            if key in {"course", "course_name", "course_ref"}:
                a, e = _norm(actual), _norm(expected)
                if not a or not e or (e not in a and a not in e):
                    return False
            elif isinstance(expected, bool):
                if bool(actual) != expected:
                    return False
            else:
                if _norm(actual) != _norm(expected):
                    return False

        return True

    def _matching_actions_current(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        matches = []
        normalized_type = _norm(event_type).replace(" ", "_")

        for action in self.pending_actions:
            if action.get("status") != "active":
                continue
            if (
                _norm(action.get("trigger_type")).replace(" ", "_")
                != normalized_type
            ):
                continue
            if self._filter_matches(
                payload,
                action.get("filters") or {},
            ):
                matches.append(dict(action))

        return matches

    def matching_actions(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            self._load()
            return self._matching_actions_current(
                event_type,
                payload or {},
            )

    def record_event(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event_type = _norm(event_type).replace(" ", "_")
        if not event_type:
            raise ValueError("event_type is required")

        event = AgentEvent(
            id=f"ev_{uuid.uuid4().hex[:12]}",
            type=event_type,
            payload=dict(payload or {}),
        )
        item = asdict(event)

        def operation():
            self.events.append(item)
            matches = self._matching_actions_current(
                event_type,
                item["payload"],
            )
            match_ids = {match.get("id") for match in matches}
            for action in self.pending_actions:
                if action.get("id") in match_ids:
                    action["last_triggered_event_id"] = item["id"]
            return {
                "event": dict(item),
                "matching_actions": matches,
            }

        return self._mutate(operation)

    def acknowledge_event(self, event_id: str) -> bool:
        def operation():
            for event in self.events:
                if event.get("id") == event_id:
                    event["acknowledged"] = True
                    return True
            return False

        return self._mutate(operation)

    def complete_pending_action(self, action_id: str) -> bool:
        def operation():
            for action in self.pending_actions:
                if action.get("id") == action_id:
                    action["status"] = "completed"
                    return True
            return False

        return self._mutate(operation)

    def snapshot(
        self,
        max_events: int = 20,
        max_actions: int = 20,
    ) -> Dict[str, Any]:
        with self._lock:
            self._load()
            events = [
                dict(x)
                for x in self.events[-max_events:]
            ]
            actions = [
                dict(x)
                for x in self.pending_actions
                if x.get("status") == "active"
            ][-max_actions:]

        return {
            "recent_events": events,
            "unacknowledged_events": [
                x for x in events
                if not x.get("acknowledged")
            ],
            "pending_actions": actions,
        }

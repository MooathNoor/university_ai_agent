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
    acknowledged_at: Optional[str] = None
    notification_status: str = "not_sent"
    notification_channel: Optional[str] = None
    notification_type: Optional[str] = None
    notification_sent_at: Optional[str] = None
    reminder_count: int = 0
    reminder_last_status: Optional[str] = None
    reminder_last_attempt_at: Optional[str] = None
    reminder_last_sent_at: Optional[str] = None
    reminder_channel: Optional[str] = None


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

    # Phase 4C persistent authorization state.
    authorization_required: bool = False
    authorized: bool = False
    authorized_at: Optional[str] = None
    authorization_source: Optional[str] = None

    # Presence-sensitive actions require a fresh, event-bound confirmation.
    presence_required: bool = False
    presence_confirmed: bool = False
    presence_confirmed_at: Optional[str] = None
    presence_confirmed_event_id: Optional[str] = None


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

            self.events = []
            for raw in data.get("events", []):
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                item.setdefault("acknowledged", False)
                item.setdefault("acknowledged_at", None)
                # Phase-2/3 files predate delivery tracking.  Their real
                # delivery state cannot be reconstructed honestly.
                item.setdefault("notification_status", "unknown")
                item.setdefault("notification_channel", None)
                item.setdefault("notification_type", None)
                item.setdefault("notification_sent_at", None)
                item.setdefault("reminder_count", 0)
                item.setdefault("reminder_last_status", None)
                item.setdefault("reminder_last_attempt_at", None)
                item.setdefault("reminder_last_sent_at", None)
                item.setdefault("reminder_channel", None)
                self.events.append(item)
            self.pending_actions = []
            for raw in data.get("pending_actions", []):
                if not isinstance(raw, dict):
                    continue

                item = dict(raw)

                # Older state files predate persistent action authorization.
                # Missing values deliberately fail closed.
                item.setdefault("authorization_required", False)
                item.setdefault("authorized", False)
                item.setdefault("authorized_at", None)
                item.setdefault("authorization_source", None)
                item.setdefault("presence_required", False)
                item.setdefault("presence_confirmed", False)
                item.setdefault("presence_confirmed_at", None)
                item.setdefault("presence_confirmed_event_id", None)

                self.pending_actions.append(item)
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
            "version": 5,
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
        *,
        authorization_required: bool = False,
        authorized: bool = False,
        authorization_source: Optional[str] = None,
        presence_required: bool = False,
    ) -> Dict[str, Any]:
        trigger_type = _norm(trigger_type).replace(" ", "_")
        if not trigger_type:
            raise ValueError("trigger_type is required")

        clean_filters = {
            str(k): v
            for k, v in (filters or {}).items()
            if v not in (None, "", [], {})
        }

        normalized_action = (
            _norm(requested_action).replace(" ", "_") or "notify"
        )

        authorization_required = bool(authorization_required)
        authorized = bool(authorized)

        if normalized_action == "notify":
            authorization_required = False
            authorized = False
            authorization_source = None
            presence_required = False

        pending = PendingAction(
            id=f"pa_{uuid.uuid4().hex[:12]}",
            trigger_type=trigger_type,
            filters=clean_filters,
            requested_action=normalized_action,
            notify=bool(notify),
            original_request=str(original_request or "").strip(),
            authorization_required=authorization_required,
            authorized=authorized,
            authorized_at=(
                _utc_now()
                if authorization_required and authorized
                else None
            ),
            authorization_source=(
                str(authorization_source or "").strip() or None
            ),
            presence_required=bool(presence_required),
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
                    event["acknowledged_at"] = _utc_now()
                    return True
            return False

        return self._mutate(operation)

    def acknowledge_latest_unacknowledged(self) -> Optional[Dict[str, Any]]:
        """Acknowledge the newest event the user has not confirmed seeing."""
        def operation():
            for event in reversed(self.events):
                if not event.get("acknowledged"):
                    event["acknowledged"] = True
                    event["acknowledged_at"] = _utc_now()
                    return dict(event)
            return None

        return self._mutate(operation)

    def mark_event_notification(
        self,
        event_id: str,
        status: str,
        channel: Optional[str] = None,
        notification_type: Optional[str] = None,
    ) -> bool:
        """Persist delivery state for one event.

        Delivery and acknowledgement are intentionally separate. Telegram can
        confirm that a message was sent, but it cannot prove the user read it.
        Once an event is recorded as sent, a later retry/failure must not
        downgrade that successful delivery.
        """
        clean_status = _norm(status).replace(" ", "_") or "unknown"

        def operation():
            for event in self.events:
                if event.get("id") != event_id:
                    continue
                already_sent = event.get("notification_status") == "sent"
                if already_sent and clean_status != "sent":
                    return True
                event["notification_status"] = clean_status
                if channel:
                    event["notification_channel"] = str(channel)
                if notification_type:
                    event["notification_type"] = str(notification_type)
                if clean_status == "sent":
                    event["notification_sent_at"] = _utc_now()
                return True
            return False

        return self._mutate(operation)

    def mark_event_reminder(
        self,
        event_id: str,
        status: str,
        channel: Optional[str] = None,
    ) -> bool:
        """Persist one reminder attempt for an existing event.

        Reminder delivery is tracked independently from the original
        notification.  Failed attempts do not consume the reminder quota; only
        successfully sent reminders increment ``reminder_count``.
        """
        clean_status = _norm(status).replace(" ", "_") or "unknown"

        def operation():
            for event in self.events:
                if event.get("id") != event_id:
                    continue
                now = _utc_now()
                event["reminder_last_status"] = clean_status
                event["reminder_last_attempt_at"] = now
                if channel:
                    event["reminder_channel"] = str(channel)
                if clean_status == "sent":
                    event["reminder_count"] = int(event.get("reminder_count") or 0) + 1
                    event["reminder_last_sent_at"] = now
                return True
            return False

        return self._mutate(operation)

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def due_reminder_events(
        self,
        policies: Dict[str, Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Return important delivered events whose reminder window is due.

        Eligibility is deliberately strict:
        - the original notification must have been confirmed as sent;
        - the user must not have acknowledged the event;
        - the event type must have an explicit reminder policy;
        - the successful reminder quota must not be exhausted.
        """
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current = current.astimezone(timezone.utc)

        with self._lock:
            self._load()
            due = []
            for event in self.events:
                if event.get("acknowledged"):
                    continue
                if event.get("notification_status") != "sent":
                    continue

                event_type = str(event.get("type") or "")
                policy = policies.get(event_type)
                if not isinstance(policy, dict):
                    continue

                reminder_count = int(event.get("reminder_count") or 0)
                max_reminders = max(0, int(policy.get("max_reminders", 0) or 0))
                if reminder_count >= max_reminders:
                    continue

                if reminder_count == 0:
                    anchor = self._parse_timestamp(event.get("notification_sent_at"))
                    wait_minutes = float(policy.get("first_after_minutes", 0) or 0)
                else:
                    anchor = self._parse_timestamp(event.get("reminder_last_sent_at"))
                    wait_minutes = float(policy.get("repeat_after_minutes", 0) or 0)

                if anchor is None:
                    continue
                elapsed_seconds = (current - anchor).total_seconds()
                if elapsed_seconds < max(0.0, wait_minutes * 60.0):
                    continue

                item = dict(event)
                item["reminder_policy"] = dict(policy)
                due.append(item)

            return due

    def set_pending_action_authorization(
        self,
        action_id: str,
        authorized: bool,
        *,
        source: Optional[str] = None,
    ) -> bool:
        """Persist or revoke authorization for one pending mutation."""

        def operation():
            for action in self.pending_actions:
                if action.get("id") != action_id:
                    continue

                value = bool(authorized)
                action["authorized"] = value
                action["authorized_at"] = _utc_now() if value else None
                action["authorization_source"] = (
                    (str(source or "").strip() or None)
                    if value
                    else None
                )
                return True

            return False

        return self._mutate(operation)

    def set_pending_action_presence_confirmation(
        self,
        action_id: str,
        confirmed: bool,
        *,
        event_id: Optional[str] = None,
    ) -> bool:
        """Persist presence confirmation for exactly one observed event."""

        if confirmed and not str(event_id or "").strip():
            return False

        def operation():
            for action in self.pending_actions:
                if action.get("id") != action_id:
                    continue

                value = bool(confirmed)
                action["presence_confirmed"] = value
                action["presence_confirmed_at"] = (
                    _utc_now() if value else None
                )
                action["presence_confirmed_event_id"] = (
                    str(event_id).strip()
                    if value
                    else None
                )
                return True

            return False

        return self._mutate(operation)

    def clear_stale_presence_confirmations(
        self,
        current_event_id: Optional[str],
    ) -> int:
        """Clear confirmations that belong to another event."""

        current_event_id = str(current_event_id or "").strip()
        cleared = 0

        def operation():
            nonlocal cleared

            for action in self.pending_actions:
                confirmed_event_id = str(
                    action.get("presence_confirmed_event_id") or ""
                ).strip()

                if (
                    action.get("presence_confirmed") is True
                    and confirmed_event_id
                    and confirmed_event_id != current_event_id
                ):
                    action["presence_confirmed"] = False
                    action["presence_confirmed_at"] = None
                    action["presence_confirmed_event_id"] = None
                    cleared += 1

            return cleared

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

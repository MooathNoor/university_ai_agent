import json
import os
import tempfile

from agent_core import AgentDecision
from event_state import EventState
import main
import monitor


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


assertions = 0


def ok(condition, message):
    global assertions
    check(condition, message)
    assertions += 1


# ============================================================
# 1. Notification watch: no mutation authorization state
# ============================================================

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "state.json")
    state = EventState(path)

    notify_action = state.add_pending_action(
        trigger_type="quiz_added",
        filters={},
        requested_action="notify",
        notify=True,
        original_request="بلغني لو نزل كويز",
        authorization_required=True,
        authorized=True,
        authorization_source="should_be_cleared",
        presence_required=True,
    )

    ok(notify_action["requested_action"] == "notify", "notify action stays notify")
    ok(not notify_action["authorization_required"], "notify action does not require mutation authorization")
    ok(not notify_action["authorized"], "notify action does not store mutation authorization")
    ok(not notify_action["presence_required"], "notify action never requires physical presence")


# ============================================================
# 2. State-changing watch persists explicit prospective auth
# ============================================================

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "state.json")
    state = EventState(path)

    action = state.add_pending_action(
        trigger_type="attendance_opened",
        filters={"course_id": 1695},
        requested_action="register_attendance",
        notify=True,
        original_request="اول ما يفتح الحضور سجلني حاضر",
        authorization_required=True,
        authorized=True,
        authorization_source="explicit_user_request",
        presence_required=True,
    )

    ok(action["authorization_required"] is True, "mutation records authorization requirement")
    ok(action["authorized"] is True, "explicit future mutation request stores authorization")
    ok(bool(action["authorized_at"]), "authorized mutation stores timestamp")
    ok(action["authorization_source"] == "explicit_user_request", "authorization source is persisted")
    ok(action["presence_required"] is True, "attendance mutation requires physical presence")
    ok(action["presence_confirmed"] is False, "presence is never inferred in advance")
    ok(action["presence_confirmed_event_id"] is None, "advance request has no presence event id")


# ============================================================
# 3. Presence confirmation requires a concrete event id
# ============================================================

    action_id = action["id"]

    ok(
        state.set_pending_action_presence_confirmation(
            action_id,
            True,
            event_id=None,
        ) is False,
        "presence confirmation without event id is rejected",
    )

    event = state.record_event(
        "attendance_opened",
        {"course_id": 1695, "status": "Open"},
    )["event"]

    event_id = event["id"]

    ok(
        state.set_pending_action_presence_confirmation(
            action_id,
            True,
            event_id=event_id,
        ),
        "presence can be confirmed for one concrete event",
    )

    saved = next(
        item
        for item in state.snapshot()["pending_actions"]
        if item["id"] == action_id
    )

    ok(saved["presence_confirmed"] is True, "presence confirmation persists")
    ok(saved["presence_confirmed_event_id"] == event_id, "presence confirmation is bound to exact event")
    ok(bool(saved["presence_confirmed_at"]), "presence confirmation stores timestamp")


# ============================================================
# 4. Another event invalidates old presence
# ============================================================

    second = state.record_event(
        "attendance_opened",
        {"course_id": 1695, "status": "Open"},
    )["event"]

    cleared = state.clear_stale_presence_confirmations(second["id"])
    ok(cleared == 1, "stale presence confirmation is cleared for a new event")

    saved = next(
        item
        for item in state.snapshot()["pending_actions"]
        if item["id"] == action_id
    )
    ok(saved["presence_confirmed"] is False, "old presence confirmation is no longer active")
    ok(saved["presence_confirmed_event_id"] is None, "old event binding is removed")


# ============================================================
# 5. Authorization can be explicitly revoked/restored
# ============================================================

    ok(
        state.set_pending_action_authorization(action_id, False),
        "authorization can be revoked",
    )
    saved = next(
        item
        for item in state.snapshot()["pending_actions"]
        if item["id"] == action_id
    )
    ok(saved["authorized"] is False, "revoked authorization persists")
    ok(saved["authorized_at"] is None, "revocation clears authorization timestamp")

    ok(
        state.set_pending_action_authorization(
            action_id,
            True,
            source="explicit_user_confirmation",
        ),
        "authorization can be restored explicitly",
    )
    saved = next(
        item
        for item in state.snapshot()["pending_actions"]
        if item["id"] == action_id
    )
    ok(saved["authorized"] is True, "restored authorization persists")
    ok(saved["authorization_source"] == "explicit_user_confirmation", "restored authorization source persists")


# ============================================================
# 6. Backward compatibility fails closed
# ============================================================

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "legacy.json")
    legacy = {
        "version": 4,
        "events": [],
        "pending_actions": [
            {
                "id": "pa_legacy",
                "trigger_type": "attendance_opened",
                "filters": {"course_id": 1695},
                "requested_action": "register_attendance",
                "notify": True,
                "status": "active",
                "created_at": "2026-09-13T00:00:00+00:00",
                "last_triggered_event_id": None,
                "original_request": "legacy request",
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(legacy, f)

    state = EventState(path)
    old = state.snapshot()["pending_actions"][0]

    ok(old["authorized"] is False, "legacy mutation defaults to unauthorized")
    ok(old["presence_confirmed"] is False, "legacy mutation defaults to no presence confirmation")
    ok(old["presence_confirmed_event_id"] is None, "legacy state has no invented event binding")


# ============================================================
# 7. Main policy is capability-based
# ============================================================

notify_decision = AgentDecision(
    action="watch",
    requested_action="notify",
    trigger_type="quiz_added",
)
notify_policy = main._pending_action_policy(notify_decision)

ok(notify_policy["authorization_required"] is False, "main policy treats notify as read-only")
ok(notify_policy["presence_required"] is False, "notify policy does not require presence")

attendance_decision = AgentDecision(
    action="watch",
    requested_action="register_attendance",
    trigger_type="attendance_opened",
)
attendance_policy = main._pending_action_policy(attendance_decision)

ok(attendance_policy["authorization_required"] is True, "attendance mutation requires authorization")
ok(attendance_policy["authorized"] is True, "explicit mutation watch is prospectively authorized")
ok(attendance_policy["presence_required"] is True, "attendance action is capability-marked presence-sensitive")


# ============================================================
# 8. Monitor accepts presence only for the exact event
# ============================================================

old_runner = monitor._verified_action_runner
old_state = monitor._event_state

try:
    class FakeResult:
        def __init__(self, status):
            self.status = status
            self.execution_status = "executed" if status == "success" else "unknown"
            self.verification_status = "verified" if status == "success" else "not_run"

        def to_dict(self):
            return {
                "action_type": "presence_demo",
                "status": self.status,
                "execution_status": self.execution_status,
                "verification_status": self.verification_status,
                "message": self.status,
                "evidence": {},
                "execution_result": {},
                "verification_result": {},
            }

    class FakeRunner:
        def __init__(self):
            self.calls = []

        def run(self, action_type, payload, *, authorized=False, presence_confirmed=False):
            self.calls.append({
                "action_type": action_type,
                "authorized": authorized,
                "presence_confirmed": presence_confirmed,
                "payload": payload,
            })
            return FakeResult("success" if authorized and presence_confirmed else "blocked")

    class FakeState:
        def __init__(self):
            self.completed = []

        def complete_pending_action(self, action_id):
            self.completed.append(action_id)
            return True

    runner = FakeRunner()
    fake_state = FakeState()
    monitor._verified_action_runner = runner
    monitor._event_state = fake_state

    pending = {
        "id": "pa_presence",
        "requested_action": "presence_demo",
        "authorized": True,
        "presence_required": True,
        "presence_confirmed": True,
        "presence_confirmed_event_id": "ev_old",
        "original_request": "test",
    }

    event_result = {
        "event": {
            "id": "ev_current",
            "type": "attendance_opened",
            "payload": {"course_id": 1695},
        },
        "matching_actions": [pending],
    }

    results = monitor.process_matching_pending_actions(event_result)

    ok(runner.calls[0]["presence_confirmed"] is False, "monitor rejects presence bound to another event")
    ok(results[0]["status"] == "blocked", "stale presence cannot produce success")
    ok(fake_state.completed == [], "stale presence never completes pending action")

    pending["presence_confirmed_event_id"] = "ev_current"

    results = monitor.process_matching_pending_actions(event_result)

    ok(runner.calls[-1]["presence_confirmed"] is True, "monitor accepts presence for exact event")
    ok(results[0]["status"] == "success", "exact event-bound presence can reach verified success")
    ok(fake_state.completed == ["pa_presence"], "verified exact-event action completes once")

finally:
    monitor._verified_action_runner = old_runner
    monitor._event_state = old_state


print()
print(f"PASS: {assertions} Phase 4C persistent-authorization assertions")

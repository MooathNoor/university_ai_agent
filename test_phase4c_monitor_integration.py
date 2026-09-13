from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

from verified_actions import VerifiedActionRunner


ROOT = Path(__file__).resolve().parent


def load_monitor_with_stubs():
    tools_stub = types.ModuleType("tools")
    tools_stub.get_courses = lambda: []
    tools_stub.get_my_courses = lambda: []
    tools_stub.get_assignments = lambda: []
    tools_stub.get_quizzes = lambda: []
    tools_stub.get_attendance = lambda course: {}

    notification_stub = types.ModuleType("notification")
    notification_stub.send_notification = lambda *args, **kwargs: True

    old_tools = sys.modules.get("tools")
    old_notification = sys.modules.get("notification")
    sys.modules["tools"] = tools_stub
    sys.modules["notification"] = notification_stub

    try:
        spec = importlib.util.spec_from_file_location(
            "phase4c_monitor_under_test",
            ROOT / "monitor.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_tools is None:
            sys.modules.pop("tools", None)
        else:
            sys.modules["tools"] = old_tools

        if old_notification is None:
            sys.modules.pop("notification", None)
        else:
            sys.modules["notification"] = old_notification


monitor = load_monitor_with_stubs()


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


assertions = 0


def ok(condition, message):
    global assertions
    check(condition, message)
    assertions += 1


class FakeEventState:
    def __init__(self):
        self.completed = []

    def complete_pending_action(self, action_id):
        self.completed.append(action_id)
        return True


original_runner = monitor._verified_action_runner
original_state = monitor._event_state

try:
    monitor._verified_action_runner = VerifiedActionRunner()
    fake_state = FakeEventState()
    monitor._event_state = fake_state

    # ------------------------------------------------------------
    # 1. notify stays read-only and never enters action runner.
    # ------------------------------------------------------------
    notify_event = {
        "event": {
            "id": "ev_notify",
            "type": "quiz_added",
            "payload": {"course_id": 1194, "name": "Quiz 1"},
        },
        "matching_actions": [
            {
                "id": "pa_notify",
                "requested_action": "notify",
                "notify": True,
                "original_request": "بلغني لو نزل كويز",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(notify_event)
    ok(results == [], "notify-only pending action bypasses state-changing runner")
    ok(fake_state.completed == [], "notify-only pending action is not completed by execution gate")

    # ------------------------------------------------------------
    # 2. Unregistered action fails closed.
    # ------------------------------------------------------------
    unregistered_event = {
        "event": {
            "id": "ev_unregistered",
            "type": "attendance_opened",
            "payload": {"course_id": 1695, "status": "Open"},
        },
        "matching_actions": [
            {
                "id": "pa_unregistered",
                "requested_action": "register_attendance",
                "authorized": True,
                "presence_confirmed": True,
                "original_request": "سجلني حاضر",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(unregistered_event)
    ok(len(results) == 1, "unregistered state-changing action produces one controlled result")
    ok(results[0]["status"] == "blocked", "unregistered state-changing action is blocked")
    ok(fake_state.completed == [], "blocked unregistered action stays pending")

    # ------------------------------------------------------------
    # 3. Registered but unauthorized action is blocked before mutation.
    # ------------------------------------------------------------
    calls = {"execute": 0, "verify": 0}

    def executor(payload):
        calls["execute"] += 1
        return {"status": "executed"}

    def verifier(payload):
        calls["verify"] += 1
        return {"status": "verified"}

    monitor.register_verified_action(
        "safe_demo",
        executor,
        verifier,
        requires_authorization=True,
    )

    unauthorized_event = {
        "event": {
            "id": "ev_unauthorized",
            "type": "assignment_added",
            "payload": {"course_id": 1194, "name": "A1"},
        },
        "matching_actions": [
            {
                "id": "pa_unauthorized",
                "requested_action": "safe_demo",
                "authorized": False,
                "original_request": "نفذ الإجراء",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(unauthorized_event)
    ok(results[0]["status"] == "blocked", "missing authorization blocks registered action")
    ok(calls["execute"] == 0, "authorization guard runs before executor")
    ok(calls["verify"] == 0, "authorization guard runs before verifier")

    # ------------------------------------------------------------
    # 4. Authorized execution must verify before completion.
    # ------------------------------------------------------------
    captured = {}

    def verified_executor(payload):
        captured["execute_payload"] = dict(payload)
        return {"status": "executed", "request_id": "req-123"}

    def verified_verifier(payload):
        captured["verify_payload"] = dict(payload)
        return {
            "status": "verified",
            "message": "Fresh external state confirms the change.",
            "evidence": {"source": "fresh_read", "state": "expected"},
        }

    monitor.register_verified_action(
        "verified_demo",
        verified_executor,
        verified_verifier,
        requires_authorization=True,
    )

    success_event = {
        "event": {
            "id": "ev_success",
            "type": "assignment_added",
            "payload": {
                "course_id": 1194,
                "course_name": "Cloud Computing",
                "name": "A2",
            },
        },
        "matching_actions": [
            {
                "id": "pa_success",
                "requested_action": "verified_demo",
                "authorized": True,
                "original_request": "نفذ الإجراء لما ينزل الواجب",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(success_event)
    result = results[0]
    ok(result["status"] == "success", "verified mutation becomes success")
    ok(result["execution_status"] == "executed", "execution state is preserved")
    ok(result["verification_status"] == "verified", "fresh verification state is preserved")
    ok("pa_success" in fake_state.completed, "pending action completes only after verified success")
    ok(captured["execute_payload"]["event_id"] == "ev_success", "executor receives grounded event id")
    ok(captured["execute_payload"]["course_id"] == 1194, "executor receives grounded Moodle payload")
    ok(captured["execute_payload"]["pending_action_id"] == "pa_success", "executor receives pending action id")
    ok(
        captured["verify_payload"]["_execution_result"]["request_id"] == "req-123",
        "verifier receives execution result for independent follow-up read",
    )

    # ------------------------------------------------------------
    # 5. Unknown verification never completes the action.
    # ------------------------------------------------------------
    monitor.register_verified_action(
        "unknown_demo",
        lambda payload: {"status": "executed"},
        lambda payload: {"status": "unknown", "message": "Fresh state unavailable."},
        requires_authorization=True,
    )
    before = list(fake_state.completed)
    unknown_event = {
        "event": {"id": "ev_unknown", "type": "quiz_added", "payload": {"course_id": 1499}},
        "matching_actions": [
            {
                "id": "pa_unknown",
                "requested_action": "unknown_demo",
                "authorized": True,
                "original_request": "نفذ",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(unknown_event)
    ok(results[0]["status"] == "unknown", "inconclusive verification stays unknown")
    ok(fake_state.completed == before, "unverified action is never marked completed")

    # ------------------------------------------------------------
    # 6. Presence-sensitive action fails closed without presence.
    # ------------------------------------------------------------
    presence_calls = {"execute": 0}

    def presence_executor(payload):
        presence_calls["execute"] += 1
        return {"status": "executed"}

    monitor.register_verified_action(
        "presence_demo",
        presence_executor,
        lambda payload: {"status": "verified"},
        requires_authorization=True,
        requires_presence=True,
    )
    presence_event = {
        "event": {"id": "ev_presence", "type": "attendance_opened", "payload": {"course_id": 1695}},
        "matching_actions": [
            {
                "id": "pa_presence",
                "requested_action": "presence_demo",
                "authorized": True,
                "presence_confirmed": False,
                "original_request": "سجلني",
            }
        ],
    }
    results = monitor.process_matching_pending_actions(presence_event)
    ok(results[0]["status"] == "blocked", "presence-sensitive action blocks without presence confirmation")
    ok(presence_calls["execute"] == 0, "presence guard blocks before mutation")

    # ------------------------------------------------------------
    # 7. Human-readable result note distinguishes outcomes.
    # ------------------------------------------------------------
    note = monitor.verified_action_note([
        {"action_type": "a", "status": "success", "message": "ok"},
        {"action_type": "b", "status": "blocked", "message": "no auth"},
        {"action_type": "c", "status": "unknown", "message": "no evidence"},
    ])
    ok("verified" in note, "success note explicitly says verified")
    ok("blocked" in note, "blocked outcome appears in notification note")
    ok("unverified" in note, "unknown outcome is never phrased as success")

finally:
    monitor._verified_action_runner = original_runner
    monitor._event_state = original_state


print()
print(f"PASS: {assertions} Phase 4C monitor-integration assertions")

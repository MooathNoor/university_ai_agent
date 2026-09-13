"""Phase 4 foundation tests: delivery state, acknowledgement, and missed events."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import types

from event_state import EventState

ROOT = Path(__file__).resolve().parent


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def load_monitor(send_result=True):
    tools_stub = types.ModuleType("tools")
    tools_stub.get_courses = lambda: []
    tools_stub.get_my_courses = lambda: []
    tools_stub.get_assignments = lambda: []
    tools_stub.get_quizzes = lambda: []
    tools_stub.get_attendance = lambda course: {}

    notification_stub = types.ModuleType("notification")
    notification_stub.send_notification = lambda *args, **kwargs: send_result

    old_tools = sys.modules.get("tools")
    old_notification = sys.modules.get("notification")
    sys.modules["tools"] = tools_stub
    sys.modules["notification"] = notification_stub
    try:
        spec = importlib.util.spec_from_file_location(
            f"phase4_monitor_{send_result}",
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


def run():
    assertions = 0
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "events.json")
        state = EventState(path)
        state.reset()

        one = state.record_event("quiz_added", {"course_id": 1499, "name": "Quiz 4"})
        two = state.record_event("assignment_added", {"course_id": 1194, "name": "A7"})
        assertions += 2
        check(one["event"]["notification_status"] == "not_sent", "event fabricated delivery")
        check(two["event"]["acknowledged"] is False, "event fabricated acknowledgement")

        state.mark_event_notification(
            one["event"]["id"], "sent", channel="telegram", notification_type="NEW_QUIZ"
        )
        snap = state.snapshot(max_events=10)
        quiz = next(x for x in snap["recent_events"] if x["id"] == one["event"]["id"])
        assertions += 3
        check(quiz["notification_status"] == "sent", "sent state not persisted")
        check(quiz["notification_channel"] == "telegram", "channel not persisted")
        check(quiz["acknowledged"] is False, "delivery incorrectly implied reading")

        acknowledged = state.acknowledge_latest_unacknowledged()
        assertions += 2
        check(acknowledged["id"] == two["event"]["id"], "latest unread event not acknowledged first")
        check(len(state.snapshot()["unacknowledged_events"]) == 1, "ack did not remove exactly one unread event")

        # Real monitor action path: a successful delivery must write back to the event.
        monitor = load_monitor(send_result=True)
        monitor._event_state = EventState(str(Path(tmp) / "monitor_success.json"))
        monitor.DEDUP_FILE = str(Path(tmp) / "success_dedup.json")
        monitor.ACTION_LOG_FILE = str(Path(tmp) / "success_actions.log")
        result = monitor.record_agent_event("quiz_added", {"course_id": 1499, "name": "Quiz 5"})
        event_id = result["event"]["id"]
        ok = monitor.execute_action(
            "NEW_QUIZ",
            "Phase 4 delivery test",
            channel="telegram",
            event_result=result,
        )
        saved = next(x for x in monitor._event_state.snapshot()["recent_events"] if x["id"] == event_id)
        assertions += 3
        check(ok is True, "successful notification path returned false")
        check(saved["notification_status"] == "sent", "monitor did not mark event sent")
        check(saved["acknowledged"] is False, "monitor delivery auto-acknowledged event")

        # Failed delivery remains visible and unacknowledged for later retry/reminder logic.
        failed_monitor = load_monitor(send_result=False)
        failed_monitor._event_state = EventState(str(Path(tmp) / "monitor_fail.json"))
        failed_monitor.DEDUP_FILE = str(Path(tmp) / "failed_dedup.json")
        failed_monitor.ACTION_LOG_FILE = str(Path(tmp) / "failed_actions.log")
        failed = failed_monitor.record_agent_event("assignment_added", {"course_id": 1194, "name": "A8"})
        failed_id = failed["event"]["id"]
        ok = failed_monitor.execute_action(
            "NEW_ASSIGNMENT",
            "Phase 4 failed delivery test",
            channel="telegram",
            event_result=failed,
        )
        failed_saved = next(
            x for x in failed_monitor._event_state.snapshot()["recent_events"]
            if x["id"] == failed_id
        )
        assertions += 3
        check(ok is False, "failed notification path returned true")
        check(failed_saved["notification_status"] == "failed", "failed delivery not persisted")
        check(failed_saved["acknowledged"] is False, "failed delivery auto-acknowledged event")

    print(f"PASS: {assertions} Phase 4 notification-state assertions")


if __name__ == "__main__":
    run()

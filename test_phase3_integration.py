"""Phase 3 integration tests: Monitor -> EventState -> Pending Action -> Notify."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import types

from event_state import EventState


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
            "phase3_monitor_under_test",
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


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def test_cross_process_style_refresh(tmpdir):
    path = str(Path(tmpdir) / "shared_event_state.json")
    telegram_state = EventState(path)
    monitor_state = EventState(path)

    telegram_state.reset()
    telegram_state.add_pending_action(
        trigger_type="assignment_added",
        filters={"course_id": 1194},
        requested_action="notify",
        notify=True,
        original_request="اذا نزل واجب جديد بالحوسبة خبرني",
    )

    result = monitor_state.record_event(
        "assignment_added",
        {
            "course_id": 1194,
            "course_name": "CLOUD COMPUTING",
            "name": "New assignment",
        },
    )

    assert_true(
        len(result["matching_actions"]) == 1,
        "monitor-side EventState did not refresh Telegram pending actions",
    )

    telegram_snapshot = telegram_state.snapshot()
    assert_true(
        len(telegram_snapshot["recent_events"]) == 1,
        "Telegram-side EventState did not refresh monitor event",
    )


def test_monitor_handlers(tmpdir):
    monitor = load_monitor_with_stubs()
    state_path = str(Path(tmpdir) / "monitor_event_state.json")
    monitor._event_state = EventState(state_path)
    monitor._event_state.reset()

    monitor._event_state.add_pending_action(
        trigger_type="assignment_added",
        filters={"course_id": 1194},
        requested_action="notify",
        notify=True,
        original_request="لو نزل واجب جديد بالحوسبة بلغني",
    )

    sent = []

    def fake_execute(action_type, message, channel=None):
        sent.append(
            {
                "type": action_type,
                "message": message,
                "channel": channel,
            }
        )
        return True

    monitor.execute_action = fake_execute

    assignment = {
        "id": "assignment-1",
        "course_id": 1194,
        "course": "CLOUD COMPUTING",
        "name": "Cloud Security Assignment",
        "url": "https://example/assignment/1",
        "due": "Tomorrow",
        "submission_status": "No submission",
        "grading_status": "Not graded",
        "time_remaining": "1 day",
    }

    assert_true(
        monitor.handle_new_assignment(assignment),
        "new assignment handler did not execute notification",
    )
    snapshot = monitor._event_state.snapshot()
    assert_true(
        snapshot["recent_events"][-1]["type"] == "assignment_added",
        "new assignment was not persisted as assignment_added",
    )
    assert_true(
        sent[-1]["channel"] == "telegram",
        "matching pending action did not force Telegram",
    )
    assert_true(
        "saved request" in sent[-1]["message"],
        "pending-action match note was not included",
    )

    quiz = {
        "id": "quiz-1",
        "course_id": 1499,
        "course": "ROBOTICS AND AUTONOMOUS SYSTEMS",
        "name": "Quiz 4",
        "url": "https://example/quiz/1",
        "opened": "Now",
        "closed": "Later",
        "attempts_allowed": 1,
        "time_limit": "5 mins",
        "attempt_status": "Not attempted",
    }
    assert_true(
        monitor.handle_new_quiz(quiz),
        "new quiz handler did not execute notification",
    )
    snapshot = monitor._event_state.snapshot()
    assert_true(
        snapshot["recent_events"][-1]["type"] == "quiz_added",
        "new quiz was not persisted as quiz_added",
    )

    opened_changes = [
        {
            "course": "CLOUD COMPUTING",
            "course_id": 1194,
            "type": "status_changed",
            "old": "Closed",
            "new": "Open",
        }
    ]
    assert_true(
        monitor.handle_attendance_changes(opened_changes),
        "attendance-open handler did not notify",
    )
    snapshot = monitor._event_state.snapshot()
    assert_true(
        snapshot["recent_events"][-1]["type"] == "attendance_opened",
        "Closed -> Open was not emitted as attendance_opened",
    )
    assert_true(
        sent[-1]["type"] == "ATTENDANCE_OPENED",
        "attendance-open notification type is wrong",
    )

    percentage_changes = [
        {
            "course": "CLOUD COMPUTING",
            "course_id": 1194,
            "type": "percentage_changed",
            "old": "80%",
            "new": "85%",
        }
    ]
    assert_true(
        monitor.handle_attendance_changes(percentage_changes),
        "attendance-change handler did not notify",
    )
    snapshot = monitor._event_state.snapshot()
    assert_true(
        snapshot["recent_events"][-1]["type"] == "attendance_changed",
        "non-open attendance change got wrong event type",
    )


def test_notification_configuration():
    spec = importlib.util.spec_from_file_location(
        "phase3_notification_under_test",
        ROOT / "notification.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert_true(
        module.get_notification_priority("NEW_ASSIGNMENT") == "HIGH",
        "new assignments must reach Telegram in Phase 3",
    )
    assert_true(
        module.get_notification_priority("NEW_QUIZ") == "HIGH",
        "new quizzes must remain high priority",
    )
    assert_true(
        module.get_notification_priority("ATTENDANCE_OPENED") == "HIGH",
        "attendance-open must be high priority",
    )


def main():
    assertions = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        test_cross_process_style_refresh(tmpdir)
        assertions += 2
        test_monitor_handlers(tmpdir)
        assertions += 10
        test_notification_configuration()
        assertions += 3

    print(f"PASS: {assertions} Phase 3 integration assertions")


if __name__ == "__main__":
    main()

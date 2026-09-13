import os
import tempfile
from datetime import datetime, timedelta, timezone

from event_state import EventState

import sys
import types

# Isolate this reminder-policy test from Moodle.  The test does not need real
# LMS access, and the artifact bundle used here does not include lms_client.py.
fake_tools = types.ModuleType("tools")
fake_tools.get_my_courses = lambda: []
fake_tools.get_assignments = lambda *args, **kwargs: []
fake_tools.get_quizzes = lambda *args, **kwargs: []
fake_tools.get_attendance = lambda *args, **kwargs: {}
fake_tools.get_courses = lambda: []
sys.modules["tools"] = fake_tools

import monitor


passed = 0


def check(condition, message):
    global passed
    if not condition:
        raise AssertionError(message)
    passed += 1


with tempfile.TemporaryDirectory() as tmp:
    state_path = os.path.join(tmp, "event_state.json")
    state = EventState(state_path)

    result = state.record_event(
        "quiz_added",
        {
            "course_id": 1499,
            "course_name": "Robotics",
            "name": "Reminder Test Quiz",
        },
    )
    event_id = result["event"]["id"]

    state.mark_event_notification(
        event_id,
        "sent",
        channel="telegram",
        notification_type="NEW_QUIZ",
    )
    snap = state.snapshot()
    event = snap["recent_events"][-1]
    sent_at = datetime.fromisoformat(event["notification_sent_at"])

    early = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=sent_at + timedelta(minutes=29),
    )
    check(not early, "quiz reminder fired before first-after window")

    due = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=sent_at + timedelta(minutes=31),
    )
    check(len(due) == 1, "quiz reminder was not due after first-after window")
    check(due[0]["id"] == event_id, "wrong event selected for reminder")

    state.mark_event_reminder(event_id, "failed", channel="telegram")
    event = state.snapshot()["recent_events"][-1]
    check(event["reminder_count"] == 0, "failed reminder consumed reminder quota")
    check(event["reminder_last_status"] == "failed", "failed reminder status not persisted")

    state.mark_event_reminder(event_id, "sent", channel="telegram")
    event = state.snapshot()["recent_events"][-1]
    check(event["reminder_count"] == 1, "successful reminder did not increment count")
    check(event["reminder_last_sent_at"], "successful reminder missing sent timestamp")

    reminder_sent_at = datetime.fromisoformat(event["reminder_last_sent_at"])
    repeat_early = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=reminder_sent_at + timedelta(minutes=119),
    )
    check(not repeat_early, "repeat quiz reminder fired too early")

    repeat_due = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=reminder_sent_at + timedelta(minutes=121),
    )
    check(len(repeat_due) == 1, "repeat quiz reminder was not due")

    state.mark_event_reminder(event_id, "sent", channel="telegram")
    event = state.snapshot()["recent_events"][-1]
    check(event["reminder_count"] == 2, "second successful reminder count incorrect")

    after_quota = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=datetime.now(timezone.utc) + timedelta(days=2),
    )
    check(not after_quota, "event remained reminder-eligible after quota exhausted")

    result2 = state.record_event(
        "assignment_added",
        {"course_id": 1194, "course_name": "Cloud", "name": "Ack Test"},
    )
    event2 = result2["event"]
    state.mark_event_notification(event2["id"], "sent", channel="telegram")
    state.acknowledge_event(event2["id"])
    event2_now = state.snapshot()["recent_events"][-1]
    anchor = datetime.fromisoformat(event2_now["notification_sent_at"])
    ack_due = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=anchor + timedelta(days=2),
    )
    check(all(x["id"] != event2["id"] for x in ack_due), "acknowledged event was reminded")

    result3 = state.record_event(
        "quiz_added",
        {"name": "Unknown Delivery"},
    )
    event3 = result3["event"]
    # Do not mark sent; reminder eligibility must fail closed.
    unknown_due = state.due_reminder_events(
        monitor.REMINDER_POLICIES,
        now=datetime.now(timezone.utc) + timedelta(days=2),
    )
    check(all(x["id"] != event3["id"] for x in unknown_due), "unsent event became reminder-eligible")

# Integration-like test for monitor reminder sender without real Telegram.
with tempfile.TemporaryDirectory() as tmp:
    original_state = monitor._event_state
    original_send = monitor.send_notification
    try:
        monitor._event_state = EventState(os.path.join(tmp, "state.json"))
        r = monitor._event_state.record_event(
            "attendance_opened",
            {"course_name": "Numerical Analysis", "name": "Attendance"},
        )
        eid = r["event"]["id"]
        monitor._event_state.mark_event_notification(eid, "sent", channel="telegram")
        e = monitor._event_state.snapshot()["recent_events"][-1]
        anchor = datetime.fromisoformat(e["notification_sent_at"])

        calls = []
        monitor.send_notification = lambda notification_type, message, channel="auto": calls.append(
            (notification_type, message, channel)
        ) or True

        count = monitor.process_due_event_reminders(
            now=anchor + timedelta(minutes=11)
        )
        check(count == 1, "monitor did not send due attendance reminder")
        check(len(calls) == 1, "monitor reminder sender called wrong number of times")
        check(calls[0][0] == "REMINDER", "monitor used wrong notification type")
        check(calls[0][2] == "telegram", "monitor did not reuse original notification channel")
        check("شفت الإشعار" in calls[0][1], "reminder message lacks acknowledgement instruction")

        after = monitor._event_state.snapshot()["recent_events"][-1]
        check(after["reminder_count"] == 1, "monitor did not persist successful reminder")

        monitor._event_state.acknowledge_event(eid)
        calls.clear()
        count2 = monitor.process_due_event_reminders(
            now=anchor + timedelta(hours=5)
        )
        check(count2 == 0 and not calls, "monitor reminded an acknowledged event")
    finally:
        monitor._event_state = original_state
        monitor.send_notification = original_send

print(f"PASS: {passed} Phase 4 reminder-policy assertions")

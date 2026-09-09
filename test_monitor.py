import os

import monitor

from monitor import (
    compare_snapshots,
    print_events,
    handle_events
)


# ============================================================
# TEST CONFIGURATION
# ============================================================

TEST_DEDUP_FILE = "test_notification_dedup.json"

# Use a temporary deduplication file for this test.
monitor.DEDUP_FILE = TEST_DEDUP_FILE

# Force all test notifications to console.
#
# This allows us to test deduplication without
# sending unnecessary Telegram messages.
monitor.NOTIFICATION_CHANNEL = "console"


# ============================================================
# CLEAN TEST FILE
# ============================================================

if os.path.exists(TEST_DEDUP_FILE):

    os.remove(TEST_DEDUP_FILE)


# ============================================================
# TEST DATA
# ============================================================

OLD_SNAPSHOT = {
    "last_checked": "2026-09-09T20:00:00",

    "assignments": [
        {
            "id": "assignment-1",
            "course": "Cloud Computing",
            "name": "Cloud Security Assignment",
            "url": "https://example.com/assignment-1",
            "due": "Sunday, 23 August 2026",
            "submission_status": "Submitted for grading",
            "grading_status": "Not graded",
            "time_remaining": "No time remaining"
        }
    ],

    "quizzes": [
        {
            "id": "quiz-1",
            "course": "Cloud Computing",
            "name": "Quiz1",
            "url": "https://example.com/quiz-1",
            "opened": "Wednesday, 29 July 2026, 8:30 PM",
            "closed": "Wednesday, 29 July 2026, 8:40 PM",
            "attempts_allowed": "1",
            "time_limit": "10 mins",
            "attempt_status": "Finished",
            "started": "Wednesday, 29 July 2026, 8:30 PM",
            "completed": "Wednesday, 29 July 2026, 8:35 PM",
            "grade": "8.00"
        }
    ],

    "attendance": {
        "Cloud Computing": {
            "status": "Closed",
            "percentage": "0.0%",
            "taken_sessions": "0",
            "points": "0 / 0",
            "sessions": []
        }
    }
}


# ============================================================
# SIMULATED NEW SNAPSHOT
# ============================================================

NEW_SNAPSHOT = {
    "last_checked": "2026-09-09T22:00:00",

    "assignments": [
        {
            "id": "assignment-1",
            "course": "Cloud Computing",
            "name": "Cloud Security Assignment",
            "url": "https://example.com/assignment-1",

            # Simulate changed due date
            "due": "Monday, 24 August 2026",

            "submission_status": "Submitted for grading",
            "grading_status": "Graded",
            "time_remaining": "No time remaining"
        },

        # Simulate a completely new assignment
        {
            "id": "assignment-2",
            "course": "Cloud Computing",
            "name": "New Cloud Assignment",
            "url": "https://example.com/assignment-2",
            "due": "Sunday, 13 September 2026",
            "submission_status": "Not submitted",
            "grading_status": "Not graded",
            "time_remaining": "4 days"
        }
    ],

    "quizzes": [
        {
            "id": "quiz-1",
            "course": "Cloud Computing",
            "name": "Quiz1",
            "url": "https://example.com/quiz-1",
            "opened": "Wednesday, 29 July 2026, 8:30 PM",
            "closed": "Wednesday, 29 July 2026, 8:40 PM",
            "attempts_allowed": "1",
            "time_limit": "10 mins",

            # Simulate changed quiz status
            "attempt_status": "Finished",
            "started": "Wednesday, 29 July 2026, 8:30 PM",
            "completed": "Wednesday, 29 July 2026, 8:35 PM",
            "grade": "9.00"
        },

        # Simulate a completely new quiz
        {
            "id": "quiz-2",
            "course": "Cloud Computing",
            "name": "New Quiz",
            "url": "https://example.com/quiz-2",
            "opened": "Sunday, 13 September 2026, 8:30 PM",
            "closed": "Sunday, 13 September 2026, 8:45 PM",
            "attempts_allowed": "1",
            "time_limit": "15 mins",
            "attempt_status": "Not attempted",
            "started": None,
            "completed": None,
            "grade": None
        }
    ],

    "attendance": {
        "Cloud Computing": {
            # Simulate attendance opening
            "status": "Open",

            # Simulate percentage change
            "percentage": "100.0%",

            "taken_sessions": "1",
            "points": "1 / 1",

            # Simulate a new attendance session
            "sessions": [
                {
                    "date": "Sunday, 13 September 2026",
                    "status": "Not taken"
                }
            ]
        }
    }
}


# ============================================================
# TEST HEADER
# ============================================================

print("\n")
print("=" * 70)
print("UNIVERSITY AI AGENT - EVENT DETECTION + ACTION TEST")
print("=" * 70)

print("\nThis test uses simulated snapshots.")
print("No Moodle data will be changed.")
print("The real monitor_snapshot.json will NOT be modified.")
print("Telegram will NOT be used in this test.")


# ============================================================
# RUN COMPARISON
# ============================================================

print("\n")
print("#" * 70)
print("COMPARING SIMULATED SNAPSHOTS")
print("#" * 70)

events = compare_snapshots(
    OLD_SNAPSHOT,
    NEW_SNAPSHOT
)


# ============================================================
# PRINT EVENTS
# ============================================================

print_events(events)


# ============================================================
# EVENT DETECTION RESULTS
# ============================================================

print("\n")
print("#" * 70)
print("EVENT DETECTION TEST SUMMARY")
print("#" * 70)


new_assignments_count = len(
    events["new_assignments"]
)

changed_assignments_count = len(
    events["changed_assignments"]
)

new_quizzes_count = len(
    events["new_quizzes"]
)

changed_quizzes_count = len(
    events["changed_quizzes"]
)

attendance_changes_count = len(
    events["attendance_changes"]
)


print(
    f"\nNew assignments detected: "
    f"{new_assignments_count}"
)

print(
    f"Changed assignments detected: "
    f"{changed_assignments_count}"
)

print(
    f"New quizzes detected: "
    f"{new_quizzes_count}"
)

print(
    f"Changed quizzes detected: "
    f"{changed_quizzes_count}"
)

print(
    f"Attendance changes detected: "
    f"{attendance_changes_count}"
)


# ============================================================
# EXPECTED RESULTS
# ============================================================

print("\n")
print("#" * 70)
print("EXPECTED EVENT DETECTION RESULTS")
print("#" * 70)

print("\nExpected:")

print("New assignments: 1")
print("Changed assignments: 1")
print("New quizzes: 1")
print("Changed quizzes: 1")
print("Attendance changes: 3")


# ============================================================
# AUTOMATIC EVENT DETECTION VALIDATION
# ============================================================

event_detection_passed = True


if new_assignments_count != 1:
    event_detection_passed = False

if changed_assignments_count != 1:
    event_detection_passed = False

if new_quizzes_count != 1:
    event_detection_passed = False

if changed_quizzes_count != 1:
    event_detection_passed = False

if attendance_changes_count != 3:
    event_detection_passed = False


# ============================================================
# ACTION HANDLER TEST
# ============================================================

print("\n")
print("#" * 70)
print("TESTING EVENT -> ACTION HANDLER")
print("#" * 70)

print("\nPassing detected events to handle_events()...")
print("These actions are simulated and only logged locally.")


first_action_count = handle_events(
    events
)


print(
    f"\nFirst run action count: "
    f"{first_action_count}"
)


# ============================================================
# EXPECTED FIRST ACTION COUNT
# ============================================================

#
# 1 new assignment
# 2 changed assignment fields
# 1 new quiz
# 1 changed quiz field
# 1 grouped attendance action
#
# Total = 6
#

expected_first_action_count = 6


if first_action_count == expected_first_action_count:

    print(
        "\nFIRST ACTION RUN PASSED"
    )

else:

    print(
        "\nFIRST ACTION RUN FAILED"
    )


# ============================================================
# DEDUPLICATION TEST
# ============================================================

print("\n")
print("#" * 70)
print("TESTING NOTIFICATION DEDUPLICATION")
print("#" * 70)

print(
    "\nSending the exact same events again..."
)

print(
    "All duplicate notifications should be skipped."
)


second_action_count = handle_events(
    events
)


print(
    f"\nSecond run action count: "
    f"{second_action_count}"
)


# ============================================================
# EXPECTED SECOND ACTION COUNT
# ============================================================

expected_second_action_count = 0


if second_action_count == expected_second_action_count:

    print(
        "\nDEDUPLICATION TEST PASSED"
    )

else:

    print(
        "\nDEDUPLICATION TEST FAILED"
    )


# ============================================================
# NEW EVENT TEST
# ============================================================

print("\n")
print("#" * 70)
print("TESTING NEW EVENT AFTER DEDUPLICATION")
print("#" * 70)


new_assignment_event = {
    "new_assignments": [
        {
            "id": "assignment-3",
            "course": "Cloud Computing",
            "name": "Another New Assignment",
            "url": "https://example.com/assignment-3",
            "due": "Monday, 14 September 2026",
            "submission_status": "Not submitted",
            "grading_status": "Not graded",
            "time_remaining": "5 days"
        }
    ],

    "changed_assignments": [],

    "new_quizzes": [],

    "changed_quizzes": [],

    "attendance_changes": []
}


new_event_action_count = handle_events(
    new_assignment_event
)


print(
    f"\nNew event action count: "
    f"{new_event_action_count}"
)


if new_event_action_count == 1:

    print(
        "\nNEW EVENT TEST PASSED"
    )

else:

    print(
        "\nNEW EVENT TEST FAILED"
    )


# ============================================================
# FINAL RESULT
# ============================================================

print("\n")
print("=" * 70)

if (
    event_detection_passed
    and
    first_action_count == expected_first_action_count
    and
    second_action_count == expected_second_action_count
    and
    new_event_action_count == 1
):

    print(
        "ALL EVENT DETECTION TESTS PASSED"
    )

    print(
        "EVENT -> ACTION HANDLER TEST PASSED"
    )

    print(
        "NOTIFICATION DEDUPLICATION TEST PASSED"
    )

    print(
        "NEW EVENT TEST PASSED"
    )

    print(
        "UNIVERSITY AI AGENT - "
        "EVENT -> ACTION PIPELINE PASSED"
    )

else:

    print(
        "UNIVERSITY AI AGENT - "
        "EVENT -> ACTION PIPELINE FAILED"
    )

print("=" * 70)


# ============================================================
# CLEANUP
# ============================================================

if os.path.exists(TEST_DEDUP_FILE):

    os.remove(TEST_DEDUP_FILE)

    print(
        f"\nTemporary test file removed: "
        f"{TEST_DEDUP_FILE}"
    )
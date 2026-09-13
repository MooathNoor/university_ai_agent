import hashlib
import json
import os
import time
from datetime import datetime

import tools

from notification import send_notification
from event_state import EventState
from verified_actions import VerifiedActionRunner

from tools import (
    get_my_courses,
    get_assignments,
    get_quizzes,
    get_attendance
)


# ============================================================
# CONFIGURATION
# ============================================================

SNAPSHOT_FILE = "monitor_snapshot.json"

# Stores actions executed by the Action Handler.
ACTION_LOG_FILE = "action_log.txt"

# Stores recently sent notification fingerprints.
DEDUP_FILE = "notification_dedup.json"

# Notification channel used by the Notification Manager.
# "auto" means the Notification Manager decides
# the channel based on notification priority.
NOTIFICATION_CHANNEL = "auto"

# How often the monitor checks Moodle.
# 300 seconds = 5 minutes
CHECK_INTERVAL = 300

# Prevent the same notification from being sent again
# during this period.
#
# 86400 seconds = 24 hours
DEDUP_WINDOW_SECONDS = 86400

# Phase 4B reminder policy.  Only events whose original Telegram notification
# was confirmed as sent are eligible.  Successful reminders are capped so the
# agent never spams the student.
REMINDER_POLICIES = {
    "attendance_opened": {
        "first_after_minutes": 10,
        "repeat_after_minutes": 20,
        "max_reminders": 2,
    },
    "quiz_added": {
        "first_after_minutes": 30,
        "repeat_after_minutes": 120,
        "max_reminders": 2,
    },
    "assignment_added": {
        "first_after_minutes": 60,
        "repeat_after_minutes": 360,
        "max_reminders": 2,
    },
    "deadline_near": {
        "first_after_minutes": 15,
        "repeat_after_minutes": 60,
        "max_reminders": 2,
    },
}


# ============================================================
# COURSE CACHE
# ============================================================

_course_cache = None
_event_state = EventState()
_verified_action_runner = VerifiedActionRunner()


def get_cached_courses():
    """
    Get Moodle courses only once during one monitoring cycle.

    The current tools functions internally call get_courses()
    multiple times. This cache prevents repeated course
    discovery requests during the same monitoring check.
    """

    global _course_cache

    if _course_cache is None:

        print(
            "\nLoading Moodle courses for this monitoring cycle..."
        )

        _course_cache = get_my_courses()

    else:

        print(
            "\nUsing cached Moodle courses..."
        )

    return _course_cache


def enable_course_cache():
    """
    Replace tools.get_courses with a cached version.

    This allows the existing tools functions to reuse
    the same course list without changing tools.py.
    """

    original_get_courses = tools.get_courses

    def cached_get_courses():
        global _course_cache

        if _course_cache is None:
            _course_cache = original_get_courses()

        return _course_cache

    tools.get_courses = cached_get_courses


def reset_course_cache():
    """
    Clear the course cache before starting
    a new monitoring cycle.
    """

    global _course_cache

    _course_cache = None


def get_course_identity(course_name):
    """Return stable Moodle course identity for an event payload."""

    if not course_name:
        return {
            "course_id": None,
            "course_name": course_name
        }

    courses = get_cached_courses()

    if not isinstance(courses, list):
        return {
            "course_id": None,
            "course_name": course_name
        }

    normalized = str(course_name).strip().lower()

    # Prefer exact Moodle name equality.
    for course in courses:
        real_name = str(course.get("name") or "").strip()
        if real_name.lower() == normalized:
            return {
                "course_id": course.get("id"),
                "course_name": real_name or course_name
            }

    # Fall back to conservative phrase matching.
    for course in courses:
        real_name = str(course.get("name") or "").strip()
        real_lower = real_name.lower()

        if normalized and (
            normalized in real_lower
            or real_lower in normalized
        ):
            return {
                "course_id": course.get("id"),
                "course_name": real_name or course_name
            }

    return {
        "course_id": None,
        "course_name": course_name
    }


def record_agent_event(event_type, payload):
    """Persist one monitor event and return matching pending actions.

    The shared EventState is refreshed from disk, so pending actions created by
    the Telegram process can be matched here even when monitor.py runs in a
    separate process.
    """

    try:
        result = _event_state.record_event(
            event_type,
            payload or {}
        )

        event = result.get("event", {})
        matches = result.get("matching_actions", [])

        print(
            f"\n[EVENT STATE] Recorded {event_type} "
            f"as {event.get('id')}. "
            f"Matching pending actions: {len(matches)}"
        )

        return result

    except Exception as error:
        # Event-state persistence must not stop Moodle monitoring.
        print(
            f"\n[EVENT STATE] Could not record "
            f"{event_type}: {error}"
        )

        return {
            "event": None,
            "matching_actions": []
        }


def pending_action_note(event_result):
    """Build a short note when a detected event matches saved user requests."""

    matches = (event_result or {}).get(
        "matching_actions",
        []
    )

    if not matches:
        return ""

    readable_requests = []

    for action in matches:
        if not action.get("notify", True):
            continue

        original = str(
            action.get("original_request") or ""
        ).strip()

        if original:
            readable_requests.append(original)

    if not readable_requests:
        return (
            "\n\n✅ This event matched a saved pending action."
        )

    unique_requests = list(dict.fromkeys(readable_requests))
    lines = [
        "",
        "✅ This event matched your saved request:"
    ]

    for request in unique_requests[:3]:
        lines.append(f"- {request}")

    if len(unique_requests) > 3:
        lines.append(
            f"- +{len(unique_requests) - 3} more saved request(s)"
        )

    return "\n".join(lines)


def notification_channel_for_event(event_result):
    """Force Telegram when a matching pending action asked for notification."""

    matches = (event_result or {}).get(
        "matching_actions",
        []
    )

    if any(action.get("notify", True) for action in matches):
        return "telegram"

    return NOTIFICATION_CHANNEL


# ============================================================
# PHASE 4C - VERIFIED STATE-CHANGING ACTIONS
# ============================================================

def register_verified_action(
    action_type,
    executor,
    verifier,
    *,
    requires_authorization=True,
    requires_presence=False
):
    """Register one real state-changing capability with execution + verification.

    Registration is explicit.  An arbitrary ``requested_action`` stored in event
    state can never execute code merely because its name appears in a pending
    action.  If it is not registered here, VerifiedActionRunner fails closed.
    """

    _verified_action_runner.register(
        action_type,
        executor,
        verifier,
        requires_authorization=requires_authorization,
        requires_presence=requires_presence,
    )


def _event_action_payload(event_result, pending_action):
    """Build the grounded payload supplied to a verified action executor."""

    event = (event_result or {}).get("event") or {}
    event_payload = event.get("payload") or {}

    payload = dict(event_payload) if isinstance(event_payload, dict) else {}
    payload.update({
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "pending_action_id": pending_action.get("id"),
        "original_request": pending_action.get("original_request", ""),
    })
    return payload


def process_matching_pending_actions(event_result):
    """Execute matched non-notification actions only through Phase 4C's gate.

    ``notify`` remains read-only and is handled by the existing Notification
    Manager.  Every other requested action is passed to VerifiedActionRunner.

    Security rules:
    - unregistered action -> blocked
    - missing stored authorization -> blocked
    - presence-sensitive action without confirmed presence -> blocked
    - execution alone never means success
    - a pending action is completed only after fresh verification succeeds
    """

    matches = (event_result or {}).get("matching_actions") or []
    results = []

    for action in matches:
        if not isinstance(action, dict):
            continue

        requested_action = str(
            action.get("requested_action") or "notify"
        ).strip().lower().replace(" ", "_")

        if not requested_action or requested_action == "notify":
            continue

        payload = _event_action_payload(
            event_result,
            action
        )

        event = (event_result or {}).get("event") or {}
        event_id = str(event.get("id") or "").strip()

        presence_confirmed = (
            action.get("presence_confirmed") is True
            and str(action.get("presence_confirmed_event_id") or "").strip()
            == event_id
        )

        result = _verified_action_runner.run(
            requested_action,
            payload,
            authorized=(action.get("authorized") is True),
            presence_confirmed=presence_confirmed,
        )

        result_dict = result.to_dict()
        result_dict["pending_action_id"] = action.get("id")
        result_dict["original_request"] = action.get("original_request", "")
        result_dict["event_id"] = event_id
        result_dict["authorized"] = action.get("authorized") is True
        result_dict["presence_required"] = action.get("presence_required") is True
        result_dict["presence_confirmed"] = presence_confirmed
        results.append(result_dict)

        print(
            f"\n[VERIFIED ACTION] {requested_action}: "
            f"{result.status} "
            f"(execution={result.execution_status}, "
            f"verification={result.verification_status})"
        )

        # A one-shot state-changing request is complete only when the external
        # system independently proves that the requested state now exists.
        if result.status == "success":
            action_id = action.get("id")
            if action_id:
                completed = _event_state.complete_pending_action(
                    action_id
                )
                if not completed:
                    print(
                        f"[VERIFIED ACTION] Warning: could not mark "
                        f"pending action {action_id} completed."
                    )

    return results


def retry_pending_action_for_event(event_id, pending_action_id):
    """Retry exactly one previously-triggered pending action.

    Used after a conversational precondition such as physical presence is
    confirmed. The event/action relationship is reloaded from persistent state
    and validated before entering the normal VerifiedActionRunner path.
    """
    event_id = str(event_id or "").strip()
    pending_action_id = str(pending_action_id or "").strip()

    if not event_id or not pending_action_id:
        return {
            "status": "blocked",
            "message": "Missing event or pending-action identity.",
        }

    snapshot = _event_state.snapshot(
        max_events=200,
        max_actions=200,
    )

    event = next(
        (
            item for item in (snapshot.get("recent_events") or [])
            if str(item.get("id") or "") == event_id
        ),
        None,
    )
    action = next(
        (
            item for item in (snapshot.get("pending_actions") or [])
            if str(item.get("id") or "") == pending_action_id
        ),
        None,
    )

    if not event:
        return {
            "status": "blocked",
            "message": "The original event is no longer available.",
        }

    if not action:
        return {
            "status": "blocked",
            "message": "The pending action is no longer active.",
        }

    if str(action.get("last_triggered_event_id") or "") != event_id:
        return {
            "status": "blocked",
            "message": "The pending action is not bound to this event.",
        }

    results = process_matching_pending_actions({
        "event": event,
        "matching_actions": [action],
    })

    if not results:
        return {
            "status": "blocked",
            "message": "No state-changing action was available to retry.",
        }

    return results[0]


def verified_action_note(results):
    """Format concise verification outcomes for the event notification."""

    if not results:
        return ""

    lines = ["", "🔐 Saved action result:"]

    for result in results:
        action_type = result.get("action_type") or "action"
        status = result.get("status") or "unknown"
        message = str(result.get("message") or "").strip()

        if (
            status == "blocked"
            and result.get("presence_required") is True
            and result.get("authorized") is True
            and result.get("presence_confirmed") is not True
        ):
            lines.append(
                "- 🟡 قبل أي تسجيل حضور لازم تأكدلي إنك موجود فعليًا بالمحاضرة الآن."
            )
            lines.append(
                "  إذا أنت موجود، رد بشكل طبيعي مثل: أنا موجود بالمحاضرة."
            )
            continue

        if status == "success":
            prefix = "✅ verified"
        elif status == "blocked":
            prefix = "🛑 blocked"
        elif status == "failed":
            prefix = "❌ failed"
        else:
            prefix = "⚠️ unverified"

        line = f"- {action_type}: {prefix}"
        if message:
            line += f" — {message}"
        lines.append(line)

    return "\n".join(lines)


# ============================================================
# LOAD SNAPSHOT
# ============================================================

def load_snapshot():
    """
    Load the previous monitoring snapshot.

    If the snapshot file does not exist,
    return an empty snapshot.
    """

    if not os.path.exists(SNAPSHOT_FILE):
        return {
            "assignments": [],
            "quizzes": [],
            "attendance": {}
        }

    try:

        with open(
            SNAPSHOT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except (json.JSONDecodeError, OSError):

        print(
            "\nWarning: Could not read the previous "
            "monitoring snapshot."
        )

        return {
            "assignments": [],
            "quizzes": [],
            "attendance": {}
        }


# ============================================================
# SAVE SNAPSHOT
# ============================================================

def save_snapshot(snapshot):
    """
    Save the current Moodle state to a JSON file.
    """

    try:

        with open(
            SNAPSHOT_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                snapshot,
                file,
                ensure_ascii=False,
                indent=4
            )

        print(
            f"\nSnapshot saved to: "
            f"{SNAPSHOT_FILE}"
        )

    except OSError as error:

        print(
            f"\nCould not save snapshot: {error}"
        )


# ============================================================
# LOAD DEDUPLICATION DATA
# ============================================================

def load_dedup_data():
    """
    Load recently sent notification fingerprints.

    The deduplication data is stored separately from
    the Moodle monitoring snapshot.

    If the file does not exist or cannot be read,
    an empty dictionary is returned.
    """

    if not os.path.exists(DEDUP_FILE):

        return {}

    try:

        with open(
            DEDUP_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            return {}

        return data

    except (json.JSONDecodeError, OSError):

        print(
            "\nWarning: Could not read notification "
            "deduplication data."
        )

        return {}


# ============================================================
# SAVE DEDUPLICATION DATA
# ============================================================

def save_dedup_data(data):
    """
    Save notification deduplication data.
    """

    try:

        with open(
            DEDUP_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

        return True

    except OSError as error:

        print(
            f"\nCould not save deduplication data: "
            f"{error}"
        )

        return False


# ============================================================
# CREATE NOTIFICATION FINGERPRINT
# ============================================================

def create_notification_fingerprint(
    action_type,
    message
):
    """
    Create a stable fingerprint for a notification.

    The same action type + same message produces
    the same fingerprint.

    This allows the system to recognize duplicate
    notifications without storing the complete message
    as the dictionary key.
    """

    raw_value = (
        f"{action_type}|{message}"
    )

    fingerprint = hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()

    return fingerprint


# ============================================================
# CLEAN EXPIRED DEDUPLICATION DATA
# ============================================================

def clean_expired_dedup_data(
    dedup_data
):
    """
    Remove deduplication records that are older
    than DEDUP_WINDOW_SECONDS.
    """

    current_time = time.time()

    cleaned_data = {}

    for fingerprint, timestamp in dedup_data.items():

        try:

            sent_time = float(timestamp)

        except (TypeError, ValueError):

            continue

        age = current_time - sent_time

        if age < DEDUP_WINDOW_SECONDS:

            cleaned_data[fingerprint] = sent_time

    return cleaned_data


# ============================================================
# CHECK IF NOTIFICATION IS DUPLICATE
# ============================================================

def is_duplicate_notification(
    action_type,
    message
):
    """
    Check whether the same notification was already sent
    recently.

    Returns True if the notification should be skipped.
    Returns False if it is a new notification.
    """

    dedup_data = load_dedup_data()

    cleaned_data = clean_expired_dedup_data(
        dedup_data
    )

    fingerprint = create_notification_fingerprint(
        action_type,
        message
    )

    if fingerprint in cleaned_data:

        last_sent = cleaned_data[
            fingerprint
        ]

        age = time.time() - last_sent

        print(
            "\n[DUPLICATE NOTIFICATION]"
        )

        print(
            "The same notification was already "
            f"sent {int(age)} seconds ago."
        )

        print(
            "Notification will be skipped."
        )

        # Save cleaned data in case expired
        # records were removed.
        save_dedup_data(
            cleaned_data
        )

        return True

    # Save cleaned data even when the current
    # notification is not a duplicate.
    save_dedup_data(
        cleaned_data
    )

    return False


# ============================================================
# MARK NOTIFICATION AS SENT
# ============================================================

def mark_notification_as_sent(
    action_type,
    message
):
    """
    Record a notification only after it has been
    successfully sent.

    This is important because a failed Telegram request
    must remain retryable.
    """

    dedup_data = load_dedup_data()

    dedup_data = clean_expired_dedup_data(
        dedup_data
    )

    fingerprint = create_notification_fingerprint(
        action_type,
        message
    )

    dedup_data[fingerprint] = time.time()

    return save_dedup_data(
        dedup_data
    )


# ============================================================
# CREATE ASSIGNMENT IDENTIFIER
# ============================================================

def assignment_key(assignment):
    """
    Create a stable identifier for an assignment.

    Moodle assignment URLs are preferred because
    the same assignment name could theoretically
    appear more than once.
    """

    return (
        assignment.get("url")
        or
        f"{assignment.get('course')}|"
        f"{assignment.get('name')}"
    )


# ============================================================
# CREATE QUIZ IDENTIFIER
# ============================================================

def quiz_key(quiz):
    """
    Create a stable identifier for a quiz.
    """

    return (
        quiz.get("url")
        or
        f"{quiz.get('course')}|"
        f"{quiz.get('name')}"
    )


# ============================================================
# BUILD CURRENT ASSIGNMENT STATE
# ============================================================

def collect_assignments():
    """
    Get the current real assignment state from Moodle.
    """

    print("\n" + "=" * 70)
    print("CHECKING ASSIGNMENTS")
    print("=" * 70)

    result = get_assignments()

    if not isinstance(result, list):

        print("Could not collect assignments.")

        return []

    assignments = []

    for assignment in result:

        course_identity = get_course_identity(
            assignment.get("course")
        )

        assignments.append({
            "id": assignment_key(assignment),
            "course_id": course_identity.get("course_id"),
            "course": course_identity.get("course_name"),
            "name": assignment.get("name"),
            "url": assignment.get("url"),
            "due": assignment.get("due"),
            "submission_status": assignment.get(
                "submission_status"
            ),
            "grading_status": assignment.get(
                "grading_status"
            ),
            "time_remaining": assignment.get(
                "time_remaining"
            )
        })

    print(
        f"Assignments collected: "
        f"{len(assignments)}"
    )

    return assignments


# ============================================================
# BUILD CURRENT QUIZ STATE
# ============================================================

def collect_quizzes():
    """
    Get the current real quiz state from Moodle.
    """

    print("\n" + "=" * 70)
    print("CHECKING QUIZZES")
    print("=" * 70)

    result = get_quizzes()

    if not isinstance(result, list):

        print("Could not collect quizzes.")

        return []

    quizzes = []

    for quiz in result:

        course_identity = get_course_identity(
            quiz.get("course")
        )

        quizzes.append({
            "id": quiz_key(quiz),
            "course_id": course_identity.get("course_id"),
            "course": course_identity.get("course_name"),
            "name": quiz.get("name"),
            "url": quiz.get("url"),
            "opened": quiz.get("opened"),
            "closed": quiz.get("closed"),
            "attempts_allowed": quiz.get(
                "attempts_allowed"
            ),
            "time_limit": quiz.get(
                "time_limit"
            ),
            "attempt_status": quiz.get(
                "attempt_status"
            ),
            "started": quiz.get(
                "started"
            ),
            "completed": quiz.get(
                "completed"
            ),
            "grade": quiz.get(
                "grade"
            )
        })

    print(
        f"Quizzes collected: "
        f"{len(quizzes)}"
    )

    return quizzes


# ============================================================
# BUILD CURRENT ATTENDANCE STATE
# ============================================================

def collect_attendance(courses):
    """
    Get the current real attendance state
    for every registered Moodle course.

    This is read-only.
    """

    print("\n" + "=" * 70)
    print("CHECKING ATTENDANCE")
    print("=" * 70)

    attendance_state = {}

    for index, course in enumerate(
        courses,
        start=1
    ):

        course_name = course.get("name")

        print(
            f"\nAttendance "
            f"{index}/{len(courses)}: "
            f"{course_name}"
        )

        result = get_attendance(course_name)

        if not isinstance(result, dict):

            attendance_state[course_name] = {
                "status": "Error"
            }

            continue

        attendance_state[course_name] = {
            "course_id": course.get("id"),
            # ``status`` from tools.get_attendance means request success/error.
            # Monitoring needs the actual student-facing activity state instead.
            # Keep the legacy fallback only for older fixtures/tests.
            "status": result.get("activity_state") or result.get("status"),
            "request_status": result.get("status"),
            "attendance_url": result.get("attendance_url"),
            "discovery": result.get("discovery", {}),
            "percentage": result.get(
                "percentage"
            ),
            "taken_sessions": result.get(
                "taken_sessions"
            ),
            "points": result.get(
                "points"
            ),
            "sessions": result.get(
                "sessions",
                []
            )
        }

    return attendance_state


# ============================================================
# COLLECT CURRENT MOODLE STATE
# ============================================================

def collect_current_state():
    """
    Collect the current Moodle state.

    This becomes the new snapshot used
    for comparison.
    """

    print("\n")
    print("#" * 70)
    print("COLLECTING CURRENT MOODLE STATE")
    print("#" * 70)

    # Start a fresh cache for this monitoring cycle.
    reset_course_cache()

    # Enable the cache inside tools.py functions.
    enable_course_cache()

    # Get courses once.
    courses = get_cached_courses()

    if not isinstance(courses, list):

        print(
            "\nCould not get Moodle courses."
        )

        return None

    print(
        f"\nCourses found: "
        f"{len(courses)}"
    )

    # These functions will reuse the cached courses.
    assignments = collect_assignments()

    quizzes = collect_quizzes()

    attendance = collect_attendance(
        courses
    )

    return {
        "last_checked": datetime.now().isoformat(
            timespec="seconds"
        ),
        "assignments": assignments,
        "quizzes": quizzes,
        "attendance": attendance
    }


# ============================================================
# FIND NEW ASSIGNMENTS
# ============================================================

def find_new_assignments(
    old_assignments,
    new_assignments
):
    """
    Detect assignments that did not exist
    in the previous snapshot.
    """

    old_ids = {
        assignment.get("id")
        for assignment in old_assignments
    }

    new_items = []

    for assignment in new_assignments:

        if assignment.get("id") not in old_ids:

            new_items.append(
                assignment
            )

    return new_items


# ============================================================
# FIND CHANGED ASSIGNMENTS
# ============================================================

def find_changed_assignments(
    old_assignments,
    new_assignments
):
    """
    Detect important changes to existing assignments.
    """

    old_by_id = {
        assignment.get("id"): assignment
        for assignment in old_assignments
    }

    changes = []

    for assignment in new_assignments:

        assignment_id = assignment.get("id")

        if assignment_id not in old_by_id:
            continue

        old_assignment = old_by_id[
            assignment_id
        ]

        changed_fields = []

        fields_to_check = [
            "due",
            "submission_status",
            "grading_status",
            "time_remaining"
        ]

        for field in fields_to_check:

            old_value = old_assignment.get(
                field
            )

            new_value = assignment.get(
                field
            )

            if old_value != new_value:

                changed_fields.append({
                    "field": field,
                    "old": old_value,
                    "new": new_value
                })

        if changed_fields:

            changes.append({
                "assignment": assignment,
                "changes": changed_fields
            })

    return changes


# ============================================================
# FIND NEW QUIZZES
# ============================================================

def find_new_quizzes(
    old_quizzes,
    new_quizzes
):
    """
    Detect quizzes that did not exist
    in the previous snapshot.
    """

    old_ids = {
        quiz.get("id")
        for quiz in old_quizzes
    }

    new_items = []

    for quiz in new_quizzes:

        if quiz.get("id") not in old_ids:

            new_items.append(
                quiz
            )

    return new_items


# ============================================================
# FIND CHANGED QUIZZES
# ============================================================

def find_changed_quizzes(
    old_quizzes,
    new_quizzes
):
    """
    Detect important changes to existing quizzes.
    """

    old_by_id = {
        quiz.get("id"): quiz
        for quiz in old_quizzes
    }

    changes = []

    for quiz in new_quizzes:

        quiz_id = quiz.get("id")

        if quiz_id not in old_by_id:
            continue

        old_quiz = old_by_id[
            quiz_id
        ]

        changed_fields = []

        fields_to_check = [
            "opened",
            "closed",
            "attempts_allowed",
            "time_limit",
            "attempt_status",
            "started",
            "completed",
            "grade"
        ]

        for field in fields_to_check:

            old_value = old_quiz.get(
                field
            )

            new_value = quiz.get(
                field
            )

            if old_value != new_value:

                changed_fields.append({
                    "field": field,
                    "old": old_value,
                    "new": new_value
                })

        if changed_fields:

            changes.append({
                "quiz": quiz,
                "changes": changed_fields
            })

    return changes


# ============================================================
# FIND ATTENDANCE CHANGES
# ============================================================

def find_attendance_changes(
    old_attendance,
    new_attendance
):
    """
    Detect attendance changes.

    The first important use is detecting when
    Moodle attendance changes from Closed to Open.

    This function does NOT submit attendance.
    """

    changes = []

    for course_name, new_data in new_attendance.items():

        old_data = old_attendance.get(
            course_name
        )

        if old_data is None:

            changes.append({
                "course": course_name,
                "course_id": new_data.get("course_id"),
                "type": "new_course_attendance",
                "old": None,
                "new": new_data
            })

            continue

        old_status = old_data.get(
            "status"
        )

        new_status = new_data.get(
            "status"
        )

        if old_status != new_status:

            changes.append({
                "course": course_name,
                "course_id": new_data.get("course_id"),
                "type": "status_changed",
                "old": old_status,
                "new": new_status
            })

        old_percentage = old_data.get(
            "percentage"
        )

        new_percentage = new_data.get(
            "percentage"
        )

        if old_percentage != new_percentage:

            changes.append({
                "course": course_name,
                "course_id": new_data.get("course_id"),
                "type": "percentage_changed",
                "old": old_percentage,
                "new": new_percentage
            })

        old_sessions = old_data.get(
            "sessions",
            []
        )

        new_sessions = new_data.get(
            "sessions",
            []
        )

        if old_sessions != new_sessions:

            changes.append({
                "course": course_name,
                "course_id": new_data.get("course_id"),
                "type": "sessions_changed",
                "old": old_sessions,
                "new": new_sessions
            })

    return changes


# ============================================================
# COMPARE SNAPSHOTS
# ============================================================

def compare_snapshots(
    old_snapshot,
    new_snapshot
):
    """
    Compare the previous Moodle state
    with the current Moodle state.
    """

    old_assignments = old_snapshot.get(
        "assignments",
        []
    )

    new_assignments = new_snapshot.get(
        "assignments",
        []
    )

    old_quizzes = old_snapshot.get(
        "quizzes",
        []
    )

    new_quizzes = new_snapshot.get(
        "quizzes",
        []
    )

    old_attendance = old_snapshot.get(
        "attendance",
        {}
    )

    new_attendance = new_snapshot.get(
        "attendance",
        {}
    )

    return {
        "new_assignments": find_new_assignments(
            old_assignments,
            new_assignments
        ),

        "changed_assignments": find_changed_assignments(
            old_assignments,
            new_assignments
        ),

        "new_quizzes": find_new_quizzes(
            old_quizzes,
            new_quizzes
        ),

        "changed_quizzes": find_changed_quizzes(
            old_quizzes,
            new_quizzes
        ),

        "attendance_changes": find_attendance_changes(
            old_attendance,
            new_attendance
        )
    }


# ============================================================
# ACTION LOG
# ============================================================

def log_action(action_type, message):
    """
    Save an executed action to the local action log.

    This is the first Action Handler implementation.
    Later, this can be replaced or extended with
    email, WhatsApp, Telegram, or another service.
    """

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    log_line = (
        f"[{timestamp}] "
        f"{action_type}: "
        f"{message}\n"
    )

    try:

        with open(
            ACTION_LOG_FILE,
            "a",
            encoding="utf-8"
        ) as file:

            file.write(log_line)

        print(
            f"\nACTION LOGGED: "
            f"{log_line.strip()}"
        )

        return True

    except OSError as error:

        print(
            f"\nCould not write action log: "
            f"{error}"
        )

        return False


# ============================================================
# EXECUTE ACTION
# ============================================================

def execute_action(
    action_type,
    message,
    channel=None,
    event_result=None
):
    """
    Execute one action.

    The action currently:
    1. Checks notification deduplication.
    2. Saves the action to action_log.txt.
    3. Sends a notification through the
       Notification Manager.
    4. Records the notification as sent only
       after successful delivery.

    This prevents duplicate notifications.
    """

    resolved_channel = channel or NOTIFICATION_CHANNEL
    event_id = None
    if isinstance(event_result, dict):
        event = event_result.get("event") or {}
        if isinstance(event, dict):
            event_id = event.get("id")

    print("\n" + "-" * 70)
    print("ACTION HANDLER")
    print("-" * 70)

    print(
        f"Action type: {action_type}"
    )

    print(
        f"Message: {message}"
    )

    # --------------------------------------------------------
    # Check duplicate notification
    # --------------------------------------------------------

    if is_duplicate_notification(
        action_type,
        message
    ):

        print(
            "\nAction skipped because the notification "
            "is a duplicate."
        )

        if event_id:
            _event_state.mark_event_notification(
                event_id,
                "skipped_duplicate",
                channel=resolved_channel,
                notification_type=action_type,
            )
        return False

    # --------------------------------------------------------
    # Save action to log
    # --------------------------------------------------------

    action_logged = log_action(
        action_type,
        message
    )

    if not action_logged:

        print(
            "\nAction was not executed because "
            "the action log could not be written."
        )

        if event_id:
            _event_state.mark_event_notification(
                event_id,
                "failed",
                channel=resolved_channel,
                notification_type=action_type,
            )
        return False

    # --------------------------------------------------------
    # Send notification
    # --------------------------------------------------------

    notification_sent = send_notification(
        action_type,
        message,
        channel=resolved_channel
    )

    if notification_sent:

        # Only mark the notification as sent
        # after successful delivery.
        marked = mark_notification_as_sent(
            action_type,
            message
        )

        if not marked:

            print(
                "\nWarning: Notification was sent, "
                "but deduplication record could not "
                "be saved."
            )

        if event_id:
            _event_state.mark_event_notification(
                event_id,
                "sent",
                channel=resolved_channel,
                notification_type=action_type,
            )

        print(
            "\nNotification sent successfully."
        )

        return True

    if event_id:
        _event_state.mark_event_notification(
            event_id,
            "failed",
            channel=resolved_channel,
            notification_type=action_type,
        )

    print(
        "\nNotification could not be sent."
    )

    return False


# ============================================================
# HANDLE NEW ASSIGNMENT
# ============================================================

def handle_new_assignment(assignment):
    """
    Handle a newly detected assignment.

    The event is persisted before notification so the conversational agent can
    later answer questions such as "شو فاتني؟" even if Telegram was missed.
    """

    payload = {
        "course_id": assignment.get("course_id"),
        "course_name": assignment.get("course"),
        "assignment_id": assignment.get("id"),
        "name": assignment.get("name"),
        "url": assignment.get("url"),
        "due": assignment.get("due"),
        "submission_status": assignment.get("submission_status"),
        "grading_status": assignment.get("grading_status"),
        "time_remaining": assignment.get("time_remaining")
    }

    event_result = record_agent_event(
        "assignment_added",
        payload
    )
    verified_results = process_matching_pending_actions(
        event_result
    )

    message = (
        f"New assignment '{assignment.get('name')}' "
        f"in {assignment.get('course')}. "
        f"Due: {assignment.get('due')}. "
        f"URL: {assignment.get('url')}"
        f"{pending_action_note(event_result)}"
        f"{verified_action_note(verified_results)}"
    )

    return execute_action(
        "NEW_ASSIGNMENT",
        message,
        channel=notification_channel_for_event(
            event_result
        ),
        event_result=event_result
    )


# ============================================================
# HANDLE CHANGED ASSIGNMENT
# ============================================================

def handle_changed_assignment(change):
    """Handle an important change to an existing assignment."""

    action_count = 0

    assignment = change.get(
        "assignment",
        {}
    )

    payload = {
        "course_id": assignment.get("course_id"),
        "course_name": assignment.get("course"),
        "assignment_id": assignment.get("id"),
        "name": assignment.get("name"),
        "url": assignment.get("url"),
        "due": assignment.get("due"),
        "changes": change.get("changes", [])
    }

    event_result = record_agent_event(
        "assignment_changed",
        payload
    )

    note = pending_action_note(event_result)
    channel = notification_channel_for_event(
        event_result
    )

    for field_change in change.get(
        "changes",
        []
    ):

        message = (
            f"Assignment '{assignment.get('name')}' "
            f"in {assignment.get('course')} "
            f"changed field '{field_change.get('field')}' "
            f"from '{field_change.get('old')}' "
            f"to '{field_change.get('new')}'."
            f"{note}"
        )

        if execute_action(
            "ASSIGNMENT_CHANGED",
            message,
            channel=channel,
            event_result=event_result
        ):

            action_count += 1

    return action_count


# ============================================================
# HANDLE NEW QUIZ
# ============================================================

def handle_new_quiz(quiz):
    """Handle a newly detected quiz and persist it as an agent event."""

    payload = {
        "course_id": quiz.get("course_id"),
        "course_name": quiz.get("course"),
        "quiz_id": quiz.get("id"),
        "name": quiz.get("name"),
        "url": quiz.get("url"),
        "opened": quiz.get("opened"),
        "closed": quiz.get("closed"),
        "attempts_allowed": quiz.get("attempts_allowed"),
        "time_limit": quiz.get("time_limit"),
        "attempt_status": quiz.get("attempt_status")
    }

    event_result = record_agent_event(
        "quiz_added",
        payload
    )
    verified_results = process_matching_pending_actions(
        event_result
    )

    message = (
        f"New quiz '{quiz.get('name')}' "
        f"in {quiz.get('course')}. "
        f"Opened: {quiz.get('opened')}. "
        f"Closed: {quiz.get('closed')}. "
        f"URL: {quiz.get('url')}"
        f"{pending_action_note(event_result)}"
        f"{verified_action_note(verified_results)}"
    )

    return execute_action(
        "NEW_QUIZ",
        message,
        channel=notification_channel_for_event(
            event_result
        ),
        event_result=event_result
    )


# ============================================================
# HANDLE CHANGED QUIZ
# ============================================================

def handle_changed_quiz(change):
    """Handle an important change to an existing quiz."""

    action_count = 0

    quiz = change.get(
        "quiz",
        {}
    )

    payload = {
        "course_id": quiz.get("course_id"),
        "course_name": quiz.get("course"),
        "quiz_id": quiz.get("id"),
        "name": quiz.get("name"),
        "url": quiz.get("url"),
        "changes": change.get("changes", [])
    }

    event_result = record_agent_event(
        "quiz_changed",
        payload
    )

    note = pending_action_note(event_result)
    channel = notification_channel_for_event(
        event_result
    )

    for field_change in change.get(
        "changes",
        []
    ):

        message = (
            f"Quiz '{quiz.get('name')}' "
            f"in {quiz.get('course')} "
            f"changed field '{field_change.get('field')}' "
            f"from '{field_change.get('old')}' "
            f"to '{field_change.get('new')}'."
            f"{note}"
        )

        if execute_action(
            "QUIZ_CHANGED",
            message,
            channel=channel,
            event_result=event_result
        ):

            action_count += 1

    return action_count


# ============================================================
# HANDLE GROUPED ATTENDANCE CHANGES
# ============================================================

def handle_attendance_changes(changes):
    """
    Handle grouped attendance changes for one course.

    A Closed -> Open transition is emitted as ``attendance_opened``. Other
    changes are emitted as ``attendance_changed``. This remains read-only and
    never submits attendance.
    """

    if not changes:
        return False

    course = changes[0].get(
        "course"
    )
    course_id = changes[0].get(
        "course_id"
    )

    attendance_opened = any(
        change.get("type") == "status_changed"
        and str(change.get("new") or "").strip().lower() == "open"
        and str(change.get("old") or "").strip().lower() != "open"
        for change in changes
    )

    current_status = None
    for change in changes:
        if change.get("type") == "status_changed":
            current_status = change.get("new")

    payload = {
        "course_id": course_id,
        "course_name": course,
        "status": current_status,
        "changes": changes
    }

    event_type = (
        "attendance_opened"
        if attendance_opened
        else "attendance_changed"
    )

    event_result = record_agent_event(
        event_type,
        payload
    )
    verified_results = process_matching_pending_actions(
        event_result
    )

    message_lines = [
        f"Attendance update in '{course}'.",
        ""
    ]

    for change in changes:

        change_type = change.get(
            "type"
        )

        old_value = change.get(
            "old"
        )

        new_value = change.get(
            "new"
        )

        if change_type == "status_changed":

            message_lines.append(
                f"Status: {old_value} -> {new_value}"
            )

        elif change_type == "percentage_changed":

            message_lines.append(
                f"Percentage: {old_value} -> {new_value}"
            )

        elif change_type == "sessions_changed":

            message_lines.append(
                "Attendance sessions changed."
            )

        elif change_type == "new_course_attendance":

            message_lines.append(
                "New attendance information detected."
            )

        else:

            message_lines.append(
                f"{change_type}: "
                f"{old_value} -> {new_value}"
            )

    note = pending_action_note(
        event_result
    )

    if note:
        message_lines.append(note)

    verification_note = verified_action_note(
        verified_results
    )
    if verification_note:
        message_lines.append(verification_note)

    message = "\n".join(
        message_lines
    )

    notification_type = (
        "ATTENDANCE_OPENED"
        if attendance_opened
        else "ATTENDANCE_CHANGED"
    )

    return execute_action(
        notification_type,
        message,
        channel=notification_channel_for_event(
            event_result
        ),
        event_result=event_result
    )


# ============================================================
# GROUP ATTENDANCE CHANGES BY COURSE
# ============================================================

def group_attendance_changes_by_course(
    changes
):
    """
    Group attendance events by course.

    If several attendance fields change for the same course,
    they are handled as one notification.

    Different courses still receive separate notifications.
    """

    grouped_changes = {}

    for change in changes:

        course = change.get(
            "course"
        )

        if course not in grouped_changes:

            grouped_changes[course] = []

        grouped_changes[course].append(
            change
        )

    return grouped_changes


# ============================================================
# HANDLE DETECTED EVENTS
# ============================================================

def handle_events(events):
    """
    Convert detected events into actions.

    This is the main Event -> Action Handler.

    Event Detection tells us WHAT changed.
    Action Handler decides WHAT TO DO about it.

    Attendance changes are grouped by course so that
    multiple changes in the same course generate
    one action and one notification.

    Duplicate notifications are skipped automatically.
    """

    print("\n")
    print("#" * 70)
    print("PROCESSING EVENTS -> ACTIONS")
    print("#" * 70)

    action_count = 0

    # --------------------------------------------------------
    # New assignments
    # --------------------------------------------------------

    for assignment in events.get(
        "new_assignments",
        []
    ):

        if handle_new_assignment(
            assignment
        ):

            action_count += 1

    # --------------------------------------------------------
    # Changed assignments
    # --------------------------------------------------------

    for change in events.get(
        "changed_assignments",
        []
    ):

        action_count += handle_changed_assignment(
            change
        )

    # --------------------------------------------------------
    # New quizzes
    # --------------------------------------------------------

    for quiz in events.get(
        "new_quizzes",
        []
    ):

        if handle_new_quiz(
            quiz
        ):

            action_count += 1

    # --------------------------------------------------------
    # Changed quizzes
    # --------------------------------------------------------

    for change in events.get(
        "changed_quizzes",
        []
    ):

        action_count += handle_changed_quiz(
            change
        )

    # --------------------------------------------------------
    # Attendance changes
    # --------------------------------------------------------

    attendance_changes = events.get(
        "attendance_changes",
        []
    )

    grouped_attendance_changes = (
        group_attendance_changes_by_course(
            attendance_changes
        )
    )

    for course_changes in grouped_attendance_changes.values():

        if handle_attendance_changes(
            course_changes
        ):

            # One action for one course.
            action_count += 1

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print("\n" + "-" * 70)

    if action_count == 0:

        print(
            "No actions were required."
        )

    else:

        print(
            f"Total actions executed: "
            f"{action_count}"
        )

    return action_count


# ============================================================
# PRINT DETECTED EVENTS
# ============================================================

def print_events(events):
    """
    Print detected Moodle changes.

    Event detection is separate from action handling.
    """

    print("\n")
    print("#" * 70)
    print("DETECTED EVENTS")
    print("#" * 70)

    has_events = False

    # --------------------------------------------------------
    # New assignments
    # --------------------------------------------------------

    for assignment in events[
        "new_assignments"
    ]:

        has_events = True

        print("\nNEW ASSIGNMENT")

        print(
            f"Course: "
            f"{assignment.get('course')}"
        )

        print(
            f"Name: "
            f"{assignment.get('name')}"
        )

        print(
            f"Due: "
            f"{assignment.get('due')}"
        )

        print(
            f"URL: "
            f"{assignment.get('url')}"
        )

    # --------------------------------------------------------
    # Changed assignments
    # --------------------------------------------------------

    for change in events[
        "changed_assignments"
    ]:

        has_events = True

        assignment = change[
            "assignment"
        ]

        print("\nASSIGNMENT CHANGED")

        print(
            f"Course: "
            f"{assignment.get('course')}"
        )

        print(
            f"Name: "
            f"{assignment.get('name')}"
        )

        for field_change in change[
            "changes"
        ]:

            print(
                f"{field_change['field']}: "
                f"{field_change['old']} "
                f"-> "
                f"{field_change['new']}"
            )

    # --------------------------------------------------------
    # New quizzes
    # --------------------------------------------------------

    for quiz in events[
        "new_quizzes"
    ]:

        has_events = True

        print("\nNEW QUIZ")

        print(
            f"Course: "
            f"{quiz.get('course')}"
        )

        print(
            f"Name: "
            f"{quiz.get('name')}"
        )

        print(
            f"Opened: "
            f"{quiz.get('opened')}"
        )

        print(
            f"Closed: "
            f"{quiz.get('closed')}"
        )

        print(
            f"URL: "
            f"{quiz.get('url')}"
        )

    # --------------------------------------------------------
    # Changed quizzes
    # --------------------------------------------------------

    for change in events[
        "changed_quizzes"
    ]:

        has_events = True

        quiz = change[
            "quiz"
        ]

        print("\nQUIZ CHANGED")

        print(
            f"Course: "
            f"{quiz.get('course')}"
        )

        print(
            f"Name: "
            f"{quiz.get('name')}"
        )

        for field_change in change[
            "changes"
        ]:

            print(
                f"{field_change['field']}: "
                f"{field_change['old']} "
                f"-> "
                f"{field_change['new']}"
            )

    # --------------------------------------------------------
    # Attendance changes
    # --------------------------------------------------------

    for change in events[
        "attendance_changes"
    ]:

        has_events = True

        print("\nATTENDANCE CHANGE")

        print(
            f"Course: "
            f"{change.get('course')}"
        )

        print(
            f"Type: "
            f"{change.get('type')}"
        )

        print(
            f"Old: "
            f"{change.get('old')}"
        )

        print(
            f"New: "
            f"{change.get('new')}"
        )

    # --------------------------------------------------------
    # No events
    # --------------------------------------------------------

    if not has_events:

        print(
            "\nNo new events or changes detected."
        )


# ============================================================
# PHASE 4B - REMINDER POLICY
# ============================================================

def _reminder_event_label(event_type):
    labels = {
        "assignment_added": "الواجب الجديد",
        "quiz_added": "الكويز الجديد",
        "attendance_opened": "فتح الحضور",
        "attendance_changed": "تحديث الحضور",
        "deadline_near": "موعد التسليم القريب",
    }
    return labels.get(str(event_type or ""), "التحديث الجامعي")


def build_event_reminder_message(event):
    """Build a short grounded reminder from the existing event payload."""
    payload = event.get("payload") or {}
    label = _reminder_event_label(event.get("type"))
    name = payload.get("name")
    course = payload.get("course_name") or payload.get("course")

    pieces = [f"تذكير: لسه ما أكدتلي إنك شفت {label}"]
    if name:
        pieces.append(str(name))
    if course:
        pieces.append(f"— {course}")
    pieces.append("إذا شفته، ابعثلي: شفت الإشعار.")
    return " ".join(pieces)


def process_due_event_reminders(now=None):
    """Send due reminders for important sent-but-unacknowledged events.

    This intentionally does not create a new AgentEvent.  A reminder belongs to
    the original event and its delivery history is persisted on that event.
    """
    due_events = _event_state.due_reminder_events(
        REMINDER_POLICIES,
        now=now,
    )

    if not due_events:
        return 0

    sent_count = 0
    for event in due_events:
        event_id = event.get("id")
        if not event_id:
            continue

        channel = event.get("notification_channel") or NOTIFICATION_CHANNEL
        message = build_event_reminder_message(event)

        print("\n" + "-" * 70)
        print("PHASE 4B REMINDER")
        print("-" * 70)
        print(f"Event ID: {event_id}")
        print(f"Event type: {event.get('type')}")
        print(f"Reminder count: {event.get('reminder_count', 0)}")

        try:
            success = bool(send_notification(
                "REMINDER",
                message,
                channel=channel,
            ))
        except Exception as error:
            print(f"Reminder send error: {error}")
            success = False

        _event_state.mark_event_reminder(
            event_id,
            "sent" if success else "failed",
            channel=channel,
        )
        if success:
            sent_count += 1

    return sent_count


# ============================================================
# RUN ONE MONITORING CHECK
# ============================================================

def run_monitoring_check():
    """
    Run one complete monitoring cycle.
    """

    print("\n")
    print("=" * 70)
    print("UNIVERSITY AI AGENT - MONITORING CHECK")
    print("=" * 70)

    print(
        f"Time: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    old_snapshot = load_snapshot()

    new_snapshot = collect_current_state()

    if new_snapshot is None:

        print(
            "\nMonitoring check failed."
        )

        return False

    # --------------------------------------------------------
    # First run
    # --------------------------------------------------------

    if not old_snapshot.get(
        "last_checked"
    ):

        print(
            "\nFirst monitoring run detected."
        )

        print(
            "Creating the initial snapshot."
        )

        save_snapshot(
            new_snapshot
        )

        print(
            "\nNo new Moodle diff events will be reported "
            "during the first run."
        )

        # Existing EventState reminders are independent from the Moodle
        # snapshot baseline, so a monitor restart must not lose them.
        process_due_event_reminders()

        return True

    # --------------------------------------------------------
    # Compare
    # --------------------------------------------------------

    events = compare_snapshots(
        old_snapshot,
        new_snapshot
    )

    # --------------------------------------------------------
    # Print detected events
    # --------------------------------------------------------

    print_events(
        events
    )

    # --------------------------------------------------------
    # Event -> Action
    # --------------------------------------------------------

    handle_events(
        events
    )

    # --------------------------------------------------------
    # Reminder policy for previously sent but unseen events
    # --------------------------------------------------------

    process_due_event_reminders()

    # --------------------------------------------------------
    # Save new state
    # --------------------------------------------------------

    save_snapshot(
        new_snapshot
    )

    return True


# ============================================================
# CONTINUOUS MONITORING LOOP
# ============================================================

def start_monitoring():
    """
    Keep monitoring Moodle continuously.

    Press Ctrl+C to stop.
    """

    print("\n")
    print("=" * 70)
    print("UNIVERSITY AI AGENT - AUTONOMOUS MONITOR")
    print("=" * 70)

    print(
        f"\nCheck interval: "
        f"{CHECK_INTERVAL} seconds"
    )

    print(
        "\nPress Ctrl+C to stop monitoring."
    )

    while True:

        try:

            run_monitoring_check()

            print("\n" + "-" * 70)

            print(
                f"Next check in "
                f"{CHECK_INTERVAL} seconds..."
            )

            print("-" * 70)

            time.sleep(
                CHECK_INTERVAL
            )

        except KeyboardInterrupt:

            print(
                "\n\nMonitoring stopped by user."
            )

            break

        except Exception as error:

            print(
                "\nUnexpected monitoring error:"
            )

            print(error)

            print(
                f"\nThe monitor will retry "
                f"after {CHECK_INTERVAL} seconds."
            )

            time.sleep(
                CHECK_INTERVAL
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    start_monitoring()
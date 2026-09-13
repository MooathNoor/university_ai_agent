"""Phase 4C conversational presence-confirmation tests.

These tests are deterministic/offline. They validate the safety-sensitive bridge
between a Telegram-style natural reply and the exact pending action/event.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types

# Offline import shims used only if optional runtime modules are unavailable.
if "ollama" not in sys.modules:
    fake_ollama = types.ModuleType("ollama")
    def _offline_chat(*args, **kwargs):
        raise RuntimeError("Ollama was called in an offline deterministic regression path")
    fake_ollama.chat = _offline_chat
    sys.modules["ollama"] = fake_ollama

if "moodle_tools" not in sys.modules:
    fake_moodle_tools = types.ModuleType("moodle_tools")
    fake_moodle_tools.get_all_assignments = lambda: []
    fake_moodle_tools.get_all_quizzes = lambda: []
    sys.modules["moodle_tools"] = fake_moodle_tools

from event_state import EventState
import main
import monitor


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


_count = 0

def ok(condition, message):
    global _count
    check(condition, message)
    _count += 1


def add_presence_watch(state, *, course_id, course_name, request, action_type="register_attendance"):
    action = state.add_pending_action(
        trigger_type="attendance_opened",
        filters={"course_id": course_id},
        requested_action=action_type,
        notify=True,
        original_request=request,
        authorization_required=True,
        authorized=True,
        authorization_source="explicit_user_request",
        presence_required=True,
    )
    event_result = state.record_event(
        "attendance_opened",
        {
            "course_id": course_id,
            "course_name": course_name,
            "status": "Open",
        },
    )
    return action, event_result["event"]


old_main_state = main._event_state
old_monitor_state = monitor._event_state
old_retry = main._retry_verified_pending_action

try:
    # ------------------------------------------------------------------
    # 1. No pending presence request: presence wording is not hijacked.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        main._event_state = state
        response = main._handle_presence_confirmation_control("انا موجود بالمحاضرة")
        ok(response is None, "presence wording is ignored when no presence request is waiting")

    # ------------------------------------------------------------------
    # 2. One candidate: explicit positive presence binds exact event.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        main._event_state = state
        action, event = add_presence_watch(
            state,
            course_id=1695,
            course_name="PRINCIPLES OF NUMERICAL ANALYSIS",
            request="اول ما يفتح الحضور بالتحليل العددي سجلني حاضر",
        )

        retry_calls = []
        def fake_retry(event_id, action_id):
            retry_calls.append((event_id, action_id))
            return {
                "status": "blocked",
                "message": "Action 'register_attendance' is not registered.",
            }
        main._retry_verified_pending_action = fake_retry

        response = main._handle_presence_confirmation_control("اه انا بالمحاضرة")
        ok(response is not None, "explicit natural presence reply is handled")
        ok(retry_calls == [(event["id"], action["id"])], "presence retry targets exact event and pending action")

        snapshot = state.snapshot(max_events=20, max_actions=20)
        saved = next(x for x in snapshot["pending_actions"] if x["id"] == action["id"])
        saved_event = next(x for x in snapshot["recent_events"] if x["id"] == event["id"])
        ok(saved["presence_confirmed"] is True, "positive reply persists presence confirmation")
        ok(saved["presence_confirmed_event_id"] == event["id"], "positive reply binds presence to exact event id")
        ok(saved_event["acknowledged"] is True, "presence reply acknowledges the same notification event")
        ok("ما سجلت حضورك" in response, "unregistered Moodle capability never claims attendance was recorded")

        # A generic social acknowledgement must not become presence proof.
        before = saved["presence_confirmed_at"]
        generic = main._presence_confirmation_intent("تمام")
        ok(generic is None, "generic social acknowledgement is not physical-presence proof")
        ok(main.get_fast_conversation_response("تمام") is not None, "generic acknowledgement remains on social fast path")

    # ------------------------------------------------------------------
    # 3. Bare yes is allowed only in the presence-request context.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        main._event_state = state
        action, event = add_presence_watch(
            state,
            course_id=1695,
            course_name="NUMERICAL ANALYSIS",
            request="اذا فتح الحضور سجلني",
        )
        main._retry_verified_pending_action = lambda e, a: {
            "status": "blocked",
            "message": "Action 'register_attendance' is not registered.",
        }
        response = main._handle_presence_confirmation_control("اه")
        ok(response is not None, "bare yes is accepted when exactly one presence request is waiting")
        saved = next(x for x in state.snapshot()["pending_actions"] if x["id"] == action["id"])
        ok(saved["presence_confirmed_event_id"] == event["id"], "bare yes still binds only to the waiting event")

    # ------------------------------------------------------------------
    # 4. Negative reply clears presence and never retries mutation.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        main._event_state = state
        action, event = add_presence_watch(
            state,
            course_id=1695,
            course_name="NUMERICAL ANALYSIS",
            request="اذا فتح الحضور سجلني",
        )
        state.set_pending_action_presence_confirmation(action["id"], True, event_id=event["id"])
        retry_calls = []
        main._retry_verified_pending_action = lambda e, a: retry_calls.append((e, a))

        response = main._handle_presence_confirmation_control("لا مش موجود بالمحاضرة")
        saved = next(x for x in state.snapshot()["pending_actions"] if x["id"] == action["id"])
        ok(saved["presence_confirmed"] is False, "negative presence reply clears confirmation")
        ok(saved["presence_confirmed_event_id"] is None, "negative reply removes event presence binding")
        ok(retry_calls == [], "negative presence reply never retries state mutation")
        ok("ما رح أنفذ تسجيل حضور" in response, "negative reply states that attendance will not be registered")

    # ------------------------------------------------------------------
    # 5. Multiple candidates: bare yes must not guess.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        main._event_state = state
        a1, e1 = add_presence_watch(
            state,
            course_id=1695,
            course_name="NUMERICAL ANALYSIS",
            request="سجلني بالتحليل العددي لما يفتح الحضور",
        )
        a2, e2 = add_presence_watch(
            state,
            course_id=1194,
            course_name="CLOUD COMPUTING",
            request="سجلني بالحوسبة لما يفتح الحضور",
        )
        retry_calls = []
        main._retry_verified_pending_action = lambda e, a: retry_calls.append((e, a))

        response = main._handle_presence_confirmation_control("اه")
        ok("أكثر من طلب حضور" in response, "ambiguous bare yes asks for course clarification")
        ok(retry_calls == [], "ambiguous presence reply never chooses an action randomly")

        response = main._handle_presence_confirmation_control("اه انا موجود بالحوسبة")
        ok(response is not None, "course-qualified presence reply resolves one candidate")
        saved1 = next(x for x in state.snapshot()["pending_actions"] if x["id"] == a1["id"])
        saved2 = next(x for x in state.snapshot()["pending_actions"] if x["id"] == a2["id"])
        ok(saved1["presence_confirmed"] is False, "unmentioned course remains unconfirmed")
        ok(saved2["presence_confirmed_event_id"] == e2["id"], "course-qualified reply confirms correct event only")

    # ------------------------------------------------------------------
    # 6. Monitor notification explains the presence requirement naturally.
    # ------------------------------------------------------------------
    note = monitor.verified_action_note([
        {
            "action_type": "register_attendance",
            "status": "blocked",
            "message": "Action 'register_attendance' is not registered.",
            "authorized": True,
            "presence_required": True,
            "presence_confirmed": False,
        }
    ])
    ok("تأكدلي إنك موجود فعليًا" in note, "attendance notification explicitly asks for real presence")
    ok("أنا موجود بالمحاضرة" in note, "attendance notification gives a natural confirmation example")

    # ------------------------------------------------------------------
    # 7. Real retry bridge uses exact saved event/action and verification gate.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        state = EventState(os.path.join(tmp, "state.json"))
        monitor._event_state = state
        action, event = add_presence_watch(
            state,
            course_id=1695,
            course_name="NUMERICAL ANALYSIS",
            request="سجلني بالحضور",
            action_type="presence_retry_demo",
        )
        state.set_pending_action_presence_confirmation(
            action["id"],
            True,
            event_id=event["id"],
        )

        monitor.register_verified_action(
            "presence_retry_demo",
            lambda payload: {"status": "executed", "message": "demo executed"},
            lambda payload: {"status": "verified", "message": "demo verified"},
            requires_authorization=True,
            requires_presence=True,
        )

        result = monitor.retry_pending_action_for_event(event["id"], action["id"])
        ok(result["status"] == "success", "retry bridge reaches verified runner after presence confirmation")
        ok(result["verification_status"] == "verified", "retry bridge still requires fresh verification")
        ok(not state.snapshot()["pending_actions"], "verified retry completes one-shot pending action")

        mismatch = monitor.retry_pending_action_for_event("wrong_event", action["id"])
        ok(mismatch["status"] == "blocked", "retry bridge fails closed for wrong event identity")

finally:
    main._event_state = old_main_state
    monitor._event_state = old_monitor_state
    main._retry_verified_pending_action = old_retry


print()
print(f"PASS: {_count} Phase 4C presence-conversation assertions")

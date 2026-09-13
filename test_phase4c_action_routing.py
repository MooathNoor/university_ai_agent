import sys
import types

# This unit test never calls Ollama. Provide a tiny import stub so the test can
# run in environments where the optional local Ollama package is unavailable.
if "ollama" not in sys.modules:
    ollama_stub = types.ModuleType("ollama")
    ollama_stub.chat = lambda *args, **kwargs: None
    sys.modules["ollama"] = ollama_stub

if "moodle_tools" not in sys.modules:
    moodle_tools_stub = types.ModuleType("moodle_tools")
    moodle_tools_stub.get_all_assignments = lambda: []
    moodle_tools_stub.get_all_quizzes = lambda: []
    sys.modules["moodle_tools"] = moodle_tools_stub

import main
from agent_core import AgentCore


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


assertions = 0


def ok(condition, message):
    global assertions
    check(condition, message)
    assertions += 1


# Keep this test independent from real Moodle/Ollama.
original_fast = main._fast_semantic_analysis
original_load_courses = main.load_courses

try:
    main._fast_semantic_analysis = lambda text: {
        "is_university_request": True,
        "intents": ["attendance"] if "حضور" in main.normalize_text(text) else ["quizzes"],
        "course_queries": [],
        "selection": "all",
        "count": None,
        "multiple_courses": False,
    }
    main.load_courses = lambda: []

    # ------------------------------------------------------------
    # 1. Normal notification-only watch keeps the fast path.
    # ------------------------------------------------------------
    message = "لو نزل كويز جديد بلغني مباشرة"
    ok(main._message_may_define_future_action(message), "notification watch is recognized as a future action")
    ok(main._future_watch_is_notification_only(message), "notification watch is classified read-only")

    decision = main._build_high_confidence_future_watch(message)
    ok(decision is not None, "notification-only watch still uses the fast path")
    ok(decision.action == "watch", "fast notification request remains a watch")
    ok(decision.requested_action == "notify", "fast notification request preserves requested_action=notify")

    # ------------------------------------------------------------
    # 2. State-changing attendance request must NOT be downgraded.
    # ------------------------------------------------------------
    mutation = "اول ما يفتح الحضور سجلني حاضر وابعتلي تاكيد"
    ok(main._message_may_define_future_action(mutation), "state-changing request is recognized as a future action")
    ok(not main._future_watch_is_notification_only(mutation), "state-changing request is not classified as notify-only")
    ok(
        main._build_high_confidence_future_watch(mutation) is None,
        "state-changing request bypasses the notify-only fast compiler",
    )

    # ------------------------------------------------------------
    # 3. Other mutation classes are also fail-safe.
    # ------------------------------------------------------------
    ok(
        not main._future_watch_is_notification_only("لما ينزل الواجب سلمه"),
        "submission-like request is not downgraded to notify",
    )
    ok(
        not main._future_watch_is_notification_only("when it opens execute the action"),
        "English execution request is not downgraded to notify",
    )

finally:
    main._fast_semantic_analysis = original_fast
    main.load_courses = original_load_courses


# ------------------------------------------------------------
# 4. AgentCore sanitizer preserves structural requested actions.
# ------------------------------------------------------------
core = AgentCore(lambda **kwargs: None, "test-model")

decision = core._validate({
    "action": "watch",
    "tool": None,
    "course_ref": "Numerical Analysis",
    "refresh": False,
    "response_goal": "register attendance when it opens",
    "clarification": "",
    "confidence": 0.95,
    "reason": "future state-changing request",
    "answer": "",
    "trigger_type": "attendance_opened",
    "event_filters": {"course_ref": "Numerical Analysis"},
    "requested_action": "register_attendance",
    "notify": True,
})

ok(decision.action == "watch", "AgentCore keeps state-changing future request as watch")
ok(
    decision.requested_action == "register_attendance",
    "AgentCore preserves structural requested_action instead of forcing notify",
)

print()
print(f"PASS: {assertions} Phase 4C action-routing assertions")

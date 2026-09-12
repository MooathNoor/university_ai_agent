"""Offline regression tests for University AI Agent conversation routing/state.

These tests intentionally replace Moodle/Ollama with deterministic fakes. They
validate routing, context isolation and output constraints without touching the
student's real Moodle account.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

COURSES = [
    {"id": 1695, "fullname": "2026/2025-3-30801281-PRINCIPLES OF NUMERICAL ANALYSIS-1"},
    {"id": 1194, "fullname": "2026/2025-3-30801361-CLOUD COMPUTING-1"},
    {"id": 1499, "fullname": "2026/2025-3-IOT 456-ROBOTICS AND AUTONOMOUS SYSTEMS .-1"},
]

CLOUD = COURSES[1]["fullname"]
NUM = COURSES[0]["fullname"]
ROBOT = COURSES[2]["fullname"]

QUIZZES = {
    CLOUD: [
        {"name": "Quizz1", "url": "https://x/mod/quiz/view.php?id=1"},
        {"name": "Quiz2", "url": "https://x/mod/quiz/view.php?id=2"},
    ],
    NUM: [],
    ROBOT: [
        {"name": "Quiz1", "url": "https://x/mod/quiz/view.php?id=3"},
        {"name": "Quiz 2", "url": "https://x/mod/quiz/view.php?id=4"},
        {"name": "Quiz 3", "url": "https://x/mod/quiz/view.php?id=5", "time_limit": "5 mins", "attempts_allowed": "1"},
    ],
}

ASSIGNMENTS = {
    NUM: [
        {"name": "13/7/2026 Assignment", "due_date": "Thursday, 16 July 2026, 8:00 PM", "description": "solve example 1", "url": "https://x/mod/assign/view.php?id=11"},
        {"name": "20/7/2026 Assignment", "due_date": "Thursday, 23 July 2026, 8:00 PM", "description": "solve example 2", "url": "https://x/mod/assign/view.php?id=12"},
        {"name": "26-7-2026 Assignment", "due_date": "Thursday, 30 July 2026, 8:00 PM", "description": "solve example 3", "url": "https://x/mod/assign/view.php?id=13"},
        {"name": "10/8/2026 Assignment", "due_date": "Thursday, 13 August 2026, 8:00 PM", "description": "solve unit 5", "url": "https://x/mod/assign/view.php?id=14"},
        {"name": "17/8/2026 Assignment", "due_date": "Thursday, 20 August 2026, 8:00 PM", "description": "solve example 3 in unit 6 derivation الحل بخط اليد فقط", "url": "https://x/mod/assign/view.php?id=15"},
    ],
    CLOUD: [
        {"name": "Public vs Private Assignment", "due_date": "Tuesday, 21 July 2026, 12:00 AM", "description": "Compare public and private cloud", "url": "https://x/mod/assign/view.php?id=20"},
        {"name": "Virtualization Assignment", "due_date": "Tuesday, 28 July 2026, 12:00 AM", "description": "Divide 16 GB RAM and 8 CPU cores equally across 4 virtual machines", "url": "https://x/mod/assign/view.php?id=21"},
        {"name": "Cloud Security Assignment", "due_date": "Sunday, 23 August 2026, 12:00 AM", "description": "Discuss cloud security", "url": "https://x/mod/assign/view.php?id=22"},
    ],
    ROBOT: [],
}


def _course_name(course):
    return course.get("fullname") or course.get("name") or ""


def _course_id(course):
    return course.get("id")


def _fake_quizzes(course_name=None):
    if course_name is None:
        out = []
        for name, items in QUIZZES.items():
            cid = next(c["id"] for c in COURSES if c["fullname"] == name)
            for item in items:
                out.append({**item, "course_name": name, "course_id": cid})
        return out
    return [dict(x) for x in QUIZZES.get(course_name, [])]


def _fake_assignments(course_name=None):
    if course_name is None:
        out = []
        for name, items in ASSIGNMENTS.items():
            cid = next(c["id"] for c in COURSES if c["fullname"] == name)
            for item in items:
                out.append({**item, "course_name": name, "course_id": cid})
        return out
    return [dict(x) for x in ASSIGNMENTS.get(course_name, [])]


def _fake_quiz_grades(course_name=None, quizzes=None):
    items = [dict(x) for x in (quizzes or _fake_quizzes(course_name))]
    marks = {"Quizz1": (10, 10), "Quiz2": (10, 10), "Quiz1": (None, None), "Quiz 2": (4, 5), "Quiz 3": (4, 5)}
    for item in items:
        grade, max_grade = marks.get(item.get("name"), (None, None))
        item["grade"] = grade
        item["max_grade"] = max_grade
        item["grade_state"] = "graded" if grade is not None else "unknown"
    return items


def load_agent():
    fake_tools = types.ModuleType("tools")
    fake_tools.get_attendance = lambda course_name: {"status": "Success", "summary": {"Taken sessions:": "0"}, "sessions": []}
    fake_tools.get_course_schedule = lambda course_name: {"status": "Success", "course": course_name}
    fake_tools.get_course_info = lambda course_name: {"status": "Success", "course": course_name}
    def _fake_resources(course_name):
        if course_name == NUM:
            return [
                {"name": "Unit 6.pdf", "type": "resource", "url": "https://x/mod/resource/view.php?id=51", "course": NUM, "course_id": 1695},
                {"name": "Lecture meeting", "type": "url", "url": "https://meet.example/lecture", "course": NUM, "course_id": 1695},
            ]
        return []
    fake_tools.get_course_resources = _fake_resources
    fake_tools.get_my_courses = lambda: {"status": "Success", "courses": COURSES}
    fake_tools.get_assignments = _fake_assignments
    fake_tools.get_announcements = lambda: {"status": "Unavailable"}
    fake_tools.get_quizzes = _fake_quizzes
    fake_tools.get_quiz_grades = _fake_quiz_grades
    fake_tools.get_upcoming_deadlines = lambda: []
    fake_tools.get_pending_work = lambda: {"status": "Success", "has_pending": False, "pending": []}
    fake_tools.get_cached_courses = lambda: COURSES
    fake_tools.get_course_name = _course_name
    fake_tools.get_course_id = _course_id
    sys.modules["tools"] = fake_tools

    fake_ollama = types.ModuleType("ollama")
    def forbidden_chat(*args, **kwargs):
        raise AssertionError("Ollama was called in an offline deterministic regression path")
    fake_ollama.chat = forbidden_chat
    sys.modules["ollama"] = fake_ollama

    spec = importlib.util.spec_from_file_location("agent_under_test", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    temp_dir = tempfile.mkdtemp()
    module.COURSE_SEMANTIC_INDEX_FILE = os.path.join(temp_dir, "course_semantic_index.json")
    module.LEARNED_RULES_FILE = os.path.join(temp_dir, "agent_learned_rules.json")
    module._event_state.path = os.path.join(temp_dir, "agent_event_state.json")
    module._event_state.reset()
    module._course_index_cache = {"fingerprint": None, "profiles": None}
    module.clear_context()
    return module


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    m = load_agent()

    # Referential words must never become a course reference/alias.
    for text in ["كم علاماتي فيهم", "شو فيهم", "منهم", "هذول", "هاي"]:
        check(m._extract_course_reference(text) == "", f"reference leak: {text!r} -> {m._extract_course_reference(text)!r}")
    check(m._valid_profile_phrase("فيهم") is None, "pronoun could become trusted alias")

    # Yes/no output constraints work with or without 'فقط'.
    check(m._response_style("جاوب اه او لا")["yes_no_only"], "yes/no without فقط not detected")
    check(m._response_style("جاوب اه او لا فقط")["yes_no_only"], "yes/no with فقط not detected")

    # Common Arabic course names resolve locally; no Ollama call allowed here.
    check(_course_id(m.resolve_courses("مادة الحوسبة السحابية كم كويز؟")[0]) == 1194, "Cloud Arabic alias failed")
    check(_course_id(m.resolve_courses("اخر واجب بماده التحليل العددي شو هو")[0]) == 1695, "Numerical Arabic alias failed")
    check(_course_id(m.resolve_courses("كم كويز بمادة الروبوتكس؟")[0]) == 1499, "Robotics Arabic alias failed")

    # Cloud count must update BOTH active course and last result set.
    m.clear_context()
    r = m.process_user_message("مادة الحوسبة السحابيه كم كويز يوجد؟")
    check(r == "عدد الكويزات: 2", f"unexpected cloud count: {r}")
    check(str(m._conversation_state["active_course"]["id"]) == "1194", "count did not set active Cloud course")
    check(len(m._last_result_items("quiz")) == 2, "count did not retain two Cloud quizzes")
    check(all(str(x.get("course_id")) == "1194" for x in m._last_result_items("quiz")), "quiz result set mixed courses")

    # Pronoun follow-up must reuse the grounded Cloud list and never call Ollama.
    r = m.process_user_message("كم علاماتي فيهم")
    check("Quizz1" in r and "Quiz2" in r, f"Cloud grade follow-up missing quizzes: {r}")
    check("Quiz 3" not in r and "Quiz 2" not in r, f"Robot quizzes leaked into Cloud grades: {r}")
    check(str(m._conversation_state["active_course"]["id"]) == "1194", "grade follow-up changed active course")

    # Explicit course switch must clear old quiz result-set and ground Numerical.
    r = m.process_user_message("كم واجب في مادة التحليل العددي؟")
    check(r == "عدد الواجبات: 5", f"wrong Numerical assignment count: {r}")
    check(str(m._conversation_state["active_course"]["id"]) == "1695", "explicit Numerical switch failed")
    check(m._conversation_state["last_result_set"]["type"] == "assignment", "old quiz result set survived course switch")

    # Follow-up selection/details stay on Numerical.
    r = m.process_user_message("اخر واجب شو هو")
    check("17/8/2026 Assignment" in r and "NUMERICAL ANALYSIS" in r, f"latest Numerical assignment failed: {r}")
    r = m.process_user_message("شو مطلوب مني")
    check("solve example 3 in unit 6" in r, f"assignment details did not reuse selected entity: {r}")
    check("Cloud Security" not in r, "Cloud assignment leaked into Numerical context")

    # Capability question must not execute Ollama/solution generation.
    r = m.process_user_message("بتقدر تساعدني بحله جاوب اه او لا")
    check(r == "اه", f"capability yes/no failed: {r}")
    r = m.enforce_response_style("بتقدر تساعدني بحله جاوب اه او لا", r)
    check(r == "اه", "response-style enforcement altered yes/no capability answer")

    # Explicit Cloud grade request should resolve locally and show Cloud only.
    m.clear_context()
    r = m.process_user_message("كوزات مادة الحوسبة السحابيه كم علاماتي فيهم")
    check("Quizz1" in r and "Quiz2" in r and "Quiz 3" not in r, f"explicit Cloud grades failed: {r}")

    # Dialect/attached-prefix variants from real logs resolve locally.
    m.clear_context()
    r = m.process_user_message("كم كويز عندي بلحوسبة؟")
    check(r == "عدد الكويزات: 2", f"attached-prefix Cloud failed: {r}")
    r = m.process_user_message("علامات الكلاود فقط")
    check("Quizz1" in r and "Quiz2" in r, f"Cloud transliteration failed: {r}")

    m.clear_context()
    r = m.process_user_message("في عندي كوزات موجوده بمادة التحليل العددي؟")
    check(r == "ما لقيت كويزات.", f"Numerical colloquial quiz lookup failed: {r}")

    # Intent inheritance with a newly named course must switch course, not inherit it.
    r = m.process_user_message("والحوسبة كمان")
    check("Quizz1" in r and "Quiz2" in r, f"new-course inherited-intent follow-up failed: {r}")
    check(str(m._conversation_state["active_course"]["id"]) == "1194", "follow-up failed to switch to Cloud")

    # A genuinely unknown alias can be clarified once, learned, and rerun without a loop.
    m.clear_context()
    r = m.process_user_message("كم كويز بمادة الزد؟")
    check("اختار المادة المقصودة" in r, f"unknown alias did not ask for clarification: {r}")
    r = m.process_user_message("2")
    check(r == "عدد الكويزات: 2", f"clarification learning loop regression: {r}")

    # The exact real follow-up that previously fell back to assignment_details
    # must stay in solve_assignment and ask for the missing referenced content.
    m.clear_context()
    r = m.process_user_message("اخر واجب بماده التحليل العددي شو هو")
    check("17/8/2026 Assignment" in r, f"could not reground Numerical assignment: {r}")
    r = m.process_user_message("طيب يلا حله وارسلي الاجابابت")
    check("Unit 6 / Example 3" in r and "صورة أو ملف" in r, f"solve follow-up did not request missing source: {r}")
    r = m.process_user_message("طيب عشان تحللي اياه شو بدك اساعدك؟")
    check("Unit 6 / Example 3" in r and "صورة أو ملف" in r, f"help-to-solve follow-up escaped assignment context: {r}")

    # Teach Mode: explicit intent aliases persist and affect future routing.
    r = m.process_user_message("علمك: لما احكي خلصه قصدي حل الواجب")
    check("solve_assignment" in r, f"intent teaching failed: {r}")
    r = m.process_user_message("خلصه")
    check("Unit 6 / Example 3" in r, f"learned solve phrase was not applied: {r}")

    # Teach Mode: course aliases are verified against actual Moodle courses.
    r = m.process_user_message("علمك: السحابه = Cloud Computing")
    check("CLOUD COMPUTING" in r, f"course teaching failed: {r}")
    check(_course_id(m.resolve_courses("كم كويز بالسحابه؟")[0]) == 1194, "learned course alias did not resolve Cloud")

    # Learned rules can be inspected and deleted by stable rule id.
    listing = m.process_user_message("شو علمتك؟")
    check("خلصه" in listing and "السحابه" in listing, f"learned-rule listing failed: {listing}")
    data = m._load_learned_rules()
    solve_rule = next(rule for rule in data["rules"] if rule.get("type") == "intent_alias")
    r = m.process_user_message(f"احذف القاعدة {solve_rule['id']}")
    check("حذفت القاعدة" in r, f"learned-rule deletion failed: {r}")
    check(all(rule.get("id") != solve_rule["id"] for rule in m._load_learned_rules()["rules"]), "deleted rule still persisted")

    # Invalid targets must fail closed rather than poisoning persistent routing.
    before = len(m._load_learned_rules()["rules"])
    r = m.process_user_message("علمك: ايشي = اخترعلي علامات")
    check("ما حفظت القاعدة" in r, f"unsafe/unknown teaching target was accepted: {r}")
    check(len(m._load_learned_rules()["rules"]) == before, "invalid learned rule was persisted")

    # Pending work yes/no remains compact and does not require a course.
    r = m.process_user_message("هل يوجد اي واجب او كويز حاليا لم اقم بحله جاوبني باه او لا فقط")
    check(r == "لا", f"pending-work yes/no regression: {r}")

    # Real-user conversational QA: cheap social turns must never reach Ollama/Moodle routing.
    m.clear_context()
    r = m.process_user_message("مرحبا")
    check("كيف فيني أساعدك اليوم" in r, f"greeting fast-path failed: {r}")
    r = m.process_user_message("عرفني بنفسك وشو انت بتقدر تساعدني")
    check("وكيلك الجامعي" in r and "الحضور" in r and "Moodle" not in r, f"identity/capability intro failed: {r}")

    # Assignment capability question without an explicit 'yes/no' constraint must
    # answer capability, not execute solve or fall into the slow semantic model.
    r = m.process_user_message("اخر واجب بماده التحليل العددي شو هو")
    check("17/8/2026 Assignment" in r, f"assignment setup failed: {r}")
    r = m.process_user_message("هل يمكنك حله بطريقه مناسبه للمطلوب؟")
    check(r.startswith("اه، بقدر"), f"natural assignment capability question failed: {r}")

    # Exact attendance sequence from the Telegram log. Predicates such as
    # 'اشي فعال' / 'خانه الحضور فعاله' must never become course aliases.
    r = m.process_user_message("طيب هل يوجد خانه حضور فعاله بماده التحليل العددي")
    check(r == "اه", f"explicit attendance activity existence failed: {r}")
    check(str(m._conversation_state["active_course"]["id"]) == "1695", "attendance did not ground Numerical")
    r = m.process_user_message("جاوبني في اشي فعال اه او لا فقط")
    check(r == "اه", f"attendance yes/no follow-up failed: {r}")
    check(m._extract_course_reference("جاوبني في اشي فعال اه او لا فقط") == "", "attendance predicate leaked as course reference")
    r = m.process_user_message("طيب حاليا خانه الحضور فعاله جاوبني ب اه او لا فقط")
    check(r == "اه", f"attendance active follow-up failed: {r}")
    check(m._arbitrate_intents("طيب حاليا خانه الحضور فعاله جاوبني ب اه او لا فقط", ["quizzes", "assignments", "attendance"]) == ["attendance"], "attendance arbitration did not suppress fuzzy false intents")

    # Result-set refinement must operate on the current resource list and never
    # treat editing language as a new course name.
    r = m.process_user_message("طيب بدي ترسلي ملفات ماده التحليل العددي كلهم")
    check("Unit 6.pdf" in r and "Lecture meeting" in r, f"course resources setup failed: {r}")
    r = m.process_user_message("احدف روابط المحاضرات وخلي الماده بس")
    check("Unit 6.pdf" in r and "Lecture meeting" not in r, f"resource refinement failed: {r}")
    check(m._extract_course_reference("احدف روابط المحاضرات وخلي الماده بس") == "", "resource edit wording leaked as course reference")

    # Two-turn Teach Mode starter must preempt inherited course intent/scoring.
    r = m.process_user_message("طيب بدي اعلمك ركز معي")
    check("احكيلي شو بدك تعلمني" in r, f"teach-mode starter failed: {r}")
    check(m._conversation_state.get("teach_waiting") is True, "teach-mode waiting state was not armed")
    # An unclear next teaching turn fails safely and exits waiting state.
    r = m.process_user_message("خلي ردودك مرتبه")
    check("احكيها بشكل أوضح" in r, f"unclear two-turn teaching did not fail safely: {r}")
    check(m._conversation_state.get("teach_waiting") is False, "teach-mode waiting state did not clear")

    # Predicted natural variants from the same manual-testing style.
    for greeting in ["هلا", "اهلا", "السلام عليكم", "صباح الخير", "hi"]:
        rr = m.process_user_message(greeting)
        check("أساعدك اليوم" in rr, f"greeting variant escaped fast path: {greeting!r} -> {rr}")

    for intro in ["مين انت وشو بتعمل", "شو امكانياتك", "كيف بتساعدني"]:
        rr = m.process_user_message(intro)
        check("وكيلك الجامعي" in rr, f"identity variant escaped fast path: {intro!r} -> {rr}")

    # Attendance status wording stays exclusive and does not mutate the active course.
    m.clear_context()
    rr = m.process_user_message("هل في خانه حضور بماده التحليل العددي؟")
    check(rr == "اه", f"attendance existence variant failed: {rr}")
    for follow in ["هي فعاله؟", "الحضور فعال؟", "هل هو مفعل جاوب اه او لا"]:
        rr = m.process_user_message(follow)
        check(rr == "اه", f"attendance follow-up variant failed: {follow!r} -> {rr}")
        check(str(m._conversation_state["active_course"]["id"]) == "1695", "attendance follow-up changed active course")

    # A state word by itself after clearing context is not magically attendance.
    m.clear_context()
    check(not m._is_attendance_activity_question("هل هو فعال؟"), "generic active-state question became attendance without context")

    # Course-resource edit phrases are control language, not course aliases.
    for edit in ["شيل روابط المحاضرات", "بدون روابط", "الملفات بس"]:
        check(m._extract_course_reference(edit) == "", f"resource edit leaked course reference: {edit!r}")

    # Second real Telegram round: bare Teach Mode should arm immediately.
    m.clear_context()
    rr = m.process_user_message("علمك")
    check("احكيلي شو بدك تعلمني" in rr, f"bare teach command escaped to semantic routing: {rr}")
    check(m._conversation_state.get("teach_waiting") is True, "bare teach did not arm waiting state")
    # Consume the waiting state safely so later tests are independent.
    m.process_user_message("خلي ردودك مرتبه")


    # Resource ordinal follow-up must stay local and reuse the grounded list.
    m.clear_context()
    rr = m.process_user_message("اعطيني ملفات ماده التحليل العددي")
    check("Unit 6.pdf" in rr, f"resource setup for first-file follow-up failed: {rr}")
    rr = m.process_user_message("هات اول ملف فقط")
    check("Unit 6.pdf" in rr and "Lecture meeting" not in rr, f"first-file follow-up escaped context: {rr}")

    # Asking whether something is new/current must force a real refresh rather than
    # silently trusting a potentially stale course-workspace cache.
    check(m._force_refresh_requested("في واجب جديد حاليا؟"), "new assignment question did not request refresh")
    # "آخر ملف بس" must refine the already grounded resource result instead of
    # becoming course_info / a giant course-page response.
    m.clear_context()
    rr = m.process_user_message("اعطيني ملفات ماده التحليل العددي")
    check("Unit 6.pdf" in rr, f"resource setup failed: {rr}")
    rr = m.process_user_message("اخر ملف بس")
    check("Lecture meeting" in rr and len(rr) < 300, f"last-file follow-up did not stay on resources: {rr}")

    # Cross-course wording must bypass the course scorer and aggregate all courses.
    m.clear_context()
    rr = m.process_user_message("بدي ترسل جميع لكوزات لكل المواد الموجوده على الموقع وعلامات جمبهم")
    check("Quizz1" in rr and "Quiz 3" in rr, f"all-course quiz grades did not aggregate courses: {rr}")
    check("10 / 10" in rr and "4 / 5" in rr, f"all-course quiz grades missing marks: {rr}")
    check(m._extract_course_reference("ارسل جميع لكوزات وبجانبهم العلامات") == "", "all-course control words leaked as course reference")

    # Numeric garbage is never a learned course alias unless it is a valid active
    # clarification choice handled by the pending-choice parser.
    check(m._extract_course_reference("123") == "", "numeric-only turn leaked as course reference")

    # Social closing must preempt inherited university intent.
    rr = m.process_user_message("تم تصبح على خير")
    check("تصبح على خير" in rr, f"goodbye inherited stale university intent: {rr}")

    # "What's new" must be honest until the 24/7 monitor has a comparison state.
    rr = m.process_user_message("هل يوجد اي جديد على الموقع؟")
    check("سجل مقارنة" in rr and "24/7" in rr, f"what's-new question fabricated a course answer: {rr}")

    # Third real Telegram round: short social acknowledgement must remain local.
    m.clear_context()
    rr = m.process_user_message("ممتاز طيب")
    check(rr == "تمام أخوي 👌", f"social acknowledgement escaped local control: {rr}")

    # One sentence can explicitly name two courses. They must resolve as two
    # grounded courses and must never be merged/taught as one alias.
    m.clear_context()
    rr = m.process_user_message("احكيلي الحوسبه كم علاماتي فيهم والروبتات كمان")
    check("10 / 10" in rr and "4 / 5" in rr, f"two-course quiz grades failed: {rr}")
    resolved = m.resolve_courses("احكيلي الحوسبه كم علاماتي فيهم والروبتات كمان", allow_ai=False)
    resolved_ids = {str(m.get_course_id(course)) for course in resolved}
    check(resolved_ids == {"1194", "1499"}, f"two-course resolver failed: {resolved_ids}")
    check(m._pending_course_resolution is None, "two explicit courses incorrectly created clarification state")

    # Assignment object-context: natural requirement questions stay attached to
    # the already-grounded last assignment and never become course references.
    m.clear_context()
    rr = m.process_user_message("اخر واجب بماده التحليل العددي شو هو")
    check("17/8/2026 Assignment" in rr, f"assignment context setup failed: {rr}")
    rr = m.process_user_message("شو المطلوب")
    check("solve example 3 in unit 6" in rr, f"short assignment-details follow-up failed: {rr}")
    rr = m.process_user_message("طلب انو بخط اليد؟")
    check("بخط اليد فقط" in rr, f"handwriting requirement follow-up failed: {rr}")
    rr = m.process_user_message("هل المطلوب انو اكتب الواجب بخط اليد؟")
    check("بخط اليد فقط" in rr, f"natural handwriting question failed: {rr}")

    # Dynamic course workspace: ordinal selection must be applied exactly once.
    m.clear_context()
    rr = m.process_user_message("بدي الواجب الثاني لمادة الحوسبة السحابيه")
    check("Virtualization Assignment" in rr, f"second Cloud assignment failed: {rr}")
    check("Public vs Private" not in rr and "Cloud Security" not in rr, f"ordinal selection returned extra assignments: {rr}")
    check(str(m._conversation_state["active_course"]["id"]) == "1194", "ordinal selection lost Cloud context")

    # A direct follow-up about the selected assignment file must stay on the
    # grounded assignment and must never create a course-clarification alias.
    rr = m.process_user_message("طيب هات الملف الي معتمد على الواجب")
    check("رابط صفحة الواجب" in rr or "مرفقات" in rr or "ملفات" in rr, f"assignment-file follow-up escaped context: {rr}")
    check(m._pending_course_resolution is None, "assignment-file follow-up incorrectly started course clarification")

    # Monitoring capability is a local capability answer, not a live Moodle query.
    m.clear_context()
    rr = m.process_user_message("بتقدر تخبرني بكل تحديث بصير مثل ادا نزل واجب او كويز او تفعل الحضور؟")
    check("monitor" in rr.lower() or "التنبيه" in rr, f"monitoring capability did not use local fast path: {rr}")
    check(m._pending_course_resolution is None, "monitoring capability created course clarification")

    # Full real-world dialogue: list -> ordinal selection -> natural details.
    # These turns must remain entirely in grounded state and must never invoke
    # the course scorer or learn conversational predicates as course aliases.
    m.clear_context()
    rr = m.process_user_message("هات قائمة الواجبات لمادة التحليل العددي")
    check("13/7/2026 Assignment" in rr and "17/8/2026 Assignment" in rr, f"Numerical list setup failed: {rr}")
    rr = m.process_user_message("بدي ترسل ثالث واجب")
    check("26-7-2026 Assignment" in rr, f"state-first third assignment selection failed: {rr}")
    check(m._pending_course_resolution is None, "ordinal follow-up triggered course clarification")
    check(m._active_entity_item("assignment").get("name") == "26-7-2026 Assignment", "third assignment was not grounded as active entity")
    rr = m.process_user_message("شو بده ؟")
    check("solve example 3" in rr, f"short predicate assignment follow-up failed: {rr}")
    rr = m.process_user_message("اشرحلي الواجب شو بده ؟")
    check("solve example 3" in rr, f"natural assignment explanation follow-up failed: {rr}")
    learned_phrases = {m.normalize_text(rule.get("phrase")) for rule in m._load_learned_rules().get("rules", [])}
    check("ترسل ثالث" not in learned_phrases and "بده" not in learned_phrases, f"generic follow-up polluted course aliases: {learned_phrases}")

    # Simple greetings are pure conversation controls: no Moodle and no Ollama.
    m.clear_context()
    rr = m.process_user_message("مساء الخير")
    check("مرحبا" in rr, f"simple greeting did not use fast local path: {rr}")

    # High-confidence future watches must bypass Ollama completely.  The semantic
    # layer should compile assignment + course + notification into a structured
    # pending action even when the local planner is unavailable.
    m.clear_context()
    original_chat = m.ollama.chat
    def _watch_must_not_call_ollama(*args, **kwargs):
        raise AssertionError("Ollama should not be called for a high-confidence future watch")
    m.ollama.chat = _watch_must_not_call_ollama
    try:
        rr = m.process_user_message("لو الدكتور نزل واجب جديد بالحوسبة السحابية بلغني مباشرة")
    finally:
        m.ollama.chat = original_chat
    check("حفظت الطلب" in rr, f"future assignment watch was not registered deterministically: {rr}")
    snapshot = m.get_event_state_snapshot()
    pending = snapshot.get("pending_actions", [])
    check(
        any(
            item.get("trigger_type") == "assignment_added"
            and str((item.get("filters") or {}).get("course_id")) == "1194"
            for item in pending
        ),
        f"future assignment watch was not canonicalized to Cloud course 1194: {pending}",
    )

    # Submission-state requests are a distinct cross-course intent. They must go
    # to pending_work directly instead of running assignments/quizzes separately.
    m.clear_context()
    rr = m.process_user_message("طيب بدي تروح تتاكد ادا في واجب او كويز لم يتم تسليمه")
    check(rr.startswith("لا"), f"pending submission mixed request did not route to pending_work: {rr}")
    check(m._conversation_state.get("last_intent") == "pending_work", "pending submission request did not save pending_work intent")
    rr = m.process_user_message("بدي منك تروح تتاكد من جميع المواد ادا في واجبات لم يتم تسليمها")
    check(rr.startswith("لا"), f"all-course unsubmitted assignment request did not route to pending_work: {rr}")

    # Short factual pending-work follow-ups remain deterministic. Open-ended
    # advice/choice wording is covered by the end-to-end LLM-reasoner scenarios.
    rr = m.process_user_message("شو ضايل علي")
    check(rr.startswith("لا"), f"factual pending-work follow-up escaped state: {rr}")

    # Discourse marker 'خلص' means 'leave that topic' here, not completed/past.
    m.clear_context()
    rr = m.process_user_message("خلص اترك هاض هسا هات كويزات الروبتات")
    check("Quiz 3" in rr, f"topic-switch 'خلص' incorrectly filtered completed quizzes: {rr}")
    rr = m.process_user_message("طيب اخر كويز شو كان؟")
    check("Quiz 3" in rr, f"last quiz selection failed after topic switch: {rr}")
    rr = m.process_user_message("كم كانت مدته؟")
    check("5 mins" in rr, f"selected quiz duration did not stay in state: {rr}")

    # An explicit course mention must outrank a stale resource result set.
    m.clear_context()
    rr = m.process_user_message("هات ملفات مادة التحليل العددي")
    check("Unit 6.pdf" in rr, f"resource setup failed: {rr}")
    rr = m.process_user_message("اول ملف من مادة الحوسبة")
    check("Unit 6.pdf" not in rr, f"stale Numerical resource hijacked explicit Cloud request: {rr}")
    check(str(m._conversation_state["active_course"]["id"]) == "1194", "explicit Cloud resource request did not switch active course")

    # Narrow course-info questions must never dump the whole course payload or
    # fabricate fields the current tool does not extract.
    rr = m.process_user_message("مين الدكتور تبع مادة الحوسبة السحابيه شو اسمه")
    check("مش موجود ضمن البيانات" in rr, f"missing instructor was not reported honestly: {rr}")

    print("PASS: 118 regression assertions")


if __name__ == "__main__":
    run()

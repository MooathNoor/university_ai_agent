import sys
import types

ollama = types.ModuleType('ollama')
ollama.chat = lambda *a, **k: {'message': {'content': '{}'}}
sys.modules['ollama'] = ollama

tools = types.ModuleType('tools')
COURSES = [
    {'id': 1695, 'fullname': '2026/2025-3-30801281-PRINCIPLES OF NUMERICAL ANALYSIS-1'},
    {'id': 1194, 'fullname': '2026/2025-3-30801361-CLOUD COMPUTING-1'},
    {'id': 1499, 'fullname': '2026/2025-3-IOT 456-ROBOTICS AND AUTONOMOUS SYSTEMS .-1'},
]
def cname(c): return c.get('fullname') or c.get('name') or ''
def cid(c): return c.get('id')
tools.get_cached_courses = lambda force=False: COURSES
tools.get_course_name = cname
tools.get_course_id = cid
tools.get_attendance = lambda course_name: {'status':'Success','course':course_name,'activity_state':'Unknown','summary':{},'sessions':[]}
tools.get_course_schedule = lambda course_name: {'status':'Unavailable'}
tools.get_course_info = lambda course_name: {'status':'Success'}
tools.get_course_resources = lambda course_name: []
tools.get_my_courses = lambda: {'status':'Success','courses':COURSES}
tools.get_assignments = lambda course_name=None: []
tools.get_announcements = lambda: {'status':'Empty'}
tools.get_quizzes = lambda course_name=None: []
tools.get_quiz_grades = lambda course_name=None, quizzes=None: []
tools.get_upcoming_deadlines = lambda: []
tools.get_pending_work = lambda: {'status':'Success','has_pending':False,'pending':[]}
tools.get_assignment_submission_status = lambda assignment: {'state':'unknown'}
sys.modules['tools'] = tools

import main

# 1) Explicit multi-domain status must not collapse into pending_work.
msg = 'لا هل يوجد اي جديد من حيث كوزات واجبات ملفات رفعت جديد او حضور ؟'
intents = main._fast_semantic_analysis(msg)['intents']
assert 'quizzes' in intents, intents
assert 'assignments' in intents, intents
assert 'attendance' in intents, intents
assert 'pending_work' not in intents, intents

# 2) General attendance status with no course reference is global, not stale-context scoped.
assert main._is_unscoped_all_courses_status_request('هل يوجد حضور تفعل او تم تسجيلي غياب فيه ؟', 'attendance')
assert not main._is_unscoped_all_courses_status_request('طيب الحضور فيها؟', 'attendance')

# 3) Bare example pointers are not enough source content for a solution.
assert not main._assignment_description_is_sufficient('solve example 2 Jacobi method')
assert not main._assignment_description_is_sufficient('solve example 3 in unit 6')
assert main._assignment_description_is_sufficient('Solve x + y = 4, 2x - y = 1 using Jacobi method')

# 4) Quiz-date future watch compiles locally without planner ambiguity.
watch = main._build_high_confidence_future_watch('وبدي تخبرني في حال تم تحديد موعد لعقد اي كويز')
assert watch is not None, 'quiz watch not compiled'
assert watch.action == 'watch'
assert watch.trigger_type == 'quiz_added', watch.to_dict()
assert watch.requested_action == 'notify'

# 5) Resource-content question fails closed instead of pretending the URL was read.
main._conversation_state['last_result_set'] = {
    'type': 'course_resources',
    'course_id': 1695,
    'course_name': cname(COURSES[0]),
    'items': [{'name':'Part 1','url':'https://example.invalid/file','type':'resource'}],
}
answer = main._course_resource_content_followup('طيب بتقدر تقراهم وتعطيني فيد باك عن الماده')
assert answer is not None
assert 'ما رح أدّعي' in answer or 'ما رح ادعي' in main.normalize_text(answer)

# 6) Natural greeting with a form of address stays on the zero-I/O fast path.
assert main._is_simple_greeting('مساء الخير معلم')
assert main.get_fast_conversation_response('مساء الخير معلم')
assert not main._is_simple_greeting('مساء الخير شو عندي واجبات؟')

# 7) Broad update/file questions are global and never manufacture a course reference.
assert main._is_global_update_question('طيب صار اي حدث جديد بالموقع او تم نشر اي ملف ؟')
assert main._is_global_update_question('سالتك بشكل عام صار اي اشي جديد؟')
assert main._is_global_update_question('في اي ملف جديد تم نشره داخل اي ماده ؟')
assert main._is_all_courses_scope('في اي ملف جديد تم نشره داخل اي ماده ؟')

# The answer must be grounded in monitor state and disclose that file-upload events
# are not tracked yet.
original_snapshot = main._event_state.snapshot
main._event_state.snapshot = lambda *a, **k: {'unacknowledged_events': []}
try:
    update_answer = main._conversation_control('في اي ملف جديد تم نشره داخل اي ماده ؟')
    assert update_answer is not None
    assert 'ما عندي أحداث جديدة' in update_answer
    assert 'ملفات المادة' in update_answer
finally:
    main._event_state.snapshot = original_snapshot

# 8) Pending clarification owns a bare numeric reply before Agent Core.
original_pending_handler = main._handle_pending_course_answer
original_core = main._run_agent_core
main._handle_pending_course_answer = lambda text: 'RESOLVED_PENDING' if text.strip() == '1' else None
main._run_agent_core = lambda text: (_ for _ in ()).throw(AssertionError('Agent Core must not see pending choice'))
try:
    assert main.process_user_message('1') == 'RESOLVED_PENDING'
finally:
    main._handle_pending_course_answer = original_pending_handler
    main._run_agent_core = original_core

print('PASS: Phase 5 hardening assertions')

# 10) Social tone requests stay on the fast path and never wake the planner.
style_reply = main.get_fast_conversation_response('لازم ترد رد يحسسني انك مش بوت رد قريب من الترحيب')
assert style_reply is not None
assert 'طبيعي' in style_reply or 'هلا' in style_reply

# 11) Greeting corrections get a warm greeting instead of a generic canned reply.
correction_reply = main.get_fast_conversation_response('مساء الخير قلت')
assert correction_reply is not None
assert 'مسا النور' in correction_reply

print('PASS: Phase 5 social/order hardening assertions')


# 12) Broad social conversation never wakes Moodle or Agent Core.
for social_msg in [
    'الحمد الله ممتاز اليوم',
    'هيك احسن ردودك',
    'اللووو شو بتخبص',
    'كيفك اليوم يا معلم',
]:
    reply = main.get_fast_conversation_response(social_msg)
    assert reply is not None, social_msg

original_core = main._run_agent_core
main._run_agent_core = lambda text: (_ for _ in ()).throw(AssertionError('social turn reached Agent Core'))
try:
    assert main.process_user_message('الحمد الله ممتاز اليوم')
    assert main.process_user_message('هيك احسن ردودك')
    assert main.process_user_message('اللووو شو بتخبص')
finally:
    main._run_agent_core = original_core

# 13) Complaint/status phrases can never become automatically learned course aliases.
for bad_alias in ['لووو تخبص', 'شو بتخبص', 'الحمد الله ممتاز', 'هيك احسن ردودك']:
    assert not main._safe_auto_course_alias(bad_alias), bad_alias
for good_alias in ['السحابه', 'تحليل عددي', 'روبتات']:
    assert main._safe_auto_course_alias(good_alias), good_alias

# 14) Numeric clarification confirms a course but must not teach a conversational phrase.
original_pending = main._pending_course_resolution
original_learn = main._learn_course_alias
learned = []
main._pending_course_resolution = {
    'reference': 'لووو تخبص',
    'original_message': '',
    'fingerprint': main._course_fingerprint(COURSES),
    'timestamp': __import__('time').time(),
}
main._learn_course_alias = lambda course, alias, courses=None: learned.append(alias)
try:
    resolved = main._handle_pending_course_answer('1')
    assert resolved is not None
    assert learned == [], learned
finally:
    main._pending_course_resolution = original_pending
    main._learn_course_alias = original_learn

# 15) Attendance deictic follow-up resolves the grounded Moodle URL locally.
main._conversation_state['last_intent'] = 'attendance'
main._last_context['raw_result'] = {
    'status': 'Success',
    'attendance_url': 'https://elearning.example/mod/attendance/view.php?id=28016',
}
link_reply = main._state_first_followup('وين ارسلها اشوف')
assert link_reply is not None
assert 'https://elearning.example/mod/attendance/view.php?id=28016' in link_reply

# 16) A university request that merely starts socially must NOT be swallowed.
assert main.get_fast_conversation_response('الحمد الله، هات واجباتي') is None
assert main.get_fast_conversation_response('كيفك؟ في حضور اليوم؟') is None

print('PASS: Phase 5 conversation-control hardening assertions')

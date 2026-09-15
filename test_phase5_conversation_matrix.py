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


# Matrix A: pure social turns must stay local.
social = [
    'مساء الخير يا باشا', 'صباح الخير معلم', 'السلام عليكم يا زلمة',
    'الحمد الله ممتاز اليوم', 'انا منيح الحمد لله', 'كيفك اليوم يا معلم',
    'شو اخبارك', 'هيك احسن ردودك', 'عجبني ردك', 'يسعدك معلم',
    'اللووو شو بتخبص', 'فهمتني غلط', 'مش قصدي هيك',
]
for msg in social:
    assert main.get_fast_conversation_response(msg) is not None, msg

# Matrix B: social wording + a real university request must NOT be swallowed.
university_mixed = [
    'مساء الخير شو عندي واجبات؟',
    'الحمد الله ممتاز، هات واجباتي',
    'كيفك؟ في حضور اليوم؟',
    'شو بتخبص هات الكويزات',
    'مش قصدي الحضور قصدي الكويزات',
    'هيك احسن، طيب ابعث ملفات الحوسبة',
]
for msg in university_mixed:
    assert main.get_fast_conversation_response(msg) is None, msg

# Matrix C: arbitrary conversational text is never a course alias candidate.
unsafe_aliases = [
    'لووو تخبص', 'شو بتخبص', 'فهمتني غلط', 'هيك احسن ردودك',
    'الحمد الله ممتاز', 'مش قصدي', 'ردك غلط',
]
for alias in unsafe_aliases:
    assert not main._safe_auto_course_alias(alias), alias
safe_aliases = ['السحابه', 'تحليل عددي', 'روبتات', 'كلاود']
for alias in safe_aliases:
    assert main._safe_auto_course_alias(alias), alias

# Matrix D: complaint cancels a pending clarification.
main._pending_course_resolution = {
    'reference':'لووو تخبص', 'original_message':'x',
    'fingerprint':main._course_fingerprint(COURSES), 'timestamp':__import__('time').time(),
}
assert main._conversation_control('اللووو شو بتخبص') is not None
assert main._pending_course_resolution is None

# Matrix E: a fresh university request also cancels stale clarification.
main._pending_course_resolution = {
    'reference':'غريب', 'original_message':'هات كويزات غريب',
    'fingerprint':main._course_fingerprint(COURSES), 'timestamp':__import__('time').time(),
}
assert main._handle_pending_course_answer('عندي واجبات لم يتم تسليمها؟') is None
assert main._pending_course_resolution is None

# Matrix F: attendance deictic/link follow-ups reuse grounded context locally.
main._conversation_state['last_intent'] = 'attendance'
main._last_context['raw_result'] = {
    'status':'Success', 'activity_state':'Unknown',
    'attendance_url':'https://elearning.example/mod/attendance/view.php?id=28016',
}
for msg in ['وين ارسلها اشوف', 'ابعث الرابط', 'هات الرابط', 'وينها خليني اشوف']:
    ans = main._state_first_followup(msg)
    assert ans and 'id=28016' in ans, (msg, ans)

# Matrix G: no fabricated link if Moodle did not ground one.
main._last_context['raw_result'] = {'status':'Success', 'activity_state':'Unknown'}
ans = main._state_first_followup('ابعث الرابط')
assert ans is not None
assert 'http' not in ans

# Matrix H: global update/file queries remain global.
for msg in [
    'صار اشي جديد بالموقع اليوم؟',
    'في ملف جديد بأي مادة؟',
    'بشكل عام شو الجديد؟',
    'تم نشر اي ملف داخل اي ماده؟',
]:
    assert main._is_global_update_question(msg) or main._is_whats_new_question(msg), msg

# Matrix I: future watches must not be mistaken for current global updates.
for msg in [
    'خبرني اذا نزل كويز جديد بأي مادة',
    'راقب اذا نزل واجب جديد',
]:
    assert main._message_may_define_future_action(msg), msg
    assert not main._is_global_update_question(msg), msg

# Matrix J: pure social process path must never invoke Agent Core.
original_core = main._run_agent_core
main._run_agent_core = lambda text: (_ for _ in ()).throw(AssertionError('Agent Core called for social turn'))
try:
    for msg in ['الحمد الله ممتاز اليوم', 'هيك احسن ردودك', 'اللووو شو بتخبص']:
        assert main.process_user_message(msg)
finally:
    main._run_agent_core = original_core

print('PASS: 45+ Phase 5 conversation-control matrix checks')

import test_agent_regression as regression


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run():
    m = regression.load_agent()

    # Exact live sequence: first Robotics quiz -> first Cloud quiz -> grades of both.
    r = m.process_user_message('طيب ارسل اول كويز من الروبتات')
    check('Quiz1' in r, f'robot first quiz failed: {r}')
    r = m.process_user_message('ولحوسبه كمان')
    check('Quizz1' in r and 'Quiz2' not in r, f'cloud inherited first selection failed: {r}')
    r = m.process_user_message('طيب هات علامات كل منهم')
    check('Quizz1' in r and 'Quiz1' in r, f'plural cross-course reference failed: {r}')
    check('10 / 10' in r, f'cloud grade missing: {r}')

    # Return to Robotics quizzes, then singular pronoun must bind to the previously
    # grounded Robotics first quiz instead of waking Agent Core/course_info.
    r = m.process_user_message('وكويز الروبتات ؟')
    check('Quiz1' in r, f'robotics quiz turn failed: {r}')
    original_core = m._run_agent_core
    m._run_agent_core = lambda text: (_ for _ in ()).throw(AssertionError('Agent Core called for grounded grade pronoun'))
    try:
        r = m.process_user_message('هات علامته')
    finally:
        m._run_agent_core = original_core
    check('Quiz1' in r, f'singular quiz reference failed: {r}')
    check('العلامة غير ظاهرة' in r or 'علامتك' in r, f'grade answer not grounded: {r}')

    # Existing same-course plural behavior must remain: visible Cloud list owns "فيهم".
    m.clear_context()
    r = m.process_user_message('مادة الحوسبة السحابيه كم كويز يوجد؟')
    check(r == 'عدد الكويزات: 2', r)
    r = m.process_user_message('كم علاماتي فيهم')
    check('Quizz1' in r and 'Quiz2' in r and 'Quiz 3' not in r, r)

    # Complaint about speed is local and must not wake Agent Core.
    for msg in ['بطيئئئئئئئئئئئئ', 'ليش بتطول هيك', 'تأخرت كثير']:
        check(m.get_fast_conversation_response(msg) is not None, f'slow complaint escaped fast path: {msg}')

    # History is grounded-only and bounded.
    history = m._conversation_state.get('recent_entities') or []
    check(len(history) <= 10, f'history unbounded: {len(history)}')
    check(all(isinstance(x.get('item'), dict) for x in history), f'ungrounded history: {history}')

    print('PASS: Phase 5 context-reference resolution scenarios')


if __name__ == '__main__':
    run()

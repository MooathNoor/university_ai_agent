import test_agent_regression as regression


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run():
    m = regression.load_agent()

    # The initial multi-intent answer must contain both grounded domains
    # and preserve both result sets for the next contextual turn.
    r = m.process_user_message('شو عندي كويزات وواجبات بالحوسبة؟')
    check('Quizz1' in r and 'Cloud Security Assignment' in r, r)
    sets = m._conversation_state.get('last_multi_result_sets') or {}
    check('quizzes' in sets and 'assignments' in sets, f'multi sets lost: {sets}')

    original_core = m._run_agent_core
    m._run_agent_core = lambda text: (_ for _ in ()).throw(
        AssertionError(f'Agent Core should not run: {text}')
    )
    try:
        # Follow-up must select the FIRST grounded item from EACH previous domain.
        r = m.process_user_message('هات أول واحد من كل نوع')
        check('Quizz1' in r and 'Public vs Private Assignment' in r, r)

        # Language/style feedback is conversation control, never Moodle/LLM.
        r = m.process_user_message('يخي ليش ما بتحكي بالعربي')
        check('بالعربي' in r, r)

        # Ultra-short ambiguous input must fail closed rather than fuzzy-match attendance.
        r = m.process_user_message('ر')
        check('مش واضح' in r, r)

        # Submission-status refinement must stay on the grounded deterministic path.
        r = m.process_user_message('بدي بس الي ماتم تسليمهم')
        check('ما عندك' in r or 'غير مكتمل' in r or 'تأكيد' in r, r)
    finally:
        m._run_agent_core = original_core

    print('PASS: Phase 5 request-frame/conversation-control scenarios')


if __name__ == '__main__':
    run()

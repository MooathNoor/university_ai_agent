"""Focused offline tests for V5 Agent Core planning."""
from agent_core import AgentCore


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    replies = iter([
        # Natural advice from grounded state.
        '{"action":"respond","tool":null,"course_ref":null,"refresh":false,'
        '"response_goal":"advise from grounded pending state","clarification":"",'
        '"confidence":0.96,"reason":"state is sufficient",'
        '"answer":"حسب آخر فحص ما عندك شيء عاجل، بتقدر تطلع."}',
        # Freshness-sensitive check.
        '{"action":"tool","tool":"pending_work","course_ref":null,"refresh":true,'
        '"response_goal":"verify current pending work","clarification":"",'
        '"confidence":0.98,"reason":"student asks for current status","answer":""}',
        # Unknown reference.
        '{"action":"clarify","tool":null,"course_ref":null,"refresh":false,'
        '"response_goal":"","clarification":"أي واجب تقصد؟","confidence":0.91,'
        '"reason":"no grounded assignment","answer":""}',
        # Invalid tool must fail closed.
        '{"action":"tool","tool":"delete_course","refresh":true,"confidence":0.99}',
        # Future condition becomes a structural watch request.
        '{"action":"watch","tool":null,"course_ref":"الحوسبة السحابية",'
        '"refresh":false,"confidence":0.97,"reason":"future trigger",'
        '"trigger_type":"assignment_added",'
        '"event_filters":{"course_ref":"الحوسبة السحابية"},'
        '"requested_action":"notify","notify":true}',
    ])

    def fake_chat(*args, **kwargs):
        return {"message": {"content": next(replies)}}

    core = AgentCore(fake_chat, "fake-model")
    state = {
        "last_intent": "pending_work",
        "pending_work": {"status": "Success", "has_pending": False},
    }

    d = core.plan("الوضع بسمح اروح عند صاحبي؟", state)
    check(d.action == "respond", f"expected respond, got {d}")
    check("بتقدر تطلع" in d.answer, f"missing grounded advice: {d.answer}")

    d = core.plan("تأكدلي هسا إذا في اشي علي", state)
    check(d.action == "tool" and d.tool == "pending_work", f"fresh check plan failed: {d}")
    check(d.refresh is True, "fresh check did not request refresh")

    d = core.plan("اشرحلي الواجب", {})
    check(d.action == "clarify", f"missing-reference clarification failed: {d}")

    d = core.plan("اعمل اشي", {})
    check(d.action != "tool", f"invalid tool escaped validation: {d}")
    check(d.tool is None, f"invalid tool was retained: {d}")

    d = core.plan("اذا نزل واجب جديد بالحوسبة خبرني", {}, future_condition_hint=True)
    check(d.action == "watch", f"future watch plan failed: {d}")
    check(d.trigger_type == "assignment_added", f"wrong trigger type: {d}")
    check(d.requested_action == "notify" and d.notify is True, f"watch action metadata failed: {d}")

    print("PASS: 5 Agent Core planner assertions")


if __name__ == "__main__":
    run()

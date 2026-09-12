"""End-to-end offline conversation scenarios for the University AI Agent.

These tests exercise multi-turn user journeys rather than isolated functions.
Moodle is faked by test_agent_regression.load_agent(); course-scoring LLM calls
remain forbidden. Assignment-solving is allowed through a tiny deterministic
stub so we can prove the selected assignment survives into the solve turn.
"""
from __future__ import annotations

import test_agent_regression as regression
from types import SimpleNamespace


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def install_solution_only_llm(agent):
    calls = []

    def chat(*args, **kwargs):
        messages = kwargs.get("messages") or []
        prompt = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
        if "Score how strongly the STUDENT COURSE REFERENCE" in prompt:
            raise AssertionError("Course scorer was called during a grounded conversation scenario")
        if "AGENT CORE PLANNER" in prompt:
            return {"message": {"content": '{"action":"legacy","confidence":0.99,"reason":"scenario keeps legacy path"}'}}
        calls.append(prompt)
        if "conversational reasoning layer" in prompt:
            if "شو بحكي" in prompt:
                return {"message": {"content": "عندي اسم الملف ورابطه فقط، ولسا ما قرأت محتواه حتى أحكيلك شو بحكي."}}
            return {"message": {"content": "حسب آخر فحص ما عندك شيء جامعي غير مكتمل ظاهر؛ إذا بدك اطلع مشوار 😄"}}
        return {"message": {"content": "حل تجريبي مبني على الواجب المحدد."}}

    agent.ollama.chat = chat
    return calls


def run():
    agent = regression.load_agent()
    solution_calls = install_solution_only_llm(agent)

    # Scenario 1: resource list -> local first-item selection.
    response = agent.process_user_message("هات ملفات مادة التحليل العددي")
    check("Unit 6.pdf" in response, f"resource list failed: {response}")
    response = agent.process_user_message("هات اول ملف فقط")
    check("Unit 6.pdf" in response, f"resource first-item follow-up failed: {response}")
    check(agent._pending_course_resolution is None, "resource follow-up opened course clarification")

    # Scenario 2: assignment list -> third item -> colloquial details -> solution.
    response = agent.process_user_message("هات قائمة الواجبات لمادة التحليل العددي")
    check("26-7-2026 Assignment" in response, f"assignment list failed: {response}")

    response = agent.process_user_message("بدي ترسل ثالث واجب")
    check("26-7-2026 Assignment" in response, f"third assignment selection failed: {response}")
    active = agent._active_entity_item("assignment")
    check(active and active.get("name") == "26-7-2026 Assignment", "third assignment not grounded")

    response = agent.process_user_message("شو بده ؟")
    check("solve example 3" in response, f"short detail follow-up failed: {response}")

    response = agent.process_user_message("اشرحلي الواجب شو بده ؟")
    check("solve example 3" in response, f"natural detail follow-up failed: {response}")

    response = agent.process_user_message("هات حله")
    check("حل تجريبي" in response, f"solve turn did not stay on selected assignment: {response}")
    check(len(solution_calls) == 1, f"solve flow used LLM unexpected number of times: {len(solution_calls)}")

    # Scenario 3: no conversational fragment may be auto-learned as a course alias.
    learned = {
        agent.normalize_text(rule.get("phrase"))
        for rule in agent._load_learned_rules().get("rules", [])
        if rule.get("type") == "course_alias"
    }
    check("ترسل ثالث" not in learned, f"ordinal action polluted aliases: {learned}")
    check("بده" not in learned, f"predicate polluted aliases: {learned}")

    # Scenario 4: submission-state wording is one cross-course pending_work task.
    agent.clear_context()
    response = agent.process_user_message("طيب بدي تروح تتاكد ادا في واجب او كويز لم يتم تسليمه")
    check(response.startswith("لا"), f"mixed pending-work route failed: {response}")
    check(agent._conversation_state.get("last_intent") == "pending_work", "mixed pending request lost pending_work intent")

    response = agent.process_user_message("بدي منك تروح تتاكد من جميع المواد ادا في واجبات لم يتم تسليمها")
    check(response.startswith("لا"), f"all-course pending-work route failed: {response}")
    check(agent._conversation_state.get("last_intent") == "pending_work", "all-course pending request lost pending_work intent")

    # Scenario 5: explicit course switch must beat stale state; discourse marker
    # 'خلص' must not be misread as a completed/past filter.
    response = agent.process_user_message("خلص اترك هاض هسا هات كويزات الروبتات")
    check("Quiz 3" in response, f"explicit switch to Robotics failed: {response}")
    check(str(agent._conversation_state["active_course"]["id"]) == "1499", "active course did not switch to Robotics")
    response = agent.process_user_message("طيب اخر كويز شو كان؟")
    check("Quiz 3" in response, f"last quiz state selection failed: {response}")
    response = agent.process_user_message("كم كانت مدته؟")
    check("5 mins" in response, f"quiz duration follow-up escaped selected quiz: {response}")

    # Scenario 6: open-ended advice around grounded pending state is interpreted
    # by the LLM reasoner WITH state, not by phrase-specific if/else rules.
    agent.clear_context()
    response = agent.process_user_message("بدي منك تروح تتاكد من جميع المواد ادا في واجبات لم يتم تسليمها")
    check(response.startswith("لا"), f"pending setup failed: {response}")
    before = len(solution_calls)
    response = agent.process_user_message("في اشي لازم اعمله حاليا ولا اروح احضر مسلسل ؟")
    check("حسب آخر فحص" in response, f"state-aware advice failed: {response}")
    check(len(solution_calls) == before + 1, "open-ended advice did not use the state-aware LLM exactly once")
    check('"pending_work"' in solution_calls[-1], "state-aware LLM prompt did not receive pending-work grounding")

    # Scenario 7: an explicit new course beats stale file state, then an unknown
    # natural follow-up is reasoned over the newly selected resource.
    agent.clear_context()
    response = agent.process_user_message("هات ملفات مادة التحليل العددي")
    check("Unit 6.pdf" in response, f"Numerical resource setup failed: {response}")
    response = agent.process_user_message("اول ملف من مادة الحوسبة")
    check("Unit 6.pdf" not in response, f"stale result hijacked explicit Cloud selection: {response}")
    check(str(agent._conversation_state["active_course"]["id"]) == "1194", "explicit Cloud request did not replace old course state")

    # Return to Numerical where the fake has a real resource, select it, then ask
    # an unseen conversational question. The reasoner must receive that resource
    # as active grounded state rather than inventing its contents.
    response = agent.process_user_message("هات ملفات مادة التحليل العددي")
    response = agent.process_user_message("هات اول ملف فقط")
    check(agent._active_entity_item("course_resource") is not None, "selected resource was not stored as an active entity")
    before = len(solution_calls)
    response = agent.process_user_message("شو بحكي ؟")
    check("لسا ما قرأت محتواه" in response, f"resource conversational reasoning was not grounded: {response}")
    check(len(solution_calls) == before + 1, "resource question did not use one state-aware LLM call")
    check('"type": "course_resource"' in solution_calls[-1], "resource state was not supplied to the LLM")

    # Scenario 8: V5 Agent Core is actually integrated into process_user_message.
    # Use an unseen everyday phrase; no phrase-specific rule is allowed to answer it.
    agent.clear_context()
    response = agent.process_user_message("بدي منك تروح تتاكد من جميع المواد ادا في واجبات لم يتم تسليمها")
    check(response.startswith("لا"), f"Agent Core setup failed: {response}")

    planner_calls = []
    original_plan = agent._agent_core.plan

    def fake_plan(message, state, **kwargs):
        planner_calls.append((message, state))
        return SimpleNamespace(
            action="respond", tool=None, course_ref=None, refresh=False,
            response_goal="give grounded advice", clarification="", confidence=0.97,
            reason="grounded pending-work state is enough",
            answer="حسب آخر فحص وضعك الجامعي هادي، بتقدر تروح عند صاحبك.",
            to_dict=lambda: {"action": "respond", "confidence": 0.97},
        )

    agent._agent_core.plan = fake_plan
    response = agent.process_user_message("الوضع بسمح اروح عند صاحبي شوي؟")
    check("بتقدر تروح" in response, f"Agent Core integration did not answer unseen advice: {response}")
    check(len(planner_calls) == 1, "Agent Core planner was not called exactly once")
    check(planner_calls[0][1].get("pending_work") is not None, "planner did not receive grounded pending-work state")
    agent._agent_core.plan = original_plan

    # Scenario 9: a future-condition request is stored structurally, then a real
    # external event matches it by canonical Moodle course_id.
    agent.clear_context()
    agent._event_state.reset()
    original_plan = agent._agent_core.plan

    def watch_plan(message, state, **kwargs):
        return SimpleNamespace(
            action="watch", tool=None, course_ref="الحوسبة السحابية", refresh=False,
            response_goal="notify on a future assignment", clarification="", confidence=0.98,
            reason="future condition", answer="", trigger_type="assignment_added",
            event_filters={"course_ref": "الحوسبة السحابية"}, requested_action="notify", notify=True,
            to_dict=lambda: {"action": "watch", "trigger_type": "assignment_added", "confidence": 0.98},
        )

    agent._agent_core.plan = watch_plan
    response = agent.process_user_message("لو الدكتور نزل واجب جديد بالحوسبة بلغني مباشرة")
    check("حفظت الطلب" in response, f"future action was not registered: {response}")
    pending = agent.get_event_state_snapshot()["pending_actions"]
    check(len(pending) == 1, f"pending action missing: {pending}")
    check(str(pending[0]["filters"].get("course_id")) == "1194", f"course was not canonicalized: {pending[0]}")

    event_result = agent.register_external_event(
        "assignment_added",
        {"course_id": 1194, "course_name": regression.CLOUD, "name": "New Cloud Assignment"},
    )
    check(len(event_result["matching_actions"]) == 1, f"real event did not match pending action: {event_result}")

    # Scenario 10: event history is part of Agent Core state, so an unseen
    # natural question about what happened while away can be answered from state.
    history_calls = []

    def history_plan(message, state, **kwargs):
        history_calls.append((message, state))
        events = (state.get("event_state") or {}).get("recent_events") or []
        check(any(e.get("type") == "assignment_added" for e in events), "planner did not receive event history")
        return SimpleNamespace(
            action="respond", tool=None, course_ref=None, refresh=False,
            response_goal="summarize missed events", clarification="", confidence=0.97,
            reason="event history is grounded", answer="صار حدث جديد: نزل واجب بالحوسبة السحابية.",
            trigger_type=None, event_filters={}, requested_action="notify", notify=True,
            to_dict=lambda: {"action": "respond", "confidence": 0.97},
        )

    agent._agent_core.plan = history_plan
    response = agent.process_user_message("شو صار وأنا غايب عن التلفون؟")
    check("نزل واجب" in response, f"event-history follow-up failed: {response}")
    check(len(history_calls) == 1, "event-history question did not use Agent Core exactly once")
    agent._agent_core.plan = original_plan

    print("PASS: 10 end-to-end conversation scenarios")


if __name__ == "__main__":
    run()

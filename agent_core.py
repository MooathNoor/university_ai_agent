"""Core reasoning layer for the University AI Agent.

This module intentionally does not know how Moodle is implemented.  Its job is
only to decide *what kind of action is needed* from a user message plus grounded
conversation state.  Execution remains in main.py/tools.py.

The separation is deliberate:
- LLM: understands natural language, context, advice, freshness and references.
- Python: validates the plan, executes real tools, enforces permissions, and
  never lets the model invent university facts.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Any, Callable, Dict, Optional


ALLOWED_ACTIONS = {
    "respond",        # answer naturally using grounded state/general reasoning
    "tool",           # execute a university tool/intent
    "clarify",        # ask one focused clarification
    "watch",          # register a future trigger/action request
    "legacy",         # let the proven deterministic executor handle the turn
}

ALLOWED_TOOLS = {
    "pending_work",
    "assignments",
    "quizzes",
    "course_files",
    "attendance",
    "schedule",
    "course_info",
    "quiz_grades",
    "announcements",
}


@dataclass
class AgentDecision:
    action: str = "legacy"
    tool: Optional[str] = None
    course_ref: Optional[str] = None
    refresh: bool = False
    response_goal: str = ""
    clarification: str = ""
    confidence: float = 0.0
    reason: str = ""
    answer: str = ""
    trigger_type: Optional[str] = None
    event_filters: Optional[Dict[str, Any]] = None
    requested_action: str = "notify"
    notify: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentCore:
    """LLM planner with strict output validation and safe fallback."""

    def __init__(self, chat_fn: Callable[..., Any], model_name: str):
        self.chat_fn = chat_fn
        self.model_name = model_name

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {}
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _validate(raw: Dict[str, Any]) -> AgentDecision:
        action = str(raw.get("action") or "legacy").strip().lower()
        if action not in ALLOWED_ACTIONS:
            action = "legacy"

        tool = raw.get("tool")
        if tool is not None:
            tool = str(tool).strip().lower()
            if tool not in ALLOWED_TOOLS:
                tool = None

        # A tool action without a valid tool is not executable.
        if action == "tool" and not tool:
            action = "clarify" if raw.get("clarification") else "legacy"

        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        course_ref = raw.get("course_ref")
        if course_ref is not None:
            course_ref = str(course_ref).strip() or None

        trigger_type = raw.get("trigger_type")
        if trigger_type is not None:
            trigger_type = str(trigger_type).strip().lower().replace(" ", "_") or None

        filters = raw.get("event_filters")
        if not isinstance(filters, dict):
            filters = {}
        filters = {str(k): v for k, v in filters.items() if v not in (None, "", [], {})}

        requested_action = str(raw.get("requested_action") or "notify").strip().lower().replace(" ", "_")
        if action == "watch" and not trigger_type:
            action = "clarify" if raw.get("clarification") else "legacy"

        clarification = str(raw.get("clarification") or "").strip()
        if clarification.lower() in {"none", "null", "n/a", "na", "no clarification"}:
            clarification = ""

        return AgentDecision(
            action=action,
            tool=tool,
            course_ref=course_ref,
            refresh=bool(raw.get("refresh", False)),
            response_goal=str(raw.get("response_goal") or "").strip(),
            clarification=clarification,
            confidence=confidence,
            reason=str(raw.get("reason") or "").strip(),
            answer=str(raw.get("answer") or "").strip(),
            trigger_type=trigger_type,
            event_filters=filters,
            requested_action=requested_action or "notify",
            notify=bool(raw.get("notify", True)),
        )

    def plan(
        self,
        user_message: str,
        state: Dict[str, Any],
        future_condition_hint: bool = False,
    ) -> AgentDecision:
        """Return a validated plan.  On any model/parsing failure, use legacy.

        ``future_condition_hint`` is supplied by the deterministic pre-router when
        the wording contains both a future condition and a requested reaction.
        It does not decide the university intent; it only prevents the planner
        from mistaking a future watch request for an immediate Moodle lookup.
        """
        # Future-condition requests use a compact, constrained planner prompt.
        # This improves both reliability and latency on local models: the planner
        # cannot confuse "when X happens, tell me" with an immediate Moodle lookup,
        # and it does not need the entire conversation payload to register a watch.
        if future_condition_hint:
            compact_state = {
                "active_course": state.get("active_course"),
                "active_entity": state.get("active_entity"),
                "last_intent": state.get("last_intent"),
            }
            prompt = f"""
FUTURE WATCH PLANNER

The student is asking the university agent to react LATER when a future condition happens.
Return ONLY JSON. You may choose only action=watch or action=clarify.
Never choose an immediate Moodle tool for this turn.

Rules:
- Use watch when the future trigger and requested reaction are understandable.
- Use clarify only if a necessary trigger/reference cannot be resolved safely.
- Never invent an event that already happened.
- course_ref should be the course phrase explicitly/reliably referenced, or null.
- requested_action should usually be notify when the student only wants to be told.
- Good structural triggers include assignment_added, quiz_added, attendance_opened, deadline_near.

Return this schema:
{{
  "action": "watch|clarify",
  "tool": null,
  "course_ref": null or "course reference",
  "refresh": false,
  "response_goal": "short goal",
  "clarification": "question only if action=clarify",
  "confidence": 0.0,
  "reason": "short rationale",
  "answer": "",
  "trigger_type": null or "structural_event_name",
  "event_filters": {{"course_ref": "optional course reference"}},
  "requested_action": "notify",
  "notify": true
}}

COMPACT STATE:
{json.dumps(compact_state, ensure_ascii=False, default=str)}

STUDENT MESSAGE:
{user_message}
"""
        else:
            prompt = f"""
AGENT CORE PLANNER

You are the planning brain of a university AI agent. Decide the next action.
If action=respond, also provide the final grounded reply in answer.

GROUNDING AND PLANNING RULES:
1. Moodle/tool data is the source of truth for university facts.
2. Never invent a course fact, deadline, submission state, grade, teacher name,
   file content, attendance state, assignment requirement, or quiz detail.
3. Use conversation STATE to resolve references and follow-ups.
4. If the student asks for advice/opinion and the needed facts are already fresh
   enough in STATE, choose action=respond.
5. If the student explicitly asks for the situation "now/currently", asks you to
   check/confirm again, or a decision materially depends on possibly changed
   Moodle data, choose action=tool and refresh=true for the appropriate tool.
6. If the request is a clear university data action, choose action=tool.
7. If a proven deterministic executor is better for an already-clear structured
   command, action=legacy is acceptable.
8. Ask for clarification only when a necessary reference truly cannot be resolved.
9. Everyday wording is not an intent.  Understand meaning, not keywords.
10. A response action may give normal advice, but factual claims must be limited
    to grounded STATE.
11. If the student asks you to remember/monitor a FUTURE condition and react when
    it happens (for example notify when a new item appears), choose action=watch.
    Express the condition structurally with trigger_type and event_filters. Do not
    invent an event that has not happened.
12. For watch requests, requested_action describes what should happen when the
    trigger occurs. Use notify when the user only wants to be told.

ALLOWED ACTIONS: respond, tool, clarify, watch, legacy
ALLOWED TOOLS: pending_work, assignments, quizzes, course_files, attendance,
schedule, course_info, quiz_grades, announcements

Return ONLY JSON with this schema:
{{
  "action": "respond|tool|clarify|watch|legacy",
  "tool": null or one allowed tool,
  "course_ref": null or the course phrase explicitly/reliably referenced,
  "refresh": true or false,
  "response_goal": "short description of what the final answer should achieve",
  "clarification": "question only if action=clarify",
  "confidence": 0.0,
  "reason": "short internal rationale",
  "answer": "ONLY when action=respond: concise natural reply grounded in STATE",
  "trigger_type": null or a structural future event name such as assignment_added, quiz_added, attendance_opened, deadline_near,
  "event_filters": {{"course_ref": "optional course reference or other structural filters"}},
  "requested_action": "notify or another concise requested action",
  "notify": true or false
}}

STATE:
{json.dumps(state, ensure_ascii=False, default=str)}

STUDENT MESSAGE:
{user_message}
"""
        try:
            response = self.chat_fn(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.get("message", {}).get("content", "")
            return self._validate(self._extract_json(content))
        except Exception:
            return AgentDecision(action="legacy", reason="planner_error")

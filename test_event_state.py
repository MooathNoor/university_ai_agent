"""Focused tests for V5 Phase 2 event/pending-action state."""
from __future__ import annotations

import os
import tempfile
from event_state import EventState


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "event_state.json")
        state = EventState(path)

        action = state.add_pending_action(
            trigger_type="assignment_added",
            filters={"course_id": 1194},
            requested_action="notify",
            original_request="اذا نزل واجب جديد بالحوسبة خبرني",
        )
        check(action["status"] == "active", f"pending action not active: {action}")

        wrong = state.record_event("assignment_added", {"course_id": 1695, "name": "A1"})
        check(not wrong["matching_actions"], f"wrong course matched action: {wrong}")

        right = state.record_event("assignment_added", {"course_id": 1194, "name": "Cloud A1"})
        check(len(right["matching_actions"]) == 1, f"matching event missed action: {right}")
        event_id = right["event"]["id"]

        snapshot = state.snapshot()
        check(len(snapshot["recent_events"]) == 2, f"events not retained: {snapshot}")
        check(len(snapshot["pending_actions"]) == 1, f"pending action disappeared: {snapshot}")
        check(any(x["id"] == event_id for x in snapshot["unacknowledged_events"]), "new event not unacknowledged")

        check(state.acknowledge_event(event_id), "event acknowledgement failed")
        check(not any(x["id"] == event_id for x in state.snapshot()["unacknowledged_events"]), "acknowledged event stayed unread")

        # Persistence across a process-like reload.
        reloaded = EventState(path)
        check(len(reloaded.snapshot()["recent_events"]) == 2, "event state did not persist")
        check(len(reloaded.snapshot()["pending_actions"]) == 1, "pending action did not persist")

    print("PASS: 8 Event State assertions")


if __name__ == "__main__":
    run()

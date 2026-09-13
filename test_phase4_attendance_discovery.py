"""Offline Phase 4 attendance discovery/state tests."""
from __future__ import annotations

import sys
import types

from bs4 import BeautifulSoup

# tools.py imports moodle_tools, which is optional in this deterministic unit test.
if "moodle_tools" not in sys.modules:
    fake = types.ModuleType("moodle_tools")
    fake.get_all_assignments = lambda: []
    fake.get_all_quizzes = lambda: []
    sys.modules["moodle_tools"] = fake

import tools
import monitor

count = 0

def ok(condition, message):
    global count
    if not condition:
        raise AssertionError(message)
    count += 1
    print(f"PASS: {message}")

base = "https://elearning3.bau.edu.jo/huson/mod/attendance/view.php?id=555"

open_html = """
<html><body>
<form method="post" action="/huson/mod/attendance/attendance.php?sessid=123&sesskey=SUPER_SECRET">
  <input type="hidden" name="sessid" value="123">
  <input type="hidden" name="sesskey" value="SUPER_SECRET">
  <input type="radio" name="status" value="1">
  <button type="submit">Submit attendance</button>
</form>
</body></html>
"""
open_result = tools._parse_attendance_discovery(BeautifulSoup(open_html, "html.parser"), base)
ok(open_result["activity_state"] == "Open", "actionable self-attendance control is classified Open")
ok(open_result["read_only"] is True, "attendance discovery is explicitly read-only")
ok(len(open_result["controls"]) == 1, "attendance form is discovered structurally")
control = open_result["controls"][0]
ok(control["method"] == "POST", "discovery records form method without submitting it")
ok(set(control["field_names"]) == {"sessid", "sesskey", "status"}, "discovery records field names")
ok("SUPER_SECRET" not in str(open_result), "discovery never exposes token values")
ok("fields=sessid,sesskey" in control["action"], "diagnostic endpoint keeps query names only")

link_html = """
<html><body>
<a href="/huson/mod/attendance/attendance.php?sessid=987&sesskey=HIDDEN">Submit attendance</a>
</body></html>
"""
link_result = tools._parse_attendance_discovery(BeautifulSoup(link_html, "html.parser"), base)
ok(link_result["activity_state"] == "Open", "actionable attendance link is classified Open")
ok("HIDDEN" not in str(link_result), "link discovery also strips secret values")

closed_html = "<html><body><div class='alert'>Attendance is Closed</div></body></html>"
closed_result = tools._parse_attendance_discovery(BeautifulSoup(closed_html, "html.parser"), base)
ok(closed_result["activity_state"] == "Closed", "explicit closed evidence is classified Closed")
ok(closed_result["controls"] == [], "closed page has no invented action control")

unknown_html = "<html><body><h2>Attendance</h2><p>Sessions</p></body></html>"
unknown_result = tools._parse_attendance_discovery(BeautifulSoup(unknown_html, "html.parser"), base)
ok(unknown_result["activity_state"] == "Unknown", "absence of evidence stays Unknown instead of guessing")

# Monitor must consume the real activity state rather than request-status Success.
old_get_attendance = monitor.get_attendance
try:
    monitor.get_attendance = lambda course_name: {
        "status": "Success",
        "activity_state": "Open",
        "attendance_url": base,
        "discovery": open_result,
        "sessions": [],
    }
    state = monitor.collect_attendance([{"id": 1695, "name": "Numerical Analysis"}])
    row = state["Numerical Analysis"]
    ok(row["status"] == "Open", "monitor tracks activity_state rather than HTTP/parser success")
    ok(row["request_status"] == "Success", "monitor preserves request status separately")
finally:
    monitor.get_attendance = old_get_attendance

changes = monitor.find_attendance_changes(
    {"Numerical Analysis": {"course_id": 1695, "status": "Closed", "sessions": []}},
    {"Numerical Analysis": {"course_id": 1695, "status": "Open", "sessions": []}},
)
ok(any(x.get("type") == "status_changed" and x.get("new") == "Open" for x in changes), "Closed to Open becomes a monitor status change")

print(f"\nPASS: {count} Phase 4 attendance-discovery assertions")

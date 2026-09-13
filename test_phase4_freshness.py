"""Offline Phase 4 freshness semantics tests."""
from __future__ import annotations
import sys
import types

if "ollama" not in sys.modules:
    fake_ollama = types.ModuleType("ollama")
    fake_ollama.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
    sys.modules["ollama"] = fake_ollama
if "moodle_tools" not in sys.modules:
    fake_mt = types.ModuleType("moodle_tools")
    fake_mt.get_all_assignments = lambda: []
    fake_mt.get_all_quizzes = lambda: []
    sys.modules["moodle_tools"] = fake_mt

import main

count = 0

def ok(condition, message):
    global count
    if not condition:
        raise AssertionError(message)
    count += 1
    print(f"PASS: {message}")

fresh_phrases = [
    "الحضور فتح هسا؟",
    "شو وضعي حاليا",
    "هل في واجب الآن؟",
    "check right now",
    "currently open?",
    "تأكد مرة ثانية",
]
for phrase in fresh_phrases:
    ok(main._force_refresh_requested(phrase), f"freshness phrase forces refresh: {phrase}")

stale_safe = [
    "هات واجبات الحوسبة",
    "اعطيني كويزات الروبوتكس",
    "معلومات مادة التحليل العددي",
]
for phrase in stale_safe:
    ok(not main._force_refresh_requested(phrase), f"ordinary lookup may use TTL cache: {phrase}")

# Prove execute_for_courses forwards force_refresh=True when freshness is requested.
old_execute = main.execute_course_tool
calls = []
try:
    def fake_execute(intent, course, force_refresh=False):
        calls.append(force_refresh)
        return {"status": "Success", "course": course.get("fullname")}
    main.execute_course_tool = fake_execute
    main.execute_for_courses(
        "attendance",
        [{"id": 1695, "fullname": "NUMERICAL ANALYSIS"}],
        "الحضور مفتوح هسا؟",
    )
    ok(calls == [True], "fresh mutable-status question reaches course tool with force_refresh=True")
finally:
    main.execute_course_tool = old_execute

print(f"\nPASS: {count} Phase 4 freshness assertions")

"""Real Moodle read-only attendance discovery.

This script performs authenticated GET requests only. It does not submit forms,
mark attendance, or print token values.
"""
from __future__ import annotations

import json

from tools import get_cached_courses, get_attendance, get_course_name


def main():
    courses = get_cached_courses(force=True)
    if not courses:
        raise SystemExit("Could not load Moodle courses.")

    print(f"Courses: {len(courses)}")
    for index, course in enumerate(courses, start=1):
        name = get_course_name(course)
        print("\n" + "=" * 70)
        print(f"{index}. {name}")
        print("=" * 70)
        result = get_attendance(name)
        safe = {
            "status": result.get("status"),
            "course": result.get("course"),
            "course_id": result.get("course_id"),
            "activity_state": result.get("activity_state"),
            "attendance_url": result.get("attendance_url"),
            "summary": result.get("summary", {}),
            "sessions": result.get("sessions", []),
            "discovery": result.get("discovery", {}),
            "message": result.get("message"),
        }
        print(json.dumps(safe, ensure_ascii=False, indent=2))

    print("\nREAD-ONLY discovery finished. No attendance submission was attempted.")


if __name__ == "__main__":
    main()

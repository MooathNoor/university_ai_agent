from __future__ import annotations

import time
from copy import deepcopy


class CourseRegistry:
    """Dynamic per-course workspace over the existing Moodle tool layer.

    The registry mirrors the current Moodle course list and lazily caches volatile
    sections (assignments, quizzes, resources, attendance). Moodle remains the
    source of truth: callers can force-refresh any section, while ordinary
    follow-ups reuse fresh grounded data instead of rescanning every course.
    """

    DEFAULT_TTLS = {
        "assignments": 60,
        "quizzes": 60,
        "resources": 120,
        "attendance": 30,
    }

    def __init__(
        self,
        load_courses,
        get_course_name,
        get_course_id,
        loaders,
        ttls=None,
    ):
        self._load_courses = load_courses
        self._get_course_name = get_course_name
        self._get_course_id = get_course_id
        self._loaders = dict(loaders or {})
        self._ttls = dict(self.DEFAULT_TTLS)
        if isinstance(ttls, dict):
            self._ttls.update(ttls)
        self._fingerprint = None
        self._courses = {}

    def _course_signature(self, courses):
        return tuple(
            (str(self._get_course_id(course)), self._get_course_name(course))
            for course in courses
        )

    def sync(self, force=False):
        try:
            courses = self._load_courses(force=force)
        except TypeError:
            courses = self._load_courses()
        courses = list(courses or [])
        signature = self._course_signature(courses)
        if signature == self._fingerprint:
            return courses

        old = self._courses
        rebuilt = {}
        for course in courses:
            course_id = str(self._get_course_id(course))
            name = self._get_course_name(course)
            previous = old.get(course_id, {})
            keep_cache = previous.get("name") == name
            rebuilt[course_id] = {
                "id": self._get_course_id(course),
                "name": name,
                "course": dict(course) if isinstance(course, dict) else course,
                "sections": deepcopy(previous.get("sections", {})) if keep_cache else {},
                "updated_at": dict(previous.get("updated_at", {})) if keep_cache else {},
            }

        self._courses = rebuilt
        self._fingerprint = signature
        return courses

    def _record(self, course):
        self.sync()
        course_id = str(self._get_course_id(course))
        return self._courses.get(course_id)

    def _is_fresh(self, record, section):
        stamp = record.get("updated_at", {}).get(section)
        if stamp is None:
            return False
        ttl = float(self._ttls.get(section, 0) or 0)
        return ttl > 0 and (time.time() - stamp) < ttl

    def _normalize_items(self, value, record):
        if not isinstance(value, list):
            return value
        normalized = []
        for item in value:
            if not isinstance(item, dict):
                normalized.append(item)
                continue
            copy = dict(item)
            copy.setdefault("course_name", record["name"])
            copy.setdefault("course", record["name"])
            copy.setdefault("course_id", record["id"])
            normalized.append(copy)
        return normalized

    def get(self, section, course, force=False):
        record = self._record(course)
        if record is None:
            return {"status": "Unknown", "message": "Course is no longer in the current Moodle list."}
        if section not in self._loaders:
            return {"status": "Error", "message": f"Unsupported registry section: {section}"}

        if not force and section in record["sections"] and self._is_fresh(record, section):
            return deepcopy(record["sections"][section])

        loader = self._loaders[section]
        value = loader(record["name"])
        value = self._normalize_items(value, record)

        # Do not preserve transient authentication/unknown failures as trusted state.
        cacheable = not (
            isinstance(value, dict)
            and value.get("status") in {"Error", "Unknown"}
        )
        if cacheable:
            record["sections"][section] = deepcopy(value)
            record["updated_at"][section] = time.time()
        return value

    def refresh(self, course, sections=None):
        targets = list(sections or self._loaders.keys())
        return {section: self.get(section, course, force=True) for section in targets}

    def invalidate(self, course=None, section=None):
        self.sync()
        records = self._courses.values()
        if course is not None:
            record = self._record(course)
            records = [record] if record else []
        for record in records:
            if section is None:
                record["sections"].clear()
                record["updated_at"].clear()
            else:
                record["sections"].pop(section, None)
                record["updated_at"].pop(section, None)

    def workspace(self):
        self.sync()
        return deepcopy(self._courses)

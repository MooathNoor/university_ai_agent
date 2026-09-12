from datetime import datetime
import time
import re

from bs4 import BeautifulSoup
from urllib.parse import urljoin

from lms_client import (
    login,
    session,
    BASE_URL,
    get_courses,
    get_assignments as get_course_assignments,
    get_quizzes as get_course_quizzes,
)

from moodle_tools import (
    get_all_assignments,
    get_all_quizzes,
)


# ============================================================
# COURSE CACHE
# ============================================================

COURSE_CACHE_SECONDS = 60

_courses_cache = None
_courses_cache_time = 0


def get_cached_courses(force=False):
    """
    Load Moodle courses and cache them for a short period.

    This avoids requesting the course list from Moodle
    repeatedly during the same conversation.
    """

    global _courses_cache
    global _courses_cache_time

    now = time.time()

    if (
        not force
        and _courses_cache is not None
        and now - _courses_cache_time < COURSE_CACHE_SECONDS
    ):
        print("[DEBUG] Using cached Moodle courses.")
        return _courses_cache

    print("[DEBUG] Loading courses from Moodle...")

    try:
        courses = get_courses()
    except Exception as error:
        print(f"[DEBUG] Course loading error: {error}")
        return []

    if courses:
        _courses_cache = courses
        _courses_cache_time = now
        print(f"[DEBUG] Cached {len(courses)} Moodle courses.")
        return courses

    return []


# ============================================================
# COURSE HELPERS
# ============================================================

def get_course_name(course):
    return (
        course.get("fullname")
        or course.get("name")
        or course.get("course_name")
        or "Unknown Course"
    )


def get_course_id(course):
    return course.get("id") or course.get("course_id")


def normalize_course_text(text):
    """
    Normalize course names and user text for basic matching.
    """

    if not text:
        return ""

    text = str(text).lower()

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text)

    return " ".join(text.split())


def get_course_display_name(course):
    return get_course_name(course)


# ============================================================
# ATTENDANCE
# ============================================================

def get_attendance(course_name):
    """
    Get real attendance data from Moodle.
    """

    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "Could not load courses from Moodle."
        }

    target_course = find_course(course_name, courses)

    if target_course is None:
        return {
            "status": "Unknown",
            "message": f"Course '{course_name}' was not found."
        }

    course_id = get_course_id(target_course)

    if course_id is None:
        return {
            "status": "Error",
            "message": "The course does not have a valid Moodle ID."
        }

    course_url = f"{BASE_URL}/course/view.php?id={course_id}"

    print(f"[DEBUG] Opening attendance course page: {course_url}")

    try:
        response = session.get(course_url, timeout=20)
    except Exception as error:
        return {
            "status": "Error",
            "message": f"Could not open course page: {error}"
        }

    if response.status_code != 200:
        return {
            "status": "Error",
            "message": f"Moodle returned HTTP {response.status_code}."
        }

    soup = BeautifulSoup(response.text, "html.parser")

    attendance_link = None

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if "/mod/attendance/view.php?id=" in href:
            attendance_link = urljoin(BASE_URL, href)
            break

    if not attendance_link:
        return {
            "status": "Empty",
            "course": get_course_name(target_course),
            "message": "No attendance activity was found for this course."
        }

    print(f"[DEBUG] Attendance URL: {attendance_link}")

    try:
        attendance_response = session.get(
            attendance_link,
            timeout=20
        )
    except Exception as error:
        return {
            "status": "Error",
            "message": f"Could not open attendance page: {error}"
        }

    if attendance_response.status_code != 200:
        return {
            "status": "Error",
            "message": (
                f"Attendance page returned HTTP "
                f"{attendance_response.status_code}."
            )
        }

    attendance_soup = BeautifulSoup(
        attendance_response.text,
        "html.parser"
    )

    summary = {}

    summary_table = attendance_soup.select_one("table.attlist")

    if summary_table:
        for row in summary_table.find_all("tr"):
            cells = row.find_all(["td", "th"])

            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True)
                value = cells[1].get_text(" ", strip=True)

                if key:
                    summary[key] = value

    sessions = []

    for row in attendance_soup.select(
        "table.generaltable tbody tr"
    ):
        cells = row.find_all("td")

        if not cells:
            continue

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        sessions.append(values)

    return {
        "status": "Success",
        "course": get_course_name(target_course),
        "course_id": course_id,
        "summary": summary,
        "sessions": sessions,
    }


# ============================================================
# SCHEDULE
# ============================================================

def get_course_schedule(course_name):
    """
    Get real calendar events for a course from Moodle.
    """

    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "Could not load Moodle courses."
        }

    target_course = find_course(course_name, courses)

    if target_course is None:
        return {
            "status": "Unknown",
            "message": f"Course '{course_name}' was not found."
        }

    course_id = get_course_id(target_course)

    calendar_url = (
        f"{BASE_URL}/calendar/view.php"
        f"?view=month&course={course_id}"
    )

    print(f"[DEBUG] Opening Moodle calendar: {calendar_url}")

    try:
        response = session.get(
            calendar_url,
            timeout=20
        )
    except Exception as error:
        return {
            "status": "Error",
            "message": f"Could not open Moodle calendar: {error}"
        }

    if response.status_code != 200:
        return {
            "status": "Error",
            "message": f"Moodle returned HTTP {response.status_code}."
        }

    soup = BeautifulSoup(response.text, "html.parser")

    events = []

    selectors = [
        "[data-region='event-item']",
        ".calendar_event",
        ".event",
        ".card-body",
    ]

    seen = set()

    for selector in selectors:

        for element in soup.select(selector):

            text = element.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            normalized = normalize_course_text(text)

            if normalized in seen:
                continue

            seen.add(normalized)

            events.append(text)

    return {
        "status": "Success",
        "course": get_course_name(target_course),
        "course_id": course_id,
        "events": events,
    }


# ============================================================
# COURSE INFORMATION
# ============================================================

def get_course_info(course_name):
    """
    Get information about a real Moodle course.
    """

    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    courses = get_cached_courses()

    target_course = find_course(course_name, courses)

    if target_course is None:
        return {
            "status": "Unknown",
            "message": f"Course '{course_name}' was not found."
        }

    course_id = get_course_id(target_course)

    course_url = (
        f"{BASE_URL}/course/view.php?id={course_id}"
    )

    try:
        response = session.get(
            course_url,
            timeout=20
        )
    except Exception as error:
        return {
            "status": "Error",
            "message": f"Could not open course page: {error}"
        }

    if response.status_code != 200:
        return {
            "status": "Error",
            "message": f"Moodle returned HTTP {response.status_code}."
        }

    soup = BeautifulSoup(response.text, "html.parser")

    title = ""

    title_element = soup.select_one(
        "h1, .page-header-headings h1"
    )

    if title_element:
        title = title_element.get_text(
            " ",
            strip=True
        )

    sections = []

    for section in soup.select(
        "li.section, .course-section"
    ):
        section_text = section.get_text(
            " ",
            strip=True
        )

        if section_text:
            sections.append(section_text)

    activities = []
    seen_activities = set()

    # Only real Moodle activities are collected. Navigation/profile/logout links
    # must never be exposed as course resources.
    activity_patterns = [
        ("/mod/assign/", "assignment"),
        ("/mod/quiz/", "quiz"),
        ("/mod/forum/", "forum"),
        ("/mod/resource/", "resource"),
        ("/mod/url/", "url"),
        ("/mod/folder/", "folder"),
        ("/mod/page/", "page"),
        ("/mod/book/", "book"),
        ("/mod/attendance/", "attendance"),
        ("/mod/h5pactivity/", "h5p"),
    ]

    for link in soup.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        text = link.get_text(" ", strip=True)
        if not text or not href:
            continue

        activity_type = None
        for pattern, candidate_type in activity_patterns:
            if pattern in href:
                activity_type = candidate_type
                break
        if activity_type is None:
            continue

        absolute_url = urljoin(BASE_URL, href)
        key = (activity_type, absolute_url)
        if key in seen_activities:
            continue
        seen_activities.add(key)

        section_name = ""
        parent_section = link.find_parent(["li", "section"], class_=re.compile(r"section|course-section"))
        if parent_section:
            heading = parent_section.select_one(
                ".sectionname, .section-name, h3, h4, [data-for='section_title']"
            )
            if heading:
                section_name = heading.get_text(" ", strip=True)

        activities.append({
            "name": text,
            "type": activity_type,
            "url": absolute_url,
            "section": section_name,
        })

    return {
        "status": "Success",
        "course": get_course_name(target_course),
        "course_id": course_id,
        "title": title,
        "sections": sections,
        "activities": activities,
    }


# ============================================================
# MY COURSES
# ============================================================

def get_my_courses():
    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Empty",
            "courses": []
        }

    result = []

    for course in courses:
        result.append({
            "id": get_course_id(course),
            "name": get_course_name(course)
        })

    return {
        "status": "Success",
        "courses": result
    }


# ============================================================
# COURSE FINDER
# ============================================================

def find_course(course_name, courses):
    """
    Find a course using several deterministic strategies.

    This function does NOT hardcode current university courses.
    It works from whatever Moodle returns.
    """

    if not course_name or not courses:
        return None

    query = normalize_course_text(course_name)

    if not query:
        return None

    # --------------------------------------------------------
    # 1. Exact normalized match
    # --------------------------------------------------------

    for course in courses:

        name = get_course_name(course)

        if normalize_course_text(name) == query:
            return course

    # --------------------------------------------------------
    # 2. Query contained in course name
    # --------------------------------------------------------

    for course in courses:

        name = normalize_course_text(
            get_course_name(course)
        )

        if query in name:
            return course

    # --------------------------------------------------------
    # 3. Course name contained in query
    # --------------------------------------------------------

    for course in courses:

        name = normalize_course_text(
            get_course_name(course)
        )

        if name and name in query:
            return course

    # --------------------------------------------------------
    # 4. Meaningful token matching
    # --------------------------------------------------------

    query_tokens = {
        token
        for token in query.split()
        if len(token) >= 4
    }

    if query_tokens:

        best_course = None
        best_score = 0

        for course in courses:

            name = normalize_course_text(
                get_course_name(course)
            )

            name_tokens = {
                token
                for token in name.split()
                if len(token) >= 4
            }

            if not name_tokens:
                continue

            overlap = query_tokens.intersection(
                name_tokens
            )

            score = len(overlap)

            if score > best_score:
                best_score = score
                best_course = course

        if best_course and best_score > 0:
            return best_course

    return None


# ============================================================
# ASSIGNMENTS
# ============================================================

def get_assignments(course_name=None):
    """Return real Moodle assignments.

    A single-course request goes directly to that Moodle course page instead of
    scanning every enrolled course first. Cross-course callers can still omit
    ``course_name`` and use the existing aggregate loader.
    """
    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    if not course_name:
        assignments = get_all_assignments()
        return [] if assignments is None else assignments

    courses = get_cached_courses()
    target_course = find_course(course_name, courses)
    if target_course is None:
        return {
            "status": "Unknown",
            "message": f"Course '{course_name}' was not found."
        }

    real_course_name = get_course_name(target_course)
    course_id = get_course_id(target_course)
    assignments = get_course_assignments(course_id) or []

    result = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        item = dict(assignment)
        item["course_name"] = real_course_name
        item["course"] = real_course_name
        item["course_id"] = course_id
        result.append(item)
    return result


# ============================================================
# QUIZZES
# ============================================================

def get_quizzes(course_name=None):
    """Return real Moodle quizzes.

    A single-course request goes directly to that Moodle course page. Omitting
    ``course_name`` preserves the existing all-course aggregate behavior.
    """
    if not login():
        return {
            "status": "Error",
            "message": "Could not authenticate with Moodle."
        }

    if not course_name:
        quizzes = get_all_quizzes()
        return [] if quizzes is None else quizzes

    courses = get_cached_courses()
    target_course = find_course(course_name, courses)
    if target_course is None:
        return {
            "status": "Unknown",
            "message": f"Course '{course_name}' was not found."
        }

    real_course_name = get_course_name(target_course)
    course_id = get_course_id(target_course)
    quizzes = get_course_quizzes(course_id) or []

    result = []
    for quiz in quizzes:
        if not isinstance(quiz, dict):
            continue
        item = dict(quiz)
        item["course_name"] = real_course_name
        item["course"] = real_course_name
        item["course_id"] = course_id
        result.append(item)
    return result


# ============================================================
# QUIZ RESULTS / GRADES
# ============================================================

def _clean_number_text(value):
    text = str(value or '').strip().replace(',', '')
    match = re.search(r'\d+(?:\.\d+)?', text)
    return match.group(0) if match else ''


def _resolve_quiz_url(item):
    """Resolve a real Moodle quiz URL from the item or the course page."""
    url = str(item.get('url', '')).strip() if isinstance(item, dict) else ''
    if '/mod/quiz/' in url:
        return url

    course_id = item.get('course_id') if isinstance(item, dict) else None
    name = str(item.get('name', '')).strip() if isinstance(item, dict) else ''
    if not course_id or not name:
        return ''

    try:
        response = session.get(f"{BASE_URL}/course/view.php?id={course_id}", timeout=20)
    except Exception:
        return ''
    if response.status_code != 200:
        return ''

    target = re.sub(r'\s+', ' ', name).strip().lower()
    soup = BeautifulSoup(response.text, 'html.parser')
    candidates = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if '/mod/quiz/view.php' not in href:
            continue
        label = re.sub(r'\s+', ' ', link.get_text(' ', strip=True)).strip().lower()
        if label == target:
            return urljoin(BASE_URL, href)
        if target and (target in label or label in target):
            candidates.append(urljoin(BASE_URL, href))
    return candidates[0] if len(candidates) == 1 else ''


def _extract_quiz_grade_from_soup(soup):
    """Extract the student's visible quiz result conservatively from Moodle.

    Returns a dict with grade_text/grade/max_grade/state. It never invents a mark.
    """
    result = {
        'grade_text': '',
        'grade': '',
        'max_grade': '',
        'state': 'unknown',
    }

    # 1) Attempt summary table is the most reliable source on Moodle quiz pages.
    for table in soup.find_all('table'):
        headers = [
            re.sub(r'\s+', ' ', cell.get_text(' ', strip=True)).strip().lower()
            for cell in table.find_all('th')
        ]
        if not headers:
            continue
        grade_idx = next((i for i, h in enumerate(headers) if h in {'grade', 'الدرجة', 'العلامة'} or 'grade' in h or 'درج' in h or 'علام' in h), None)
        marks_idx = next((i for i, h in enumerate(headers) if 'marks' in h or 'mark' in h or 'العلامات' in h), None)
        state_idx = next((i for i, h in enumerate(headers) if 'state' in h or 'الحالة' in h), None)
        if grade_idx is None and marks_idx is None:
            continue

        rows = table.select('tbody tr') or table.find_all('tr')[1:]
        parsed_rows = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            values = [re.sub(r'\s+', ' ', c.get_text(' ', strip=True)).strip() for c in cells]
            state = values[state_idx] if state_idx is not None and state_idx < len(values) else ''
            grade_text = ''
            if grade_idx is not None and grade_idx < len(values):
                grade_text = values[grade_idx]
            elif marks_idx is not None and marks_idx < len(values):
                grade_text = values[marks_idx]
            if grade_text and re.search(r'\d', grade_text):
                parsed_rows.append((state, grade_text))

        if parsed_rows:
            # Moodle lists attempts chronologically. The last visible numeric result is
            # the safest representation of the most recent completed attempt.
            state, grade_text = parsed_rows[-1]
            result['grade_text'] = grade_text
            result['state'] = state or 'visible'
            nums = re.findall(r'\d+(?:\.\d+)?', grade_text.replace(',', ''))
            if nums:
                result['grade'] = nums[0]
            if len(nums) >= 2:
                result['max_grade'] = nums[1]
            return result

    # 2) Common Moodle text such as: "Grade 8.00 out of 10.00".
    page_text = re.sub(r'\s+', ' ', soup.get_text(' ', strip=True))
    patterns = [
        r'Grade\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:out of|/)\s*([0-9]+(?:\.[0-9]+)?)',
        r'(?:الدرجة|العلامة)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:من|/)\s*([0-9]+(?:\.[0-9]+)?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.I)
        if match:
            result['grade'] = match.group(1)
            result['max_grade'] = match.group(2)
            result['grade_text'] = f"{match.group(1)} / {match.group(2)}"
            result['state'] = 'visible'
            return result

    # 3) Detect completed attempts even when Moodle does not expose a grade.
    lowered = page_text.lower()
    if 'finished' in lowered or 'مكتمل' in lowered or 'تم الانتهاء' in lowered:
        result['state'] = 'finished_no_grade'
    return result


def get_quiz_grades(course_name=None, quizzes=None):
    """Read real visible quiz grades from each Moodle quiz page.

    If ``quizzes`` is supplied, only those already-resolved quiz items are inspected.
    Otherwise quizzes are loaded normally, optionally filtered by course_name.
    """
    if not login():
        return {'status': 'Error', 'message': 'Could not authenticate with Moodle.'}

    items = quizzes if isinstance(quizzes, list) else get_quizzes(course_name)
    if isinstance(items, dict):
        return items
    items = [item for item in (items or []) if isinstance(item, dict)]

    results = []
    for item in items:
        copy = dict(item)
        url = _resolve_quiz_url(copy)
        copy['url'] = url or copy.get('url', '')
        if not url:
            copy.update({
                'grade_text': '', 'grade': '', 'max_grade': '',
                'grade_state': 'unknown',
                'grade_message': 'Quiz page URL could not be resolved.',
            })
            results.append(copy)
            continue
        try:
            response = session.get(url, timeout=20)
        except Exception as error:
            copy.update({
                'grade_text': '', 'grade': '', 'max_grade': '',
                'grade_state': 'unknown',
                'grade_message': f'Could not open quiz page: {error}',
            })
            results.append(copy)
            continue
        if response.status_code != 200:
            copy.update({
                'grade_text': '', 'grade': '', 'max_grade': '',
                'grade_state': 'unknown',
                'grade_message': f'Quiz page returned HTTP {response.status_code}.',
            })
            results.append(copy)
            continue

        parsed = _extract_quiz_grade_from_soup(BeautifulSoup(response.text, 'html.parser'))
        copy['grade_text'] = parsed.get('grade_text', '')
        copy['grade'] = parsed.get('grade', '')
        copy['max_grade'] = parsed.get('max_grade', '')
        copy['grade_state'] = parsed.get('state', 'unknown')
        results.append(copy)
    return results


# ============================================================
# MOCK / FUTURE DATA
# ============================================================

def get_grades():
    """
    Grades are not connected to Moodle yet.

    IMPORTANT:
    Do not treat this as real student grade data.
    """

    return {
        "status": "Unavailable",
        "message": (
            "Real Moodle grade scraping has not been "
            "implemented yet."
        )
    }


def get_announcements():
    """
    Announcements are not connected to Moodle yet.
    """

    return {
        "status": "Unavailable",
        "message": (
            "Real Moodle announcements have not been "
            "implemented yet."
        )
    }


# ============================================================
# DATE PARSING
# ============================================================

def parse_moodle_date(date_text):
    """
    Parse common Moodle date formats.
    """

    if not date_text:
        return None

    text = str(date_text).strip()

    formats = [
        "%d/%m/%Y, %I:%M %p",
        "%d/%m/%Y %I:%M %p",
        "%d-%m-%Y, %I:%M %p",
        "%d-%m-%Y %I:%M %p",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y, %H:%M",
        "%d/%m/%Y %H:%M",
        "%A, %d %B %Y, %I:%M %p",
        "%A, %d %B %Y, %H:%M",
        "%d %B %Y, %I:%M %p",
        "%d %B %Y, %H:%M",
    ]

    for date_format in formats:

        try:
            return datetime.strptime(
                text,
                date_format
            )
        except ValueError:
            continue

    return None


# ============================================================
# UPCOMING DEADLINES
# ============================================================

def get_upcoming_deadlines():
    """
    Combine assignments and quizzes into one chronological list.
    """

    now = datetime.now()

    assignments = get_assignments()
    quizzes = get_quizzes()

    result = []

    if isinstance(assignments, list):

        for assignment in assignments:

            date_text = (
                assignment.get("due_date")
                or assignment.get("due")
            )

            parsed_date = parse_moodle_date(
                date_text
            )

            if parsed_date is None:
                continue

            if parsed_date < now:
                continue

            result.append({
                "type": "assignment",
                "course_id": assignment.get(
                    "course_id"
                ),
                "course": assignment.get(
                    "course_name"
                ) or assignment.get(
                    "course"
                ),
                "name": assignment.get(
                    "name",
                    ""
                ),
                "due_date": date_text,
                "description": assignment.get(
                    "description",
                    ""
                ),
                "url": assignment.get(
                    "url",
                    ""
                ),
                "_parsed_date": parsed_date,
            })

    if isinstance(quizzes, list):

        for quiz in quizzes:

            date_text = (
                quiz.get("closed_date")
                or quiz.get("close")
            )

            parsed_date = parse_moodle_date(
                date_text
            )

            if parsed_date is None:
                continue

            if parsed_date < now:
                continue

            result.append({
                "type": "quiz",
                "course_id": quiz.get(
                    "course_id"
                ),
                "course": quiz.get(
                    "course_name"
                ) or quiz.get(
                    "course"
                ),
                "name": quiz.get(
                    "name",
                    ""
                ),
                "due_date": date_text,
                "description": quiz.get(
                    "description",
                    ""
                ),
                "url": quiz.get(
                    "url",
                    ""
                ),
                "_parsed_date": parsed_date,
            })

    result.sort(
        key=lambda item: item["_parsed_date"]
    )

    for item in result:
        item.pop("_parsed_date", None)

    return result

# ============================================================
# PENDING WORK / SUBMISSION STATE
# ============================================================

def _normalized_page_text(soup):
    return " ".join(soup.stripped_strings).lower()


def _field_text(item, *names):
    for name in names:
        value = item.get(name) if isinstance(item, dict) else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _activity_is_current(item, kind, now=None):
    """Return True/False/None for whether an item is still actionable now."""
    now = now or datetime.now()
    if kind == "assignment":
        end_text = _field_text(item, "cutoff_date", "due_date", "due", "close")
    else:
        end_text = _field_text(item, "closed_date", "close", "due_date", "due")
    parsed = parse_moodle_date(end_text)
    if parsed is None:
        return None
    return parsed >= now


def _inspect_assignment_submission(item):
    """Inspect real assignment data/page and return done/pending/unknown."""
    direct = " ".join(
        str(item.get(key, ""))
        for key in ("submission_status", "status", "state", "submissionstate")
    ).lower()
    submitted_markers = [
        "submitted for grading", "submitted", "تم التسليم", "تم الارسال", "تم الإرسال",
    ]
    pending_markers = [
        "no submission", "not submitted", "لم يتم التسليم", "لا يوجد تسليم",
    ]
    if any(marker in direct for marker in submitted_markers):
        return "done"
    if any(marker in direct for marker in pending_markers):
        return "pending"

    url = str(item.get("url", "")).strip()
    if not url:
        return "unknown"
    try:
        response = session.get(url, timeout=20)
    except Exception:
        return "unknown"
    if response.status_code != 200:
        return "unknown"
    text = _normalized_page_text(BeautifulSoup(response.text, "html.parser"))

    # Order matters: explicit negative phrases before the generic word submitted.
    if any(marker in text for marker in pending_markers):
        return "pending"
    if any(marker in text for marker in submitted_markers):
        return "done"
    return "unknown"


def _inspect_quiz_attempt(item):
    """Inspect a real quiz page and conservatively infer attempt completion."""
    direct = " ".join(
        str(item.get(key, ""))
        for key in ("attempt_status", "status", "state", "attempts_made", "attempts")
    ).lower()
    if any(marker in direct for marker in ("finished", "completed", "submitted", "مكتمل")):
        return "done"

    url = str(item.get("url", "")).strip()
    if not url:
        return "unknown"
    try:
        response = session.get(url, timeout=20)
    except Exception:
        return "unknown"
    if response.status_code != 200:
        return "unknown"
    soup = BeautifulSoup(response.text, "html.parser")
    text = _normalized_page_text(soup)

    # Moodle commonly renders completed attempts with a summary table/state.
    if (
        "state finished" in text
        or "attempt state finished" in text
        or "finished" in text and "review" in text
    ):
        return "done"

    # A start/attempt button indicates that an actionable attempt exists. We only
    # use it as pending when there is no evidence of a completed attempt.
    button_text = " ".join(
        element.get_text(" ", strip=True).lower()
        for element in soup.select("button, input[type='submit'], a.btn")
    )
    if any(marker in button_text for marker in ("attempt quiz now", "start attempt", "ابدأ المحاولة", "بدء المحاولة")):
        return "pending"
    return "unknown"


def get_pending_work():
    """Check current assignments/quizzes and their real Moodle completion state.

    Returns Success only when a yes/no answer is grounded. If active items exist
    but Moodle does not expose enough state to verify them, returns Unknown rather
    than pretending that merely seeing an activity means it is unfinished.
    """
    if not login():
        return {"status": "Error", "message": "Could not authenticate with Moodle."}

    now = datetime.now()
    assignments = get_assignments()
    quizzes = get_quizzes()
    pending = []
    unknown = []
    checked = []

    sources = []
    if isinstance(assignments, list):
        sources.extend(("assignment", item) for item in assignments if isinstance(item, dict))
    if isinstance(quizzes, list):
        sources.extend(("quiz", item) for item in quizzes if isinstance(item, dict))

    for kind, item in sources:
        current = _activity_is_current(item, kind, now=now)
        # Closed/past work is irrelevant to "currently pending".
        if current is False:
            continue
        # Without an end date, still inspect state, but keep uncertainty visible.
        state = (
            _inspect_assignment_submission(item)
            if kind == "assignment"
            else _inspect_quiz_attempt(item)
        )
        record = {
            "type": kind,
            "name": item.get("name", ""),
            "course": item.get("course_name") or item.get("course", ""),
            "course_id": item.get("course_id"),
            "url": item.get("url", ""),
            "state": state,
        }
        checked.append(record)
        if state == "pending":
            pending.append(record)
        elif state == "unknown" and current is not False:
            unknown.append(record)

    if pending:
        return {
            "status": "Success",
            "has_pending": True,
            "pending": pending,
            "unknown": unknown,
            "checked": checked,
        }

    # If there are no active items at all, 'no' is grounded even without status pages.
    active_or_unknown = [
        (kind, item)
        for kind, item in sources
        if _activity_is_current(item, kind, now=now) is not False
    ]
    if not active_or_unknown:
        return {
            "status": "Success",
            "has_pending": False,
            "pending": [],
            "unknown": [],
            "checked": checked,
        }

    if unknown:
        return {
            "status": "Unknown",
            "message": "Moodle did not expose enough submission/attempt state to verify every active item.",
            "pending": [],
            "unknown": unknown,
            "checked": checked,
        }

    return {
        "status": "Success",
        "has_pending": False,
        "pending": [],
        "unknown": [],
        "checked": checked,
    }


# ============================================================
# COURSE RESOURCES / FILES
# ============================================================

def get_course_resources(course_name):
    """Return real Moodle course resources/links for one course.

    This intentionally reports only activities that are visible on the real
    Moodle course page. It does not invent filenames or pretend that a link is
    a downloadable file when Moodle exposes only a page/URL.
    """
    info = get_course_info(course_name)
    if not isinstance(info, dict):
        return []
    if info.get("status") != "Success":
        return info

    resources = []
    seen = set()
    for activity in info.get("activities", []):
        if not isinstance(activity, dict):
            continue
        activity_type = str(activity.get("type", "")).lower()
        url = str(activity.get("url", "")).strip()
        name = str(activity.get("name", "")).strip()
        if activity_type not in {"resource", "url", "folder", "page", "book"}:
            continue
        key = (name, url)
        if key in seen:
            continue
        seen.add(key)
        resources.append({
            "name": name or "Moodle resource",
            "type": activity_type,
            "url": url,
            "section": str(activity.get("section", "")).strip(),
            "course": info.get("course"),
            "course_id": info.get("course_id"),
        })
    return resources

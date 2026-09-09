from datetime import datetime
import time

from bs4 import BeautifulSoup
from urllib.parse import urljoin

from lms_client import (
    login,
    session,
    BASE_URL,
    get_courses,
    get_assignments as lms_get_assignments,
    get_quizzes as lms_get_quizzes
)


# ============================================================
# COURSE CACHE
# ============================================================

COURSE_CACHE_SECONDS = 60

_courses_cache = None
_courses_cache_time = 0


def get_cached_courses():
    """
    Get the student's Moodle courses.

    Courses are cached for a short period to avoid repeatedly
    requesting the same course list from Moodle.
    """

    global _courses_cache
    global _courses_cache_time

    current_time = time.time()

    # --------------------------------------------------------
    # Use cache if it is still valid
    # --------------------------------------------------------

    if (
        _courses_cache is not None
        and
        current_time - _courses_cache_time < COURSE_CACHE_SECONDS
    ):
        print("\nUsing cached Moodle courses...")
        return _courses_cache

    # --------------------------------------------------------
    # Cache expired or does not exist
    # --------------------------------------------------------

    print("\nLoading courses from Moodle...")

    courses = get_courses()

    if courses:

        _courses_cache = courses
        _courses_cache_time = current_time

    return courses


# ============================================================
# 1. GET ATTENDANCE
# ============================================================

def get_attendance(course_name):
    """
    Get real attendance information from Moodle.

    This function is read-only.
    It does not submit or modify attendance.
    """

    print("\nConnecting to Moodle to get real attendance...")

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    selected_course = None

    search_text = course_name.lower().strip()

    for course in courses:

        course_text = course["name"].lower()

        if search_text in course_text:
            selected_course = course
            break

    if not selected_course:

        search_words = [
            word
            for word in search_text.split()
            if len(word) >= 5
        ]

        for course in courses:

            course_text = course["name"].lower()

            for word in search_words:

                if word in course_text:
                    selected_course = course
                    break

            if selected_course:
                break

    if not selected_course:
        return {
            "status": "Unknown",
            "message": (
                f"Course not found in Moodle: "
                f"{course_name}"
            )
        }

    course_id = selected_course["id"]
    real_course_name = selected_course["name"]

    print(
        f"\nOpening course: "
        f"{real_course_name}"
    )

    course_url = (
        f"{BASE_URL}/course/view.php"
        f"?id={course_id}"
    )

    response = session.get(course_url)

    print(
        f"Course page status: "
        f"{response.status_code}"
    )

    if response.status_code != 200:
        return {
            "status": "Error",
            "message": (
                "Could not open the Moodle "
                "course page."
            )
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    attendance_url = None

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get("href", "")

        if "/mod/attendance/view.php?id=" in href:
            attendance_url = urljoin(
                course_url,
                href
            )
            break

    if not attendance_url:
        return {
            "status": "Unknown",
            "message": (
                f"No Attendance activity was found "
                f"for course: {real_course_name}"
            )
        }

    print(
        f"Attendance URL found: "
        f"{attendance_url}"
    )

    attendance_response = session.get(
        attendance_url
    )

    print(
        f"Attendance page status: "
        f"{attendance_response.status_code}"
    )

    if attendance_response.status_code != 200:
        return {
            "status": "Error",
            "message": (
                "Could not open the Moodle "
                "attendance page."
            )
        }

    attendance_soup = BeautifulSoup(
        attendance_response.text,
        "html.parser"
    )

    full_course_name = real_course_name

    summary_table = attendance_soup.select_one(
        "table.attlist"
    )

    if not summary_table:
        return {
            "status": "Error",
            "message": (
                "Attendance summary table "
                "was not found."
            )
        }

    taken_sessions = "0"
    points = "0 / 0"
    percentage = "0.0%"

    for row in summary_table.find_all("tr"):

        cells = row.find_all("td")

        if len(cells) < 2:
            continue

        label = cells[0].get_text(
            " ",
            strip=True
        )

        value = cells[1].get_text(
            " ",
            strip=True
        )

        if label == "Taken sessions:":
            taken_sessions = value

        elif label == "Points over taken sessions:":
            points = value

        elif label == "Percentage over taken sessions:":
            percentage = value

    sessions = []

    session_table = attendance_soup.select_one(
        "table.generaltable.attwidth.boxaligncenter.table-reboot"
    )

    if session_table:

        rows = session_table.select(
            "tbody tr"
        )

        for row in rows:

            cells = row.find_all("td")

            if len(cells) < 5:
                continue

            values = [
                cell.get_text(
                    " ",
                    strip=True
                )
                for cell in cells
            ]

            sessions.append({
                "date": values[0],
                "description": values[1],
                "status": values[2],
                "points": values[3],
                "remarks": values[4]
            })

    return {
        "course": full_course_name,
        "taken_sessions": taken_sessions,
        "points": points,
        "percentage": percentage,
        "sessions": sessions
    }


# ============================================================
# 2. GET COURSE SCHEDULE
# ============================================================

def get_course_schedule(course_name):
    """
    Try to get real schedule/event information
    for a specific course from Moodle Calendar.

    IMPORTANT:
    Moodle Calendar may contain course events and deadlines,
    but it may NOT contain the university's weekly lecture
    timetable.

    Therefore this function never returns fake schedule data.
    """

    print(
        "\nConnecting to Moodle Calendar "
        "to get real schedule information..."
    )

    if not course_name:
        return {
            "status": "Unknown",
            "message": "Course name was not provided."
        }

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    search_text = course_name.lower().strip()

    selected_course = None

    for course in courses:

        if course["name"].lower().strip() == search_text:
            selected_course = course
            break

    if not selected_course:

        for course in courses:

            course_text = course["name"].lower()

            if search_text in course_text:
                selected_course = course
                break

    if not selected_course:

        search_words = [
            word
            for word in search_text.split()
            if len(word) >= 5
        ]

        for course in courses:

            course_text = course["name"].lower()

            for word in search_words:

                if word in course_text:
                    selected_course = course
                    break

            if selected_course:
                break

    if not selected_course:

        return {
            "status": "Unknown",
            "message": (
                f"Course not found in Moodle: "
                f"{course_name}"
            )
        }

    real_course_name = selected_course["name"]
    course_id = selected_course["id"]

    print(
        f"Course found: "
        f"{real_course_name}"
    )

    calendar_url = (
        f"{BASE_URL}/calendar/view.php"
        f"?view=month"
        f"&course={course_id}"
    )

    print(
        f"\nOpening Moodle Calendar:"
    )
    print(calendar_url)

    calendar_response = session.get(
        calendar_url
    )

    print(
        f"Calendar page status: "
        f"{calendar_response.status_code}"
    )

    if calendar_response.status_code != 200:

        return {
            "status": "Error",
            "message": (
                "Could not open the Moodle "
                "Calendar page."
            )
        }

    calendar_soup = BeautifulSoup(
        calendar_response.text,
        "html.parser"
    )

    events = []

    possible_event_selectors = [
        ".calendar_event",
        ".event",
        ".calendar_event_course",
        ".calendar_event_user",
        ".calendar_event_global",
        "[data-event-id]",
        "[data-eventtype]"
    ]

    event_elements = []

    for selector in possible_event_selectors:

        found_elements = calendar_soup.select(
            selector
        )

        for element in found_elements:

            if element not in event_elements:
                event_elements.append(element)

    print(
        f"Possible calendar event elements found: "
        f"{len(event_elements)}"
    )

    for element in event_elements:

        event_text = element.get_text(
            " ",
            strip=True
        )

        if not event_text:
            continue

        event_url = None

        link = element.find(
            "a",
            href=True
        )

        if link:

            event_url = urljoin(
                calendar_url,
                link["href"]
            )

        events.append({
            "course": real_course_name,
            "course_id": course_id,
            "title": event_text,
            "url": event_url
        })

    unique_events = []

    seen = set()

    for event in events:

        key = (
            event["title"],
            event["url"]
        )

        if key in seen:
            continue

        seen.add(key)

        unique_events.append(event)

    events = unique_events

    print(
        f"Calendar events extracted: "
        f"{len(events)}"
    )

    if not events:

        return {
            "status": "Unknown",
            "course": real_course_name,
            "course_id": course_id,
            "source": "moodle_calendar",
            "message": (
                "No calendar events were found for this "
                "course in Moodle. The university weekly "
                "lecture timetable may be stored in another "
                "system."
            )
        }

    return {
        "status": "Success",
        "course": real_course_name,
        "course_id": course_id,
        "source": "moodle_calendar",
        "events": events
    }


# ============================================================
# 3. GET COURSE INFO
# ============================================================

def get_course_info(course_name):
    """
    Get real course information from Moodle.
    """

    print(
        "\nConnecting to Moodle to get real "
        "course information..."
    )

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    selected_course = None

    search_text = course_name.lower().strip()

    for course in courses:

        course_text = course["name"].lower()

        if search_text in course_text:
            selected_course = course
            break

    if not selected_course:

        search_words = [
            word
            for word in search_text.split()
            if len(word) >= 5
        ]

        for course in courses:

            course_text = course["name"].lower()

            for word in search_words:

                if word in course_text:
                    selected_course = course
                    break

            if selected_course:
                break

    if not selected_course:
        return {
            "status": "Unknown",
            "message": (
                f"Course not found in Moodle: "
                f"{course_name}"
            )
        }

    course_id = selected_course["id"]
    real_course_name = selected_course["name"]

    print(
        f"\nOpening course: "
        f"{real_course_name}"
    )

    course_url = (
        f"{BASE_URL}/course/view.php"
        f"?id={course_id}"
    )

    response = session.get(course_url)

    print(
        f"Course page status: "
        f"{response.status_code}"
    )

    if response.status_code != 200:
        return {
            "status": "Error",
            "message": (
                "Could not open the Moodle "
                "course page."
            )
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    full_course_name = real_course_name

    h1 = soup.find("h1")

    if h1:

        h1_text = h1.get_text(
            " ",
            strip=True
        )

        if h1_text:
            full_course_name = h1_text

    page_title = ""

    if soup.title:

        page_title = soup.title.get_text(
            " ",
            strip=True
        )

    sections = []

    moodle_sections = soup.select(
        "li.section"
    )

    for section_element in moodle_sections:

        section_name = ""

        section_name_element = section_element.select_one(
            ".sectionname"
        )

        if section_name_element:

            section_name = section_name_element.get_text(
                " ",
                strip=True
            )

        if not section_name:

            section_heading = section_element.find(
                ["h3", "h4", "h2"]
            )

            if section_heading:

                section_name = section_heading.get_text(
                    " ",
                    strip=True
                )

        if not section_name:
            continue

        section_activities = []

        for link in section_element.find_all(
            "a",
            href=True
        ):

            text = link.get_text(
                " ",
                strip=True
            )

            href = link.get("href", "")

            if not text or not href:
                continue

            if "/mod/" not in href:
                continue

            activity_type = "Unknown"

            if "/mod/assign/" in href:
                activity_type = "Assignment"

            elif "/mod/quiz/" in href:
                activity_type = "Quiz"

            elif "/mod/forum/" in href:
                activity_type = "Forum"

            elif "/mod/resource/" in href:
                activity_type = "File"

            elif "/mod/url/" in href:
                activity_type = "URL"

            elif "/mod/attendance/" in href:
                activity_type = "Attendance"

            elif "/mod/h5pactivity/" in href:
                activity_type = "H5P"

            activity = {
                "name": text,
                "type": activity_type,
                "url": href
            }

            duplicate = False

            for existing_activity in section_activities:

                if (
                    existing_activity["name"] == activity["name"]
                    and
                    existing_activity["url"] == activity["url"]
                ):
                    duplicate = True
                    break

            if not duplicate:
                section_activities.append(activity)

        sections.append({
            "name": section_name,
            "activities": section_activities
        })

    activities = []

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = link.get_text(
            " ",
            strip=True
        )

        href = link.get("href")

        if not text or not href:
            continue

        if "/mod/" not in href:
            continue

        activity_type = "Unknown"

        if "/mod/assign/" in href:
            activity_type = "Assignment"

        elif "/mod/quiz/" in href:
            activity_type = "Quiz"

        elif "/mod/forum/" in href:
            activity_type = "Forum"

        elif "/mod/resource/" in href:
            activity_type = "File"

        elif "/mod/url/" in href:
            activity_type = "URL"

        elif "/mod/attendance/" in href:
            activity_type = "Attendance"

        elif "/mod/h5pactivity/" in href:
            activity_type = "H5P"

        activities.append({
            "name": text,
            "type": activity_type,
            "url": href
        })

    unique_activities = []

    seen = set()

    for activity in activities:

        key = (
            activity["name"],
            activity["url"]
        )

        if key in seen:
            continue

        seen.add(key)

        unique_activities.append(activity)

    return {
        "id": course_id,
        "name": full_course_name,
        "page_title": page_title,
        "url": course_url,
        "sections": sections,
        "activities": unique_activities
    }


# ============================================================
# 4. GET MY COURSES
# ============================================================

def get_my_courses():
    """
    Return the courses currently registered
    by the student from Moodle.
    """

    print(
        "\nConnecting to Moodle to get real courses..."
    )

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    return courses


# ============================================================
# 5. GET ASSIGNMENTS
# ============================================================

def get_assignments(course_name=None):
    """
    Return real assignments from Moodle.

    If course_name is provided, return assignments
    for that course only.

    If course_name is not provided, return assignments
    from all available Moodle courses.
    """

    print(
        "\nConnecting to Moodle to get real assignments..."
    )

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    if course_name:

        search_text = course_name.lower().strip()

        selected_course = None

        for course in courses:

            course_text = course["name"].lower()

            if search_text == course_text:
                selected_course = course
                break

        if not selected_course:

            for course in courses:

                course_text = course["name"].lower()

                if search_text in course_text:
                    selected_course = course
                    break

        if not selected_course:

            search_words = [
                word
                for word in search_text.split()
                if len(word) >= 5
            ]

            for course in courses:

                course_text = course["name"].lower()

                for word in search_words:

                    if word in course_text:
                        selected_course = course
                        break

                if selected_course:
                    break

        if not selected_course:

            return {
                "status": "Unknown",
                "message": (
                    f"Course not found in Moodle: "
                    f"{course_name}"
                )
            }

        print(
            f"\nGetting assignments for selected course: "
            f"{selected_course['name']}"
        )

        assignments = lms_get_assignments(
            selected_course["id"]
        )

        for assignment in assignments:
            assignment["course"] = selected_course["name"]

        if not assignments:

            return {
                "status": "Unknown",
                "message": (
                    f"No assignments found for course: "
                    f"{selected_course['name']}"
                )
            }

        return assignments

    all_assignments = []

    for course in courses:

        print(
            f"\nGetting assignments for: "
            f"{course['name']}"
        )

        assignments = lms_get_assignments(
            course["id"]
        )

        for assignment in assignments:

            assignment["course"] = course["name"]

            all_assignments.append(
                assignment
            )

    return all_assignments


# ============================================================
# 6. GET GRADES
# ============================================================

def get_grades():
    """
    Get student grades.

    Currently uses mock data.
    """

    return [
        {
            "course": "Artificial Intelligence",
            "grade": 85,
            "status": "Passed"
        },
        {
            "course": "Database",
            "grade": 78,
            "status": "Passed"
        },
        {
            "course": "Python",
            "grade": 92,
            "status": "Passed"
        }
    ]


# ============================================================
# 7. GET ANNOUNCEMENTS
# ============================================================

def get_announcements():
    """
    Get university announcements.

    Currently uses mock data.
    """

    return [
        {
            "course": "Artificial Intelligence",
            "title": "AI Lecture Postponed",
            "date": "2026-09-09"
        },
        {
            "course": "Database",
            "title": "SQL Assignment Reminder",
            "date": "2026-09-10"
        },
        {
            "course": "Python",
            "title": "Python Quiz",
            "date": "2026-09-11"
        }
    ]


# ============================================================
# 8. GET QUIZZES
# ============================================================

def get_quizzes(course_name=None):
    """
    Return real quizzes from Moodle.

    If course_name is provided:
        ONLY that course is searched.

    If course_name is not provided:
        all available Moodle courses are searched.
    """

    print(
        "\nConnecting to Moodle to get real quizzes..."
    )

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_cached_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    if course_name:

        search_text = course_name.lower().strip()

        selected_course = None

        for course in courses:

            course_text = course["name"].lower()

            if search_text == course_text:

                selected_course = course
                break

        if not selected_course:

            for course in courses:

                course_text = course["name"].lower()

                if search_text in course_text:

                    selected_course = course
                    break

        if not selected_course:

            search_words = [
                word
                for word in search_text.split()
                if len(word) >= 5
            ]

            for course in courses:

                course_text = course["name"].lower()

                matched = False

                for word in search_words:

                    if word in course_text:

                        matched = True
                        break

                if matched:

                    selected_course = course
                    break

        if not selected_course:

            return {
                "status": "Unknown",
                "message": (
                    f"Course not found in Moodle: "
                    f"{course_name}"
                )
            }

        print(
            f"\nGetting quizzes for SELECTED course ONLY: "
            f"{selected_course['name']}"
        )

        quizzes = lms_get_quizzes(
            selected_course["id"]
        )

        for quiz in quizzes:

            quiz["course"] = selected_course["name"]

        print(
            f"Selected course quizzes returned: "
            f"{len(quizzes)}"
        )

        if not quizzes:

            return {
                "status": "Unknown",
                "message": (
                    f"No quizzes found for course: "
                    f"{selected_course['name']}"
                )
            }

        return quizzes

    all_quizzes = []

    for course in courses:

        print(
            f"\nGetting quizzes for: "
            f"{course['name']}"
        )

        quizzes = lms_get_quizzes(
            course["id"]
        )

        for quiz in quizzes:

            quiz["course"] = course["name"]

            all_quizzes.append(
                quiz
            )

    return all_quizzes


# ============================================================
# 9. GET UPCOMING DEADLINES
# ============================================================

def get_upcoming_deadlines():
    """
    Return only real upcoming assignments from Moodle.

    Past assignments are excluded.

    Quizzes are not included yet.
    """

    assignments = get_assignments()

    deadlines = []

    now = datetime.now()

    if isinstance(assignments, list):

        for assignment in assignments:

            due_date = assignment.get("due")

            if not due_date:
                continue

            parsed_due_date = None

            date_formats = [
                "%d/%m/%Y, %I:%M %p",
                "%d/%m/%Y %I:%M %p",
                "%d-%m-%Y, %I:%M %p",
                "%d-%m-%Y %I:%M %p",
                "%Y-%m-%d %H:%M"
            ]

            for date_format in date_formats:

                try:
                    parsed_due_date = datetime.strptime(
                        due_date.strip(),
                        date_format
                    )
                    break

                except ValueError:
                    continue

            if parsed_due_date is None:
                continue

            if parsed_due_date <= now:
                continue

            deadlines.append({
                "course": assignment.get("course"),
                "title": assignment.get("name"),
                "type": "Assignment",
                "due_date": due_date,
                "status": assignment.get(
                    "submission_status"
                )
            })

    if deadlines:

        def parse_deadline_date(item):

            due_date = item["due_date"].strip()

            date_formats = [
                "%d/%m/%Y, %I:%M %p",
                "%d/%m/%Y %I:%M %p",
                "%d-%m-%Y, %I:%M %p",
                "%d-%m-%Y %I:%M %p",
                "%Y-%m-%d %H:%M"
            ]

            for date_format in date_formats:

                try:
                    return datetime.strptime(
                        due_date,
                        date_format
                    )

                except ValueError:
                    continue

            return datetime.max

        deadlines.sort(
            key=parse_deadline_date
        )

    return deadlines
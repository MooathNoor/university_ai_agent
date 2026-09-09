from datetime import datetime

from bs4 import BeautifulSoup

from lms_client import (
    login,
    session,
    BASE_URL,
    get_courses,
    get_assignments as lms_get_assignments
)


# ============================================================
# 1. GET ATTENDANCE
# ============================================================

def get_attendance(course_name):
    """
    Get real attendance information from Moodle.

    The function:
        1. Logs in to Moodle.
        2. Finds the requested course.
        3. Opens the course page.
        4. Finds the Attendance activity dynamically.
        5. Opens the Attendance page.
        6. Reads attendance summary information.
        7. Reads attendance sessions.

    This function is read-only.
    It does not submit or modify attendance.
    """

    print("\nConnecting to Moodle to get real attendance...")

    if not login():
        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    courses = get_courses()

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
            attendance_url = href
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
    Get course schedule.

    Currently this function still uses mock data.
    """

    schedules = {
        "Artificial Intelligence": {
            "day": "Sunday",
            "time": "10:00 AM",
            "room": "Lab 2"
        },
        "Database": {
            "day": "Monday",
            "time": "12:00 PM",
            "room": "Room 15"
        },
        "Python": {
            "day": "Tuesday",
            "time": "10:00 AM",
            "room": "Lab 1"
        }
    }

    if course_name not in schedules:
        return {
            "status": "Unknown",
            "message": "Course not found."
        }

    return schedules[course_name]


# ============================================================
# 3. GET COURSE INFO
# ============================================================

def get_course_info(course_name):
    """
    Get real course information from Moodle.

    The function searches the student's Moodle courses
    and opens the matching course page.

    It returns:
        - course id
        - course name
        - course URL
        - sections
        - activities
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

    courses = get_courses()

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

    # ========================================================
    # Extract sections and their activities
    # ========================================================

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

    # ========================================================
    # Extract all activities
    # ========================================================

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

    # --------------------------------------------------------
    # Remove duplicate activities
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Return compact real Moodle information
    #
    # IMPORTANT:
    # page_text was removed.
    # The structured sections and activities are enough
    # for the AI to answer course-information questions.
    # --------------------------------------------------------

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

    courses = get_courses()

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

    courses = get_courses()

    if not courses:
        return {
            "status": "Error",
            "message": "No courses were found in Moodle."
        }

    all_assignments = []

    for course in courses:

        if course_name:

            search_text = course_name.lower().strip()
            course_text = course["name"].lower()

            direct_match = (
                search_text in course_text
            )

            word_match = False

            if not direct_match:

                search_words = [
                    word
                    for word in search_text.split()
                    if len(word) >= 5
                ]

                for word in search_words:

                    if word in course_text:
                        word_match = True
                        break

            if not direct_match and not word_match:
                continue

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

    if course_name and not all_assignments:
        return {
            "status": "Unknown",
            "message": (
                f"No assignments found for course: "
                f"{course_name}"
            )
        }

    return all_assignments


# ============================================================
# 6. GET GRADES
# ============================================================

def get_grades():
    """
    Get student grades.

    Currently this function still uses mock data.
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

    Currently this function still uses mock data.
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

def get_quizzes():
    """
    Get quizzes.

    Currently this function still uses mock data.
    """

    return [
        {
            "course": "Artificial Intelligence",
            "title": "AI Quiz 1",
            "available_date": "2026-09-09",
            "due_date": "2026-09-10",
            "status": "Upcoming"
        },
        {
            "course": "Database",
            "title": "SQL Quiz 1",
            "available_date": "2026-09-11",
            "due_date": "2026-09-12",
            "status": "Upcoming"
        },
        {
            "course": "Python",
            "title": "Python Quiz 1",
            "available_date": "2026-09-09",
            "due_date": "2026-09-11",
            "status": "Upcoming"
        }
    ]


# ============================================================
# 9. GET UPCOMING DEADLINES
# ============================================================

def get_upcoming_deadlines():
    """
    Return only real upcoming assignments from Moodle.

    Past assignments are excluded.

    Quizzes are intentionally not included yet because
    get_quizzes() still contains mock data.
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

    deadlines.sort(
        key=lambda item: datetime.strptime(
            item["due_date"].strip(),
            "%d/%m/%Y, %I:%M %p"
        )
    )

    return deadlines
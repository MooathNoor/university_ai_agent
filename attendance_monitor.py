from bs4 import BeautifulSoup

from lms_client import (
    login,
    session,
    BASE_URL,
    get_courses
)


def find_course(course_name):
    """
    Find a university course using flexible name matching.
    """

    courses = get_courses()

    if not courses:
        return None

    requested = course_name.lower().strip()

    # First: exact/phrase matching
    for course in courses:

        real_name = course.get("name", "").strip()

        if not real_name:
            continue

        if requested in real_name.lower():
            return course

    # Second: word matching
    requested_words = [
        word
        for word in requested.split()
        if len(word) >= 5
    ]

    for course in courses:

        real_name = course.get("name", "").strip()

        if not real_name:
            continue

        real_name_lower = real_name.lower()

        if all(
            word in real_name_lower
            for word in requested_words
        ):
            return course

    return None


def find_attendance_url(course):
    """
    Find the Attendance activity URL inside a Moodle course.
    """

    course_id = course.get("id")

    if not course_id:
        return None

    course_url = (
        f"{BASE_URL}/course/view.php?id={course_id}"
    )

    response = session.get(course_url)

    print(
        f"Course page status: {response.status_code}"
    )

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for link in soup.find_all("a", href=True):

        href = link.get("href", "")

        if "/mod/attendance/view.php?id=" in href:

            if href.startswith("/"):
                href = BASE_URL + href

            return href

    return None


def check_attendance_open(course_name):
    """
    Read-only attendance monitor.

    Checks whether an actionable Present/self-record
    option appears on the Moodle Attendance page.

    This function does NOT submit attendance.
    """

    print(
        f"\nChecking attendance for: {course_name}"
    )

    # -----------------------------------
    # LOGIN
    # -----------------------------------

    if not login():

        return {
            "status": "Error",
            "message": "Could not log in to Moodle."
        }

    # -----------------------------------
    # FIND COURSE
    # -----------------------------------

    course = find_course(course_name)

    if course is None:

        return {
            "status": "Unknown",
            "message": (
                f"Course '{course_name}' "
                "was not found."
            )
        }

    real_course_name = course.get(
        "name",
        course_name
    )

    print(
        f"Course found: {real_course_name}"
    )

    # -----------------------------------
    # FIND ATTENDANCE ACTIVITY
    # -----------------------------------

    attendance_url = find_attendance_url(
        course
    )

    if attendance_url is None:

        return {
            "status": "Error",
            "course": real_course_name,
            "message": (
                "Attendance activity "
                "was not found."
            )
        }

    print(
        f"Attendance URL: {attendance_url}"
    )

    # -----------------------------------
    # OPEN ATTENDANCE PAGE
    # -----------------------------------

    response = session.get(
        attendance_url
    )

    print(
        f"Attendance page status: "
        f"{response.status_code}"
    )

    if response.status_code != 200:

        return {
            "status": "Error",
            "course": real_course_name,
            "message": (
                "Could not open "
                "Attendance page."
            )
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # -----------------------------------
    # LOOK FOR ACTIONABLE PRESENT ELEMENTS
    # -----------------------------------

    present_elements = []

    # Check buttons
    for element in soup.find_all(
        ["button", "input", "a"]
    ):

        text = element.get_text(
            " ",
            strip=True
        )

        value = element.get(
            "value",
            ""
        )

        combined_text = (
            f"{text} {value}"
        ).strip().lower()

        if "present" in combined_text:

            present_elements.append({
                "tag": element.name,
                "text": text or value,
                "href": element.get("href"),
                "type": element.get("type")
            })

    # -----------------------------------
    # LOOK FOR SELF-RECORDING ELEMENTS
    # -----------------------------------

    self_record_elements = []

    for element in soup.find_all(
        ["button", "input", "a"]
    ):

        text = element.get_text(
            " ",
            strip=True
        )

        value = element.get(
            "value",
            ""
        )

        combined_text = (
            f"{text} {value}"
        ).strip().lower()

        if (
            "self-record" in combined_text
            or
            "self record" in combined_text
            or
            "record attendance" in combined_text
        ):

            self_record_elements.append({
                "tag": element.name,
                "text": text or value,
                "href": element.get("href"),
                "type": element.get("type")
            })

    # -----------------------------------
    # DETERMINE STATUS
    # -----------------------------------

    attendance_open = bool(
        present_elements
        or
        self_record_elements
    )

    if attendance_open:

        print(
            "Attendance appears to be OPEN ⚠️"
        )

        return {
            "status": "Open",
            "course": real_course_name,
            "attendance_url": attendance_url,
            "present_elements": present_elements,
            "self_record_elements": (
                self_record_elements
            )
        }

    print(
        "Attendance does not appear to be open."
    )

    return {
        "status": "Closed",
        "course": real_course_name,
        "attendance_url": attendance_url,
        "present_elements": [],
        "self_record_elements": []
    }


if __name__ == "__main__":

    result = check_attendance_open(
        "Numerical Analysis"
    )

    print("\nRESULT:")
    print(result)
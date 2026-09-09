import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import urljoin


load_dotenv()

USERNAME = os.getenv("BAU_USERNAME")
PASSWORD = os.getenv("BAU_PASSWORD")

BASE_URL = "https://elearning3.bau.edu.jo/huson"
LOGIN_URL = f"{BASE_URL}/login/index.php"
MY_COURSES_URL = f"{BASE_URL}/my/"

session = requests.Session()

# Keeps track of the current Moodle session
_logged_in = False


def login():
    """
    Log in to Moodle.

    If the current session is already logged in,
    do not perform the login process again.
    """

    global _logged_in

    # --------------------------------------------------
    # ALREADY LOGGED IN
    # --------------------------------------------------

    if _logged_in:
        print("Already logged in to Moodle ✅")
        return True

    # --------------------------------------------------
    # OPEN LOGIN PAGE
    # --------------------------------------------------

    print("Opening Moodle login page...")

    response = session.get(
        LOGIN_URL
    )

    print(
        f"Login page status: "
        f"{response.status_code}"
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    token_input = soup.find(
        "input",
        {"name": "logintoken"}
    )

    if not token_input:
        print("Login token not found ❌")
        return False

    logintoken = token_input.get("value")

    print("Login token found ✅")
    print("Submitting login...")

    # --------------------------------------------------
    # LOGIN DATA
    # --------------------------------------------------

    login_data = {
        "username": USERNAME,
        "password": PASSWORD,
        "logintoken": logintoken,
    }

    login_response = session.post(
        LOGIN_URL,
        data=login_data,
        allow_redirects=True
    )

    print(
        f"Login response status: "
        f"{login_response.status_code}"
    )

    print(
        f"Final URL: "
        f"{login_response.url}"
    )

    # --------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------

    if "/my/" in login_response.url:

        print("Login successful ✅")

        _logged_in = True

        return True

    print("Login may have failed ❌")

    return False


def get_courses():
    """
    Get the courses available to the logged-in student.

    Moodle may display truncated course names on the
    My Courses page. Therefore, after getting each
    course ID, we open the actual course page and
    extract the complete course name from the <h1>.

    Returns:
        list of dictionaries:
        [
            {
                "id": "1695",
                "name": "Full course name"
            },
            ...
        ]
    """

    print("\nOpening My Courses page...")

    response = session.get(
        MY_COURSES_URL
    )

    print(
        f"My Courses status: "
        f"{response.status_code}"
    )

    if response.status_code != 200:
        print(
            "Could not open My Courses page ❌"
        )
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------
    # GET COURSE IDS AND DISPLAY NAMES
    # --------------------------------------------------

    courses = []

    for option in soup.find_all("option"):

        value = option.get("value")
        name = option.get_text(strip=True)

        if (
            value
            and value.isdigit()
            and name
            and name.lower() != "all courses"
        ):

            courses.append({
                "id": value,
                "name": name
            })

    # --------------------------------------------------
    # GET FULL COURSE NAME FROM COURSE PAGE
    # --------------------------------------------------

    for course in courses:

        course_url = (
            f"{BASE_URL}/course/view.php?id={course['id']}"
        )

        print(
            f"\nOpening course page to get full name:"
        )

        print(
            f"Course ID: {course['id']}"
        )

        course_response = session.get(
            course_url
        )

        if course_response.status_code != 200:

            print(
                "Could not open course page ❌"
            )

            print(
                f"Keeping displayed name: "
                f"{course['name']}"
            )

            continue

        course_soup = BeautifulSoup(
            course_response.text,
            "html.parser"
        )

        # Moodle course page contains the complete
        # course name inside the main <h1>.
        heading = course_soup.find("h1")

        if heading:

            full_name = heading.get_text(
                " ",
                strip=True
            )

            if full_name:

                course["name"] = full_name

                print(
                    f"Full course name found ✅: "
                    f"{full_name}"
                )

        else:

            print(
                "Course <h1> not found ❌"
            )

            print(
                f"Keeping displayed name: "
                f"{course['name']}"
            )

    return courses


def get_assignments(course_id):
    """
    Get all assignments for a specific Moodle course.

    Args:
        course_id: Moodle course ID.

    Returns:
        list of dictionaries containing assignment information.
    """

    course_url = (
        f"{BASE_URL}/course/view.php?id={course_id}"
    )

    print(
        f"\nOpening course: "
        f"{course_url}"
    )

    course_response = session.get(
        course_url
    )

    if course_response.status_code != 200:
        print(
            f"Course page request failed ❌ "
            f"Status: {course_response.status_code}"
        )
        return []

    course_soup = BeautifulSoup(
        course_response.text,
        "html.parser"
    )

    # --------------------------------------------------
    # FIND ASSIGNMENTS SECTION
    # --------------------------------------------------

    assignments_section_link = None

    for link in course_soup.find_all(
        "a",
        href=True
    ):

        text = link.get_text(
            " ",
            strip=True
        )

        if "assignments" in text.lower():
            assignments_section_link = link
            break

    if not assignments_section_link:
        print(
            "Assignments section not found ❌"
        )
        return []

    assignments_section_url = urljoin(
        course_url,
        assignments_section_link["href"]
    )

    print(
        "Assignments section found ✅"
    )

    print(
        f"Assignments URL: "
        f"{assignments_section_url}"
    )

    # --------------------------------------------------
    # OPEN ASSIGNMENTS SECTION
    # --------------------------------------------------

    section_response = session.get(
        assignments_section_url
    )

    if section_response.status_code != 200:
        print(
            f"Assignments section request failed ❌ "
            f"Status: {section_response.status_code}"
        )
        return []

    section_soup = BeautifulSoup(
        section_response.text,
        "html.parser"
    )

    # --------------------------------------------------
    # FIND ALL ASSIGNMENTS
    # --------------------------------------------------

    assignment_links = []

    for link in section_soup.find_all(
        "a",
        href=True
    ):

        href = link.get("href", "")

        text = link.get_text(
            " ",
            strip=True
        )

        if "/mod/assign/view.php" in href:

            assignment_url = urljoin(
                assignments_section_url,
                href
            )

            assignment_links.append({
                "name": text,
                "url": assignment_url
            })

    # --------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------

    unique_assignments = []

    seen_urls = set()

    for assignment in assignment_links:

        if assignment["url"] not in seen_urls:

            seen_urls.add(
                assignment["url"]
            )

            unique_assignments.append(
                assignment
            )

    print(
        f"\nAssignments found: "
        f"{len(unique_assignments)}"
    )

    # --------------------------------------------------
    # OPEN EACH ASSIGNMENT
    # --------------------------------------------------

    assignments = []

    for index, assignment in enumerate(
        unique_assignments,
        start=1
    ):

        print(
            f"\nReading assignment "
            f"{index}/{len(unique_assignments)}..."
        )

        print(
            f"Name: "
            f"{assignment['name']}"
        )

        print(
            f"URL: "
            f"{assignment['url']}"
        )

        assignment_response = session.get(
            assignment["url"]
        )

        if assignment_response.status_code != 200:

            print(
                "Could not open assignment ❌"
            )

            continue

        assignment_soup = BeautifulSoup(
            assignment_response.text,
            "html.parser"
        )

        assignment_data = {
            "name": assignment["name"],
            "url": assignment["url"],
            "due": None,
            "submission_status": None,
            "grading_status": None,
            "time_remaining": None,
            "last_modified": None,
            "file_submissions": []
        }

        # --------------------------------------------------
        # FIND SUBMISSION STATUS TABLE
        # --------------------------------------------------

        tables = assignment_soup.find_all(
            "table"
        )

        for table in tables:

            rows = table.find_all("tr")

            for row in rows:

                cells = row.find_all(
                    ["th", "td"]
                )

                if len(cells) < 2:
                    continue

                key = cells[0].get_text(
                    " ",
                    strip=True
                )

                value = cells[1].get_text(
                    " ",
                    strip=True
                )

                key_lower = key.lower()

                if key_lower == "submission status":

                    assignment_data[
                        "submission_status"
                    ] = value

                elif key_lower == "grading status":

                    assignment_data[
                        "grading_status"
                    ] = value

                elif key_lower == "time remaining":

                    assignment_data[
                        "time_remaining"
                    ] = value

                elif key_lower == "last modified":

                    assignment_data[
                        "last_modified"
                    ] = value

                elif key_lower == "file submissions":

                    file_links = cells[1].find_all(
                        "a",
                        href=True
                    )

                    for file_link in file_links:

                        file_name = file_link.get_text(
                            " ",
                            strip=True
                        )

                        file_url = urljoin(
                            assignment["url"],
                            file_link["href"]
                        )

                        assignment_data[
                            "file_submissions"
                        ].append({
                            "name": file_name,
                            "url": file_url
                        })

        # --------------------------------------------------
        # FIND DUE DATE
        # --------------------------------------------------

        page_text = assignment_soup.get_text(
            "\n",
            strip=True
        )

        lines = page_text.splitlines()

        for index_line, line in enumerate(lines):

            if line.strip().lower() == "due:":

                if index_line + 1 < len(lines):

                    assignment_data["due"] = (
                        lines[index_line + 1].strip()
                    )

                break

        assignments.append(
            assignment_data
        )

    return assignments


# ======================================================
# TESTING
# ======================================================

if __name__ == "__main__":

    print(
        "Testing real Moodle get_assignments()..."
    )

    if not login():
        raise SystemExit()

    courses = get_courses()

    print("\nCourses found:")

    for index, course in enumerate(
        courses,
        start=1
    ):

        print(
            f"{index}. {course['name']} "
            f"(ID: {course['id']})"
        )

    if not courses:

        print(
            "\nNo courses found ❌"
        )

        raise SystemExit()

    # --------------------------------------------------
    # TEST get_assignments()
    # --------------------------------------------------

    first_course = courses[0]

    print(
        "\n" + "=" * 70
    )

    print(
        "TESTING get_assignments()"
    )

    print(
        "=" * 70
    )

    assignments = get_assignments(
        first_course["id"]
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "ASSIGNMENTS RESULT"
    )

    print(
        "=" * 70
    )

    if not assignments:

        print(
            "No assignments found."
        )

    else:

        for index, assignment in enumerate(
            assignments,
            start=1
        ):

            print(
                f"\nAssignment {index}"
            )

            print(
                f"Name: "
                f"{assignment['name']}"
            )

            print(
                f"URL: "
                f"{assignment['url']}"
            )

            print(
                f"Due: "
                f"{assignment['due']}"
            )

            print(
                f"Submission status: "
                f"{assignment['submission_status']}"
            )

            print(
                f"Grading status: "
                f"{assignment['grading_status']}"
            )

            print(
                f"Time remaining: "
                f"{assignment['time_remaining']}"
            )

            print(
                f"Last modified: "
                f"{assignment['last_modified']}"
            )

            print(
                "Files:"
            )

            if assignment["file_submissions"]:

                for file_data in assignment[
                    "file_submissions"
                ]:

                    print(
                        f"  - {file_data['name']}"
                    )

            else:

                print(
                    "  No submitted files"
                )
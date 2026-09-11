import os
import re
import requests

from bs4 import BeautifulSoup
from dotenv import load_dotenv


# ============================================================
# Environment
# ============================================================

load_dotenv()

USERNAME = os.getenv("BAU_USERNAME")
PASSWORD = os.getenv("BAU_PASSWORD")


# ============================================================
# Moodle URLs
# ============================================================

BASE_URL = "https://elearning3.bau.edu.jo/huson"

LOGIN_URL = f"{BASE_URL}/login/index.php"
MY_COURSES_URL = f"{BASE_URL}/my/"
AJAX_URL = f"{BASE_URL}/lib/ajax/service.php"


# ============================================================
# Session
# ============================================================

session = requests.Session()

session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/139.0.0.0 Safari/537.36"
        )
    }
)


# ------------------------------------------------------------
# Track Moodle authentication state
# ------------------------------------------------------------

_logged_in = False


# ------------------------------------------------------------
# Course page cache
# ------------------------------------------------------------

_course_page_cache = {}


# ============================================================
# Moodle date/time pattern
# ============================================================

MOODLE_DATETIME_PATTERN = (
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"\d{1,2}\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+"
    r"\d{4},\s+"
    r"\d{1,2}:\d{2}\s+"
    r"(?:AM|PM)"
)


# ============================================================
# Cache
# ============================================================

def clear_course_page_cache():
    """
    Clear cached Moodle course pages.
    """

    global _course_page_cache

    _course_page_cache = {}


def get_cached_course_page(course_id):
    """
    Return a cached course page if it exists.
    """

    return _course_page_cache.get(course_id)


# ============================================================
# HTTP helpers
# ============================================================

def safe_request(method, url, **kwargs):
    """
    Make a safe HTTP request and handle
    connection-level errors.
    """

    try:

        response = session.request(
            method,
            url,
            timeout=30,
            **kwargs
        )

        return response

    except requests.RequestException as error:

        print(
            f"Request error: {error}"
        )

        return None


def is_session_expired(response):
    """
    Check whether Moodle redirected us
    to the login page or returned an
    authentication-related status.
    """

    if response is None:
        return True

    final_url = response.url.lower()

    if "/login/" in final_url:
        return True

    if response.status_code in (401, 403):
        return True

    return False


# ============================================================
# Login
# ============================================================

def login(force=False):
    """
    Login to BAU Moodle.

    If the current Session is already authenticated,
    do not perform another login.

    force=True can be used when the current Moodle
    session has expired.
    """

    global _logged_in

    # --------------------------------------------------------
    # Reuse the existing authenticated session
    # --------------------------------------------------------

    if _logged_in and not force:

        print(
            "Moodle session already authenticated ✅"
        )

        return True

    # --------------------------------------------------------
    # Check credentials
    # --------------------------------------------------------

    if not USERNAME or not PASSWORD:

        print(
            "BAU_USERNAME or BAU_PASSWORD "
            "is missing from .env"
        )

        _logged_in = False

        return False

    print(
        "Opening Moodle login page..."
    )

    response = safe_request(
        "GET",
        LOGIN_URL
    )

    if response is None:

        _logged_in = False

        return False

    print(
        f"Login page status: "
        f"{response.status_code}"
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    login_token_input = soup.find(
        "input",
        {"name": "logintoken"}
    )

    login_token = ""

    if login_token_input:

        login_token = login_token_input.get(
            "value",
            ""
        )

    if login_token:

        print(
            "Login token found ✅"
        )

    else:

        print(
            "Login token not found."
        )

    payload = {
        "username": USERNAME,
        "password": PASSWORD,
        "logintoken": login_token,
    }

    print(
        "Submitting login..."
    )

    login_response = safe_request(
        "POST",
        LOGIN_URL,
        data=payload,
        allow_redirects=True
    )

    if login_response is None:

        _logged_in = False

        return False

    print(
        f"Login response status: "
        f"{login_response.status_code}"
    )

    print(
        f"Final URL: "
        f"{login_response.url}"
    )

    # --------------------------------------------------------
    # Moodle keeps failed logins on /login/
    # --------------------------------------------------------

    if "/login/" in login_response.url.lower():

        print(
            "Login failed ❌"
        )

        _logged_in = False

        return False

    # --------------------------------------------------------
    # Login succeeded
    # --------------------------------------------------------

    _logged_in = True

    print(
        "Login successful ✅"
    )

    return True


# ============================================================
# Request with automatic authentication
# ============================================================

def request_with_relogin(method, url, **kwargs):
    """
    Make an authenticated Moodle request.

    Flow:

    1. If there is no authenticated session,
       login first.
    2. Make the request.
    3. If Moodle says the session expired,
       force one new login.
    4. Retry the request once.
    """

    global _logged_in

    # --------------------------------------------------------
    # Make sure we have an authenticated session
    # --------------------------------------------------------

    if not _logged_in:

        print(
            "No authenticated Moodle session. "
            "Logging in..."
        )

        if not login():

            return None

    # --------------------------------------------------------
    # First request
    # --------------------------------------------------------

    response = safe_request(
        method,
        url,
        **kwargs
    )

    if response is None:

        return None

    # --------------------------------------------------------
    # Check whether Moodle session expired
    # --------------------------------------------------------

    if is_session_expired(response):

        print(
            "Moodle session expired. "
            "Logging in again..."
        )

        _logged_in = False

        # ----------------------------------------------------
        # Force a fresh login
        # ----------------------------------------------------

        if not login(force=True):

            return response

        # ----------------------------------------------------
        # Retry request once
        # ----------------------------------------------------

        response = safe_request(
            method,
            url,
            **kwargs
        )

    return response


# ============================================================
# Sesskey
# ============================================================

def get_sesskey():
    """
    Extract Moodle sesskey from the logged-in page.
    """

    response = request_with_relogin(
        "GET",
        MY_COURSES_URL
    )

    if response is None:

        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # Try standard Moodle JavaScript config
    # --------------------------------------------------------

    sesskey_match = re.search(
        r'"sesskey"\s*:\s*"([^"]+)"',
        response.text
    )

    if sesskey_match:

        return sesskey_match.group(1)

    # --------------------------------------------------------
    # Try input field
    # --------------------------------------------------------

    sesskey_input = soup.find(
        "input",
        {"name": "sesskey"}
    )

    if sesskey_input:

        return sesskey_input.get(
            "value"
        )

    # --------------------------------------------------------
    # Try links containing sesskey
    # --------------------------------------------------------

    sesskey_match = re.search(
        r"sesskey=([A-Za-z0-9]+)",
        response.text
    )

    if sesskey_match:

        return sesskey_match.group(1)

    print(
        "Could not find Moodle sesskey."
    )

    return None


# ============================================================
# Courses
# ============================================================

def get_courses():
    """
    Dynamically retrieve all courses currently enrolled
    by the Moodle account.

    No course IDs or course names are hard-coded.
    """

    sesskey = get_sesskey()

    if not sesskey:

        print(
            "Could not retrieve sesskey."
        )

        return []

    payload = [
        {
            "index": 0,
            "methodname": (
                "core_course_get_enrolled_courses_by_"
                "timeline_classification"
            ),
            "args": {
                "classification": "all",
                "limit": 0,
                "offset": 0,
                "sort": "fullname",
            },
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    params = {
        "sesskey": sesskey,
    }

    response = request_with_relogin(
        "POST",
        AJAX_URL,
        params=params,
        json=payload,
        headers=headers
    )

    if response is None:

        return []

    if response.status_code != 200:

        print(
            f"Courses AJAX request failed: "
            f"{response.status_code}"
        )

        return []

    try:

        data = response.json()

    except ValueError:

        print(
            "Could not decode "
            "Moodle course JSON."
        )

        return []

    courses = []

    try:

        results = data[0]["data"]["courses"]

        for course in results:

            course_id = course.get(
                "id"
            )

            course_name = course.get(
                "fullname"
            )

            if course_id and course_name:

                courses.append(
                    {
                        "id": course_id,
                        "name": course_name,
                    }
                )

    except (
        KeyError,
        TypeError,
        IndexError
    ):

        print(
            "Unexpected Moodle course "
            "response format."
        )

        return []

    return courses


# ============================================================
# Course page
# ============================================================

def get_course_page(course_id):
    """
    Retrieve and cache a Moodle course page.
    """

    cached_page = get_cached_course_page(
        course_id
    )

    if cached_page is not None:

        return cached_page

    course_url = (
        f"{BASE_URL}/course/view.php?id={course_id}"
    )

    response = request_with_relogin(
        "GET",
        course_url
    )

    if response is None:

        return None

    if response.status_code != 200:

        print(
            f"Could not open course {course_id}: "
            f"{response.status_code}"
        )

        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    _course_page_cache[course_id] = soup

    return soup


# ============================================================
# Assignment due date
# ============================================================

def extract_assignment_due_date(soup):
    """
    Extract only the Moodle assignment due date/time.

    Example:

    Tuesday, 14 July 2026, 2:00 PM

    The assignment description is intentionally
    excluded from the returned date.
    """

    page_text = soup.get_text(
        " ",
        strip=True
    )

    # --------------------------------------------------------
    # Standard Moodle "Due:"
    # --------------------------------------------------------

    due_match = re.search(
        rf"\bDue\s*:\s*({MOODLE_DATETIME_PATTERN})",
        page_text,
        re.IGNORECASE
    )

    if due_match:

        return due_match.group(1).strip()

    # --------------------------------------------------------
    # "Due date:"
    # --------------------------------------------------------

    due_date_match = re.search(
        rf"\bDue\s+date\s*:\s*({MOODLE_DATETIME_PATTERN})",
        page_text,
        re.IGNORECASE
    )

    if due_date_match:

        return due_date_match.group(1).strip()

    return ""


# ============================================================
# Assignment description
# ============================================================

def extract_assignment_description(soup):
    """
    Extract the actual assignment description
    from the assignment detail page.

    Moodle normally stores the activity description
    inside one of these containers.
    """

    # --------------------------------------------------------
    # Preferred Moodle container
    # --------------------------------------------------------

    description_element = soup.select_one(
        ".activity-description"
    )

    if description_element:

        description = description_element.get_text(
            " ",
            strip=True
        )

        if description:

            return description

    # --------------------------------------------------------
    # Fallback description container
    # --------------------------------------------------------

    description_element = soup.select_one(
        ".description"
    )

    if description_element:

        description = description_element.get_text(
            " ",
            strip=True
        )

        if description:

            return description

    return ""


# ============================================================
# Assignment detail page
# ============================================================

def get_assignment_page(assignment_url):
    """
    Open the actual Moodle assignment page
    using the same logged-in Session.

    This is important because Moodle requires
    the authenticated session to expose the
    assignment details.
    """

    response = request_with_relogin(
        "GET",
        assignment_url
    )

    if response is None:

        return None

    if response.status_code != 200:

        print(
            f"Could not open assignment: "
            f"{response.status_code}"
        )

        return None

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


# ============================================================
# Assignments
# ============================================================

def get_assignments(course_id):
    """
    Extract all assignments from a Moodle course.

    Process:

    1. Open the course page.
    2. Find all assignment links.
    3. Open each assignment detail page.
    4. Extract the real Due Date.
    5. Extract the real Description.

    No assignment IDs or course IDs are hard-coded.
    """

    soup = get_course_page(
        course_id
    )

    if soup is None:

        return []

    assignments = []

    # --------------------------------------------------------
    # Find assignment links from course page
    # --------------------------------------------------------

    assignment_links = soup.select(
        'a[href*="/mod/assign/view.php"]'
    )

    seen_urls = set()

    for link in assignment_links:

        href = link.get("href")

        if not href:

            continue

        # ----------------------------------------------------
        # Moodle may return relative URLs.
        # Convert them to absolute URLs.
        # ----------------------------------------------------

        if href.startswith("/"):

            href = (
                "https://elearning3.bau.edu.jo"
                + href
            )

        elif href.startswith("mod/"):

            href = (
                f"{BASE_URL}/{href}"
            )

        # ----------------------------------------------------
        # Avoid duplicate assignment links
        # ----------------------------------------------------

        if href in seen_urls:

            continue

        seen_urls.add(href)

        # ----------------------------------------------------
        # Assignment name
        # ----------------------------------------------------

        name = link.get_text(
            " ",
            strip=True
        )

        if not name:

            continue

        print(
            f"  Reading assignment: "
            f"{name}"
        )

        # ----------------------------------------------------
        # Open actual assignment page
        # ----------------------------------------------------

        assignment_soup = get_assignment_page(
            href
        )

        if assignment_soup is None:

            print(
                "    Could not read assignment page."
            )

            assignments.append(
                {
                    "name": name,
                    "url": href,
                    "description": "",
                    "due_date": "",
                }
            )

            continue

        # ----------------------------------------------------
        # Extract real Due Date
        # ----------------------------------------------------

        due_date = extract_assignment_due_date(
            assignment_soup
        )

        # ----------------------------------------------------
        # Extract real Description
        # ----------------------------------------------------

        description = (
            extract_assignment_description(
                assignment_soup
            )
        )

        assignments.append(
            {
                "name": name,
                "url": href,
                "description": description,
                "due_date": due_date,
            }
        )

    return assignments


# ============================================================
# Quiz information
# ============================================================

def extract_quiz_info(soup):
    """
    Extract quiz metadata from a Moodle quiz page.

    Dates are extracted using the exact Moodle
    datetime format so descriptions cannot leak
    into date fields.
    """

    page_text = soup.get_text(
        " ",
        strip=True
    )

    opened_date = ""
    closed_date = ""
    attempts_allowed = ""
    time_limit = ""

    # --------------------------------------------------------
    # Opened
    # --------------------------------------------------------

    opened_match = re.search(
        rf"\bOpened\s*:\s*({MOODLE_DATETIME_PATTERN})",
        page_text,
        re.IGNORECASE
    )

    if opened_match:

        opened_date = (
            opened_match.group(1).strip()
        )

    # --------------------------------------------------------
    # Closed
    # --------------------------------------------------------

    closed_match = re.search(
        rf"\bClosed\s*:\s*({MOODLE_DATETIME_PATTERN})",
        page_text,
        re.IGNORECASE
    )

    if closed_match:

        closed_date = (
            closed_match.group(1).strip()
        )

    # --------------------------------------------------------
    # Attempts allowed
    # --------------------------------------------------------

    attempts_match = re.search(
        r"\bAttempts allowed\s*:\s*(.*?)(?=\s+Time limit\s*:)",
        page_text,
        re.IGNORECASE
    )

    if attempts_match:

        attempts_allowed = (
            attempts_match.group(1)
            .strip()
        )

    # --------------------------------------------------------
    # Time limit
    # --------------------------------------------------------

    time_limit_match = re.search(
        r"\bTime limit\s*:\s*(.*?)(?=\s+(?:Your attempts|Your final|Grade|Back to the course|$))",
        page_text,
        re.IGNORECASE
    )

    if time_limit_match:

        time_limit = (
            time_limit_match.group(1)
            .strip()
        )

    return {
        "opened_date": opened_date,
        "closed_date": closed_date,
        "attempts_allowed": attempts_allowed,
        "time_limit": time_limit,
    }


# ============================================================
# Quiz description
# ============================================================

def extract_quiz_description(soup):
    """
    Extract the quiz description.

    Prefer Moodle's activity-description
    container.
    """

    description_element = soup.select_one(
        ".activity-description"
    )

    if description_element:

        description = (
            description_element.get_text(
                " ",
                strip=True
            )
        )

        if description:

            return description

    description_element = soup.select_one(
        ".description"
    )

    if description_element:

        description = (
            description_element.get_text(
                " ",
                strip=True
            )
        )

        if description:

            return description

    return ""


# ============================================================
# Quizzes
# ============================================================

def get_quizzes(course_id):
    """
    Extract all quizzes from a Moodle course.
    """

    soup = get_course_page(
        course_id
    )

    if soup is None:

        return []

    quizzes = []

    quiz_links = soup.select(
        'a[href*="/mod/quiz/view.php"]'
    )

    seen_urls = set()

    for link in quiz_links:

        href = link.get("href")

        if not href:

            continue

        # ----------------------------------------------------
        # Convert relative URL to absolute URL
        # ----------------------------------------------------

        if href.startswith("/"):

            href = (
                "https://elearning3.bau.edu.jo"
                + href
            )

        elif href.startswith("mod/"):

            href = (
                f"{BASE_URL}/{href}"
            )

        # ----------------------------------------------------
        # Avoid duplicates
        # ----------------------------------------------------

        if href in seen_urls:

            continue

        seen_urls.add(href)

        name = link.get_text(
            " ",
            strip=True
        )

        if not name:

            continue

        # ----------------------------------------------------
        # Extract quiz ID
        # ----------------------------------------------------

        quiz_id_match = re.search(
            r"[?&]id=(\d+)",
            href
        )

        quiz_id = None

        if quiz_id_match:

            quiz_id = quiz_id_match.group(1)

        # ----------------------------------------------------
        # Open actual quiz page
        # ----------------------------------------------------

        quiz_soup = soup

        if quiz_id:

            quiz_url = (
                f"{BASE_URL}/mod/quiz/view.php"
                f"?id={quiz_id}"
            )

            response = request_with_relogin(
                "GET",
                quiz_url
            )

            if (
                response is not None
                and response.status_code == 200
            ):

                quiz_soup = BeautifulSoup(
                    response.text,
                    "html.parser"
                )

        # ----------------------------------------------------
        # Extract quiz information
        # ----------------------------------------------------

        quiz_info = extract_quiz_info(
            quiz_soup
        )

        description = (
            extract_quiz_description(
                quiz_soup
            )
        )

        quizzes.append(
            {
                "name": name,
                "url": href,
                "description": description,
                **quiz_info,
            }
        )

    return quizzes


# ============================================================
# Main test
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("BAU Moodle LMS Client Test")
    print("=" * 60)

    if not login():

        print(
            "\nLogin failed ❌"
        )

        raise SystemExit(1)

    print(
        "\nGetting enrolled courses..."
    )

    courses = get_courses()

    print(
        f"\nFound {len(courses)} course(s):"
    )

    for index, course in enumerate(
        courses,
        start=1
    ):

        print(
            f"{index}. "
            f"ID {course['id']} - "
            f"{course['name']}"
        )

    print(
        "\n" + "=" * 60
    )

    for course in courses:

        course_id = course["id"]
        course_name = course["name"]

        print(
            f"\nCOURSE: {course_name}"
        )

        print(
            f"COURSE ID: {course_id}"
        )

        print(
            "-" * 60
        )

        # ----------------------------------------------------
        # Assignments
        # ----------------------------------------------------

        print(
            "\nAssignments:"
        )

        assignments = get_assignments(
            course_id
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
                    f"\nAssignment {index}:"
                )

                print(
                    f"Name: "
                    f"{assignment['name']}"
                )

                print(
                    f"Due: "
                    f"{assignment['due_date']}"
                )

                print(
                    f"URL: "
                    f"{assignment['url']}"
                )

                print(
                    f"Description: "
                    f"{assignment['description']}"
                )

        # ----------------------------------------------------
        # Quizzes
        # ----------------------------------------------------

        print(
            "\nQuizzes:"
        )

        quizzes = get_quizzes(
            course_id
        )

        if not quizzes:

            print(
                "No quizzes found."
            )

        else:

            for index, quiz in enumerate(
                quizzes,
                start=1
            ):

                print(
                    f"\nQuiz {index}:"
                )

                print(
                    f"Name: "
                    f"{quiz['name']}"
                )

                print(
                    f"Opened: "
                    f"{quiz['opened_date']}"
                )

                print(
                    f"Closed: "
                    f"{quiz['closed_date']}"
                )

                print(
                    f"Attempts allowed: "
                    f"{quiz['attempts_allowed']}"
                )

                print(
                    f"Time limit: "
                    f"{quiz['time_limit']}"
                )

                print(
                    f"Description: "
                    f"{quiz['description']}"
                )

                print(
                    f"URL: "
                    f"{quiz['url']}"
                )

    print(
        "\n" + "=" * 60
    )

    print(
        "Test completed."
    )

    print(
        "=" * 60
    )
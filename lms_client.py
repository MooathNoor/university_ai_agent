import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

BAU_USERNAME = os.getenv("BAU_USERNAME")
BAU_PASSWORD = os.getenv("BAU_PASSWORD")


# =========================================================
# MOODLE CONFIGURATION
# =========================================================

BASE_URL = "https://elearning3.bau.edu.jo/huson"

LOGIN_URL = f"{BASE_URL}/login/index.php"
MY_COURSES_URL = f"{BASE_URL}/my/"

REQUEST_TIMEOUT = 15


# =========================================================
# SESSION
# =========================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
})

_logged_in = False


# =========================================================
# COURSE PAGE CACHE
# =========================================================

_course_page_cache = {}


def clear_course_page_cache():
    """
    Clear cached Moodle course pages.
    """

    global _course_page_cache

    _course_page_cache = {}

    print("[DEBUG] Course page cache cleared.")


def get_cached_course_page(course_id):
    """
    Get a Moodle course page.

    If the course page was already downloaded during the current
    process, return it from cache instead of making another request.
    """

    if course_id in _course_page_cache:

        print(
            f"[DEBUG] Using cached course page "
            f"for course ID {course_id}"
        )

        return _course_page_cache[course_id]

    url = f"{BASE_URL}/course/view.php?id={course_id}"

    print(
        f"[DEBUG] Downloading course page: {url}"
    )

    response = request_with_relogin(
        "GET",
        url
    )

    if response is None:
        return None

    if response.status_code != 200:

        print(
            f"[ERROR] Failed to download course page. "
            f"Status code: {response.status_code}"
        )

        return None

    _course_page_cache[course_id] = response.text

    print(
        f"[DEBUG] Course page cached "
        f"for course ID {course_id}"
    )

    return response.text


# =========================================================
# REQUEST HELPERS
# =========================================================

def safe_request(method, url, **kwargs):
    """
    Send an HTTP request safely.
    """

    try:

        response = session.request(
            method,
            url,
            timeout=REQUEST_TIMEOUT,
            **kwargs
        )

        return response

    except requests.RequestException as e:

        print(
            f"[ERROR] Request failed: {e}"
        )

        return None


def is_session_expired(response):
    """
    Check whether Moodle redirected us to the login page.
    """

    if response is None:
        return True

    final_url = response.url.lower()

    if "/login/index.php" in final_url:
        return True

    return False


def request_with_relogin(method, url, **kwargs):
    """
    Send request.

    If the Moodle session expired, login again
    and retry once.
    """

    global _logged_in

    response = safe_request(
        method,
        url,
        **kwargs
    )

    if response is None:
        return None

    if is_session_expired(response):

        print(
            "[DEBUG] Moodle session expired. "
            "Re-logging in..."
        )

        _logged_in = False

        if not login():

            print(
                "[ERROR] Re-login failed."
            )

            return response

        response = safe_request(
            method,
            url,
            **kwargs
        )

    return response


# =========================================================
# LOGIN
# =========================================================

def login():
    """
    Login to BAU Moodle.
    """

    global _logged_in

    if not BAU_USERNAME or not BAU_PASSWORD:

        print(
            "[ERROR] BAU_USERNAME or BAU_PASSWORD "
            "is missing from .env"
        )

        _logged_in = False

        return False

    print(
        "Opening Moodle login page..."
    )

    response = safe_request(
        "GET",
        LOGIN_URL,
        allow_redirects=True
    )

    if response is None:

        print(
            "[ERROR] Could not open Moodle login page."
        )

        return False

    print(
        f"Login page status: {response.status_code}"
    )

    print(
        f"Final URL: {response.url}"
    )

    if response.status_code != 200:

        print(
            f"[ERROR] Moodle login page returned "
            f"status code {response.status_code}."
        )

        return False

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    login_form = soup.find(
        "form",
        id="login"
    )

    if not login_form:

        print(
            "[ERROR] Moodle login form not found."
        )

        return False

    print(
        "Moodle login form found ✅"
    )

    # -----------------------------------------------------
    # Collect all hidden fields
    # -----------------------------------------------------

    login_data = {}

    hidden_inputs = login_form.find_all(
        "input",
        type="hidden"
    )

    for field in hidden_inputs:

        name = field.get("name")

        if not name:
            continue

        value = field.get(
            "value",
            ""
        )

        login_data[name] = value

    if "logintoken" not in login_data:

        print(
            "[ERROR] Login token not found."
        )

        return False

    print(
        "Login token found ✅"
    )

    # -----------------------------------------------------
    # Add credentials
    # -----------------------------------------------------

    login_data["username"] = BAU_USERNAME
    login_data["password"] = BAU_PASSWORD

    print(
        "Submitting login..."
    )

    response = safe_request(
        "POST",
        LOGIN_URL,
        data=login_data,
        allow_redirects=True
    )

    if response is None:

        print(
            "[ERROR] Login request failed."
        )

        _logged_in = False

        return False

    print(
        f"Login response status: "
        f"{response.status_code}"
    )

    print(
        f"Final URL: {response.url}"
    )

    # -----------------------------------------------------
    # Check whether login failed
    # -----------------------------------------------------

    final_url = response.url.lower()

    if "/login/index.php" in final_url:

        print(
            "[ERROR] Moodle login failed."
        )

        _logged_in = False

        return False

    # -----------------------------------------------------
    # Check authenticated page
    # -----------------------------------------------------

    final_html = response.text.lower()

    authenticated = (
        "/my/" in final_url
        or "usermenu" in final_html
        or "logout" in final_html
    )

    if not authenticated:

        print(
            "[ERROR] Moodle authentication "
            "could not be confirmed."
        )

        _logged_in = False

        return False

    _logged_in = True

    print(
        "Moodle login successful ✅"
    )

    return True


# =========================================================
# GET COURSES
# =========================================================

def get_courses():
    """
    Get the user's Moodle courses.
    """

    global _logged_in

    if not _logged_in:

        print(
            "[DEBUG] Not logged in. Logging in..."
        )

        if not login():

            return {
                "status": "Error",
                "message": "Moodle login failed."
            }

    print(
        "Opening Moodle My Courses page..."
    )

    response = request_with_relogin(
        "GET",
        MY_COURSES_URL
    )

    if response is None:

        return {
            "status": "Error",
            "message": "Could not connect to Moodle."
        }

    if response.status_code != 200:

        return {
            "status": "Error",
            "message": (
                f"Moodle returned status "
                f"{response.status_code}."
            )
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    courses = []

    course_links = soup.select(
        "a.aalink.coursename"
    )

    if not course_links:

        course_links = soup.select(
            "a.coursename"
        )

    for link in course_links:

        name = link.get_text(
            " ",
            strip=True
        )

        href = link.get(
            "href"
        )

        if not name or not href:
            continue

        course_id = None

        if "id=" in href:

            try:

                course_id = int(
                    href.split(
                        "id="
                    )[1].split(
                        "&"
                    )[0]
                )

            except ValueError:

                course_id = None

        courses.append(
            {
                "id": course_id,
                "name": name,
                "url": href
            }
        )

    print(
        f"[DEBUG] Courses found: "
        f"{len(courses)}"
    )

    return {
        "status": "Success",
        "courses": courses
    }


# =========================================================
# GET ASSIGNMENTS
# =========================================================

def get_assignments(course_id):
    """
    Get assignments for a specific course.
    """

    print(
        f"\n[DEBUG] Getting assignments "
        f"for course ID: {course_id}"
    )

    course_html = get_cached_course_page(
        course_id
    )

    if not course_html:

        return {
            "status": "Error",
            "message": "Could not load course page."
        }

    soup = BeautifulSoup(
        course_html,
        "html.parser"
    )

    assignment_links = soup.select(
        'a[href*="/mod/assign/view.php?id="]'
    )

    print(
        f"[DEBUG] Assignment links found: "
        f"{len(assignment_links)}"
    )

    assignments = []

    seen_urls = set()

    for link in assignment_links:

        href = link.get(
            "href"
        )

        if not href:
            continue

        if href in seen_urls:
            continue

        seen_urls.add(
            href
        )

        print(
            f"[DEBUG] Downloading assignment: "
            f"{href}"
        )

        response = request_with_relogin(
            "GET",
            href
        )

        if response is None:

            print(
                "[ERROR] Could not download "
                "assignment page."
            )

            continue

        if response.status_code != 200:

            print(
                f"[ERROR] Assignment page returned "
                f"status {response.status_code}"
            )

            continue

        assignment_soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # -------------------------------------------------
        # Assignment name
        # -------------------------------------------------

        name = ""

        heading = assignment_soup.find(
            "h1"
        )

        if heading:

            name = heading.get_text(
                " ",
                strip=True
            )

        if not name:

            name = link.get_text(
                " ",
                strip=True
            )

        # -------------------------------------------------
        # Description
        # -------------------------------------------------

        description = ""

        description_element = (
            assignment_soup.select_one(
                ".activity-description"
            )
        )

        if description_element:

            description = (
                description_element.get_text(
                    " ",
                    strip=True
                )
            )

        # -------------------------------------------------
        # Due date
        # -------------------------------------------------

        due_date = ""

        page_text = assignment_soup.get_text(
            " ",
            strip=True
        )

        due_marker = "Due date"

        if due_marker.lower() in page_text.lower():

            lower_text = page_text.lower()

            index = lower_text.find(
                due_marker.lower()
            )

            if index != -1:

                due_date = page_text[
                    index:index + 150
                ]

        assignments.append(
            {
                "name": name,
                "url": href,
                "description": description,
                "due_date": due_date
            }
        )

    print(
        f"[DEBUG] Assignments collected: "
        f"{len(assignments)}"
    )

    return {
        "status": "Success",
        "course_id": course_id,
        "assignments": assignments
    }


# =========================================================
# GET QUIZZES
# =========================================================

def get_quizzes(course_id):
    """
    Get quizzes for a specific course.
    """

    print(
        f"\n[DEBUG] Getting quizzes "
        f"for course ID: {course_id}"
    )

    course_html = get_cached_course_page(
        course_id
    )

    if not course_html:

        return {
            "status": "Error",
            "message": "Could not load course page."
        }

    soup = BeautifulSoup(
        course_html,
        "html.parser"
    )

    quiz_links = soup.select(
        'a[href*="/mod/quiz/view.php?id="]'
    )

    print(
        f"[DEBUG] Quiz links found: "
        f"{len(quiz_links)}"
    )

    quizzes = []

    seen_urls = set()

    for link in quiz_links:

        href = link.get(
            "href"
        )

        if not href:
            continue

        if href in seen_urls:
            continue

        seen_urls.add(
            href
        )

        print(
            f"[DEBUG] Downloading quiz: "
            f"{href}"
        )

        response = request_with_relogin(
            "GET",
            href
        )

        if response is None:

            print(
                "[ERROR] Could not download "
                "quiz page."
            )

            continue

        if response.status_code != 200:

            print(
                f"[ERROR] Quiz page returned "
                f"status {response.status_code}"
            )

            continue

        quiz_soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # -------------------------------------------------
        # Quiz name
        # -------------------------------------------------

        name = ""

        heading = quiz_soup.find(
            "h1"
        )

        if heading:

            name = heading.get_text(
                " ",
                strip=True
            )

        if not name:

            name = link.get_text(
                " ",
                strip=True
            )

        # -------------------------------------------------
        # Description
        # -------------------------------------------------

        description = ""

        description_element = (
            quiz_soup.select_one(
                ".activity-description"
            )
        )

        if description_element:

            description = (
                description_element.get_text(
                    " ",
                    strip=True
                )
            )

        # -------------------------------------------------
        # Close date
        # -------------------------------------------------

        close_date = ""

        page_text = quiz_soup.get_text(
            " ",
            strip=True
        )

        close_marker = "Close the quiz"

        if close_marker.lower() in page_text.lower():

            lower_text = page_text.lower()

            index = lower_text.find(
                close_marker.lower()
            )

            if index != -1:

                close_date = page_text[
                    index:index + 150
                ]

        quizzes.append(
            {
                "name": name,
                "url": href,
                "description": description,
                "close_date": close_date
            }
        )

    print(
        f"[DEBUG] Quizzes collected: "
        f"{len(quizzes)}"
    )

    return {
        "status": "Success",
        "course_id": course_id,
        "quizzes": quizzes
    }


# =========================================================
# MAIN TEST
# =========================================================

if __name__ == "__main__":

    print(
        "Testing BAU Moodle assignments..."
    )

    result = get_courses()

    print(
        result
    )

    if result.get("status") == "Success":

        courses = result.get(
            "courses",
            []
        )

        if courses:

            first_course = courses[0]

            course_id = first_course.get(
                "id"
            )

            print(
                f"\nTesting assignments "
                f"for: {first_course.get('name')}"
            )

            assignments_result = get_assignments(
                course_id
            )

            print(
                assignments_result
            )
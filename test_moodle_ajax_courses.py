import lms_client


# =========================================================
# MOODLE AJAX COURSE TEST
# =========================================================

def test_ajax_courses():

    print("=" * 60)
    print("TESTING MOODLE AJAX COURSES API")
    print("=" * 60)

    # -----------------------------------------------------
    # 1. Login
    # -----------------------------------------------------

    print("\n[1] Logging in to Moodle...")

    if not lms_client.login():

        print("[ERROR] Moodle login failed.")

        return

    print("[OK] Moodle login successful.")

    # -----------------------------------------------------
    # 2. Prepare AJAX endpoint
    # -----------------------------------------------------

    ajax_url = (
        f"{lms_client.BASE_URL}/lib/ajax/service.php"
    )

    print("\n[2] AJAX URL:")
    print(ajax_url)

    # -----------------------------------------------------
    # 3. Get session key
    # -----------------------------------------------------

    print("\n[3] Getting Moodle session key...")

    response = lms_client.request_with_relogin(
        "GET",
        lms_client.MY_COURSES_URL
    )

    if response is None:

        print(
            "[ERROR] Could not open Moodle My Courses page."
        )

        return

    if response.status_code != 200:

        print(
            "[ERROR] My Courses page returned status:",
            response.status_code
        )

        return

    # -----------------------------------------------------
    # Extract sesskey from page
    # -----------------------------------------------------

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    sesskey = None

    # Moodle usually exposes sesskey in JavaScript/config.
    # We search for the value without printing it.

    import re

    match = re.search(
        r'"sesskey"\s*:\s*"([^"]+)"',
        response.text
    )

    if match:

        sesskey = match.group(1)

    if not sesskey:

        # Fallback: hidden input

        sesskey_input = soup.find(
            "input",
            {
                "name": "sesskey"
            }
        )

        if sesskey_input:

            sesskey = sesskey_input.get(
                "value"
            )

    if not sesskey:

        print(
            "[ERROR] Could not find Moodle sesskey."
        )

        return

    print("[OK] Moodle sesskey found.")

    # -----------------------------------------------------
    # 4. Prepare AJAX request
    # -----------------------------------------------------

    print("\n[4] Calling Moodle course AJAX service...")

    payload = [
        {
            "index": 0,
            "methodname": (
                "core_course_get_enrolled_courses_by_timeline_classification"
            ),
            "args": {
                "classification": "all",
                "limit": 0,
                "offset": 0,
                "sort": "fullname"
            }
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    }

    # -----------------------------------------------------
    # 5. Send AJAX request
    # -----------------------------------------------------

    ajax_response = lms_client.request_with_relogin(
        "POST",
        ajax_url,
        params={
            "sesskey": sesskey
        },
        json=payload,
        headers=headers
    )

    if ajax_response is None:

        print(
            "[ERROR] AJAX request failed."
        )

        return

    print(
        "[DEBUG] AJAX status:",
        ajax_response.status_code
    )

    print(
        "[DEBUG] AJAX final URL:",
        ajax_response.url
    )

    if ajax_response.status_code != 200:

        print(
            "[ERROR] Moodle AJAX service returned:",
            ajax_response.status_code
        )

        print(
            ajax_response.text[:1000]
        )

        return

    # -----------------------------------------------------
    # 6. Parse response
    # -----------------------------------------------------

    try:

        data = ajax_response.json()

    except ValueError:

        print(
            "[ERROR] Moodle returned invalid JSON."
        )

        print(
            ajax_response.text[:2000]
        )

        return

    # -----------------------------------------------------
    # 7. Print safe response structure
    # -----------------------------------------------------

    print("\n[5] AJAX response received.")

    print(
        "Response type:",
        type(data).__name__
    )

    if not isinstance(data, list):

        print(
            "[ERROR] Unexpected Moodle response format."
        )

        print(data)

        return

    print(
        "Number of AJAX results:",
        len(data)
    )

    if not data:

        print(
            "[WARNING] Moodle returned an empty response."
        )

        return

    first_result = data[0]

    print(
        "\nAJAX result keys:",
        list(first_result.keys())
    )

    # -----------------------------------------------------
    # 8. Check for Moodle exception
    # -----------------------------------------------------

    if first_result.get("error"):

        print(
            "\n[ERROR] Moodle AJAX returned an error."
        )

        print(
            "Error:",
            first_result.get("exception")
        )

        print(
            "Message:",
            first_result.get("message")
        )

        return

    # -----------------------------------------------------
    # 9. Extract courses
    # -----------------------------------------------------

    courses = first_result.get(
        "data",
        {}
    )

    print(
        "\nData type:",
        type(courses).__name__
    )

    if isinstance(courses, dict):

        print(
            "Data keys:",
            list(courses.keys())
        )

        course_list = courses.get(
            "courses",
            []
        )

    else:

        course_list = []

    # -----------------------------------------------------
    # 10. Print courses
    # -----------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        f"COURSES FOUND: {len(course_list)}"
    )

    print(
        "=" * 60
    )

    for index, course in enumerate(
        course_list,
        start=1
    ):

        print(
            f"\nCourse {index}:"
        )

        print(
            "ID:",
            course.get("id")
        )

        print(
            "Full name:",
            course.get("fullname")
        )

        print(
            "Short name:",
            course.get("shortname")
        )

        print(
            "Visible:",
            course.get("visible")
        )

        print(
            "End date:",
            course.get("enddate")
        )

    print(
        "\n" + "=" * 60
    )

    if course_list:

        print(
            "[SUCCESS] Moodle AJAX course retrieval works! ✅"
        )

    else:

        print(
            "[WARNING] AJAX worked, but no courses were returned."
        )


# =========================================================
# RUN TEST
# =========================================================

if __name__ == "__main__":

    test_ajax_courses()
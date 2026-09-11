import re
from bs4 import BeautifulSoup

from lms_client import (
    login,
    get_courses,
    request_with_relogin,
)


def inspect_assignment_page(url):
    print("\n" + "=" * 70)
    print("INSPECTING ASSIGNMENT PAGE")
    print("=" * 70)

    print(f"\n[DEBUG] Opening assignment:")
    print(url)

    response = request_with_relogin("GET", url)

    print(f"[DEBUG] Status code: {response.status_code}")
    print(f"[DEBUG] Final URL: {response.url}")

    if response.status_code != 200:
        print("[ERROR] Could not open assignment page.")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    print("\n[1] Searching for common due-date text...")

    patterns = [
        "Due date",
        "Due",
        "Submission due",
        "Submission due date",
        "Cut-off date",
        "Cut-off",
        "Deadline",
    ]

    found = False

    for pattern in patterns:
        matches = soup.find_all(
            string=re.compile(re.escape(pattern), re.IGNORECASE)
        )

        if matches:
            found = True

            print(f"\n[FOUND] Text matching: {pattern}")

            for match in matches[:5]:
                parent = match.parent

                print("\n--- HTML CONTEXT ---")
                print(parent.prettify()[:3000])
                print("--- END CONTEXT ---")

    if not found:
        print("[WARNING] No common due-date text found.")

    print("\n[2] Searching for Moodle date/time elements...")

    date_elements = soup.select(
        ".submissionstatussubmitted .datesubmitted,"
        ".submissionstatussubmitted,"
        ".submissionstatustable,"
        ".activity-dates,"
        ".activity-information,"
        ".description-inner"
    )

    if date_elements:
        print(f"[FOUND] Possible date containers: {len(date_elements)}")

        for element in date_elements[:10]:
            text = element.get_text(" ", strip=True)

            if text:
                print("\n--- DATE CONTAINER ---")
                print(text[:2000])
                print("--- END CONTAINER ---")
    else:
        print("[WARNING] No common Moodle date containers found.")

    print("\n[3] Searching page text for date-like values...")

    page_text = soup.get_text(" ", strip=True)

    date_patterns = [
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{4}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}:\d{2}\b",
    ]

    all_matches = []

    for pattern in date_patterns:
        matches = re.findall(pattern, page_text)

        for match in matches:
            if match not in all_matches:
                all_matches.append(match)

    if all_matches:
        print("[FOUND] Date/time values:")

        for value in all_matches:
            print(f"  - {value}")
    else:
        print("[WARNING] No obvious date/time values found.")

    print("\n" + "=" * 70)
    print("INSPECTION COMPLETE")
    print("=" * 70)


def main():
    print("=" * 70)
    print("TESTING MOODLE ASSIGNMENT DUE DATE")
    print("=" * 70)

    print("\n[1] Logging in to Moodle...")

    if not login():
        print("[ERROR] Moodle login failed.")
        return

    print("[OK] Moodle login successful.")

    print("\n[2] Getting courses...")

    courses_result = get_courses()

    if courses_result.get("status") != "Success":
        print("[ERROR] Could not retrieve courses.")
        print(courses_result)
        return

    courses = courses_result.get("courses", [])

    if not courses:
        print("[ERROR] No courses found.")
        return

    print(f"[OK] Courses found: {len(courses)}")

    first_course = courses[0]

    course_id = first_course["id"]
    course_name = first_course["name"]

    print(f"\n[3] Using first course:")
    print(f"Course ID: {course_id}")
    print(f"Course: {course_name}")

    print("\n[4] Opening course page...")

    course_url = first_course["url"]

    response = request_with_relogin("GET", course_url)

    if response.status_code != 200:
        print("[ERROR] Could not open course page.")
        return

    print("[OK] Course page opened.")

    soup = BeautifulSoup(response.text, "html.parser")

    assignment_links = []

    for link in soup.select("a[href*='/mod/assign/view.php?id=']"):
        href = link.get("href")

        if href and href not in assignment_links:
            assignment_links.append(href)

    print(f"\n[5] Assignment links found: {len(assignment_links)}")

    if not assignment_links:
        print("[ERROR] No assignment links found.")
        return

    print("\nAssignments:")

    for index, url in enumerate(assignment_links, start=1):
        print(f"{index}. {url}")

    print("\n[6] Inspecting first assignment...")

    inspect_assignment_page(assignment_links[0])


if __name__ == "__main__":
    main()
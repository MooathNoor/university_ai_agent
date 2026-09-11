import lms_client


def extract_quiz_dates(soup):
    """
    Extract Opened and Closed dates from a Moodle quiz page.
    """

    opened = ""
    closed = ""

    # Search for Moodle activity dates container
    containers = soup.select(
        ".activity-dates, "
        ".activity-information, "
        ".quizinfo, "
        ".quizattemptcounts"
    )

    for container in containers:
        text = container.get_text(" ", strip=True)

        if not opened:
            opened_match = lms_client.re.search(
                r"Opened\s*:\s*(.*?)(?=\s+Closed\s*:|\s*$)",
                text,
                lms_client.re.IGNORECASE
            )

            if opened_match:
                opened = opened_match.group(1).strip()

        if not closed:
            closed_match = lms_client.re.search(
                r"Closed\s*:\s*(.*?)(?=\s+(?:Attempts allowed|Time limit|Your attempts|$))",
                text,
                lms_client.re.IGNORECASE
            )

            if closed_match:
                closed = closed_match.group(1).strip()

    # Fallback: search the whole page text
    if not opened or not closed:
        page_text = soup.get_text(" ", strip=True)

        if not opened:
            opened_match = lms_client.re.search(
                r"Opened\s*:\s*(.*?)(?=\s+Closed\s*:)",
                page_text,
                lms_client.re.IGNORECASE
            )

            if opened_match:
                opened = opened_match.group(1).strip()

        if not closed:
            closed_match = lms_client.re.search(
                r"Closed\s*:\s*(.*?)(?=\s+(?:Attempts allowed|Time limit|Your attempts|Back to the course|$))",
                page_text,
                lms_client.re.IGNORECASE
            )

            if closed_match:
                closed = closed_match.group(1).strip()

    return opened, closed


def test_quizzes_for_course(course):
    course_id = course["id"]
    course_name = course["name"]

    print("\n" + "=" * 80)
    print(f"COURSE: {course_name}")
    print(f"COURSE ID: {course_id}")
    print("=" * 80)

    course_url = f"{lms_client.BASE_URL}/course/view.php?id={course_id}"

    print(f"\nDownloading course page:")
    print(course_url)

    response = lms_client.request_with_relogin(
        "GET",
        course_url
    )

    if response is None:
        print("Could not download course page.")
        return

    print(f"Course page status: {response.status_code}")

    soup = lms_client.BeautifulSoup(
        response.text,
        "html.parser"
    )

    quiz_links = []

    # Normal Moodle quiz links
    for link in soup.select("a[href*='/mod/quiz/view.php?id=']"):
        href = link.get("href")

        if not href:
            continue

        if href not in quiz_links:
            quiz_links.append(href)

    print(f"\nQuiz links found: {len(quiz_links)}")

    if not quiz_links:
        print("No quizzes found in this course.")
        return

    for index, quiz_url in enumerate(quiz_links, start=1):

        print("\n" + "-" * 80)
        print(f"QUIZ #{index}")
        print(f"URL: {quiz_url}")
        print("-" * 80)

        quiz_response = lms_client.request_with_relogin(
            "GET",
            quiz_url
        )

        if quiz_response is None:
            print("Could not download quiz page.")
            continue

        print(f"Quiz page status: {quiz_response.status_code}")

        quiz_soup = lms_client.BeautifulSoup(
            quiz_response.text,
            "html.parser"
        )

        # Quiz title
        title = ""

        h1 = quiz_soup.find("h1")

        if h1:
            title = h1.get_text(" ", strip=True)

        if not title:
            page_title = quiz_soup.find("title")

            if page_title:
                title = page_title.get_text(" ", strip=True)

        # Dates
        opened, closed = extract_quiz_dates(quiz_soup)

        # Description / topic
        description = ""

        description_container = quiz_soup.select_one(
            ".activity-description"
        )

        if description_container:
            description = description_container.get_text(
                " ",
                strip=True
            )

        if not description:
            description_container = quiz_soup.select_one(
                ".quizinfo"
            )

            if description_container:
                description = description_container.get_text(
                    " ",
                    strip=True
                )

        print(f"Title: {title}")
        print(f"Opened: {opened}")
        print(f"Closed: {closed}")

        if description:
            print(f"Description: {description}")


if __name__ == "__main__":

    print("Testing BAU Moodle quiz data...")

    courses_result = lms_client.get_courses()

    if courses_result.get("status") != "Success":
        print("\nFailed to get courses.")
        print(courses_result)
        raise SystemExit

    courses = courses_result.get("courses", [])

    print(f"\nTotal courses: {len(courses)}")

    for course in courses:
        test_quizzes_for_course(course)

    print("\n" + "=" * 80)
    print("Quiz testing completed.")
    print("=" * 80)
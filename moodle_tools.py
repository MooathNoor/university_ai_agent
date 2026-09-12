import lms_client


def get_all_courses():
    """
    Return all courses currently enrolled by the user.
    """
    return lms_client.get_courses()


def get_course_name(course):
    """
    Safely extract the course name.
    """
    return (
        course.get("fullname")
        or course.get("name")
        or course.get("course_name")
        or "Unknown Course"
    )


def get_course_id(course):
    """
    Safely extract the course ID.
    """
    return course.get("id") or course.get("course_id")


def get_all_assignments():
    """
    Return all assignments from all enrolled courses.
    """

    courses = get_all_courses()
    result = []

    for course in courses:
        course_id = get_course_id(course)
        course_name = get_course_name(course)

        if course_id is None:
            continue

        assignments = lms_client.get_assignments(course_id)

        for assignment in assignments:
            result.append({
                "course_id": course_id,
                "course_name": course_name,
                "name": assignment.get("name", ""),
                "due_date": assignment.get("due_date", ""),
                "description": assignment.get("description", ""),
                "url": assignment.get("url", "")
            })

    return result


def get_all_quizzes():
    """
    Return all quizzes from all enrolled courses.
    """

    courses = get_all_courses()
    result = []

    for course in courses:
        course_id = get_course_id(course)
        course_name = get_course_name(course)

        if course_id is None:
            continue

        quizzes = lms_client.get_quizzes(course_id)

        for quiz in quizzes:
            result.append({
                "course_id": course_id,
                "course_name": course_name,
                "name": quiz.get("name", ""),
                "opened_date": quiz.get("opened_date", ""),
                "closed_date": quiz.get("closed_date", ""),
                "attempts_allowed": quiz.get("attempts_allowed", ""),
                "time_limit": quiz.get("time_limit", ""),
                "description": quiz.get("description", ""),
                "url": quiz.get("url", "")
            })

    return result


def get_course_overview():
    """
    Return a simple overview of all enrolled courses.
    """

    courses = get_all_courses()
    result = []

    for course in courses:
        result.append({
            "id": get_course_id(course),
            "name": get_course_name(course)
        })

    return result


if __name__ == "__main__":

    print("\n" + "=" * 70)
    print("COURSE OVERVIEW")
    print("=" * 70)

    courses = get_course_overview()

    for course in courses:
        print(f"ID: {course['id']}")
        print(f"Name: {course['name']}")
        print("-" * 70)

    print("\n" + "=" * 70)
    print("ALL ASSIGNMENTS")
    print("=" * 70)

    assignments = get_all_assignments()

    for index, assignment in enumerate(assignments, start=1):

        print(f"\nAssignment {index}")
        print(f"Course: {assignment['course_name']}")
        print(f"Name: {assignment['name']}")
        print(f"Due: {assignment['due_date']}")
        print(f"Description: {assignment['description']}")
        print(f"URL: {assignment['url']}")
        print("-" * 70)

    print("\n" + "=" * 70)
    print("ALL QUIZZES")
    print("=" * 70)

    quizzes = get_all_quizzes()

    for index, quiz in enumerate(quizzes, start=1):

        print(f"\nQuiz {index}")
        print(f"Course: {quiz['course_name']}")
        print(f"Name: {quiz['name']}")
        print(f"Opened: {quiz['opened_date']}")
        print(f"Closed: {quiz['closed_date']}")
        print(f"Attempts Allowed: {quiz['attempts_allowed']}")
        print(f"Time Limit: {quiz['time_limit']}")
        print(f"Description: {quiz['description']}")
        print(f"URL: {quiz['url']}")
        print("-" * 70)
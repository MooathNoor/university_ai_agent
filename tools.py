def get_attendance(course_name):
    """
    Return attendance information for a course.
    """

    attendance_data = {
        "Artificial Intelligence": {
            "status": "Present",
            "attendance_percentage": 92
        },
        "Database": {
            "status": "Absent",
            "attendance_percentage": 85
        },
        "Python": {
            "status": "Present",
            "attendance_percentage": 95
        }
    }

    if course_name not in attendance_data:
        return {
            "status": "Unknown",
            "message": "Course not found."
        }

    return attendance_data[course_name]


def get_course_schedule(course_name):
    """
    Return the schedule for a course.
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


def get_course_info(course_name):
    """
    Return general information about a course.
    """

    courses = {
        "Artificial Intelligence": {
            "name": "Artificial Intelligence",
            "code": "AI101",
            "credit_hours": 3,
            "instructor": "Dr. Ahmad",
            "section": 1,
            "room": "Lab 2"
        },
        "Database": {
            "name": "Database",
            "code": "DB201",
            "credit_hours": 3,
            "instructor": "Dr. Mohammad",
            "section": 2,
            "room": "Room 15"
        },
        "Python": {
            "name": "Python",
            "code": "PY101",
            "credit_hours": 3,
            "instructor": "Dr. Sara",
            "section": 1,
            "room": "Lab 1"
        }
    }

    if course_name not in courses:
        return {
            "status": "Unknown",
            "message": "Course not found."
        }

    return courses[course_name]


def get_my_courses():
    """
    Return the courses currently registered by the student.
    """

    courses = [
        {
            "name": "Artificial Intelligence",
            "code": "AI101",
            "credit_hours": 3,
            "instructor": "Dr. Ahmad",
            "section": 1
        },
        {
            "name": "Database",
            "code": "DB201",
            "credit_hours": 3,
            "instructor": "Dr. Mohammad",
            "section": 2
        },
        {
            "name": "Python",
            "code": "PY101",
            "credit_hours": 3,
            "instructor": "Dr. Sara",
            "section": 1
        }
    ]

    return courses


def get_assignments():
    """
    Return the current assignments for the student's courses.
    """

    assignments = [
        {
            "course": "Artificial Intelligence",
            "title": "AI Assignment 1",
            "due_date": "2026-09-10",
            "status": "Pending"
        },
        {
            "course": "Database",
            "title": "SQL Assignment",
            "due_date": "2026-09-12",
            "status": "Pending"
        },
        {
            "course": "Python",
            "title": "Python Functions Assignment",
            "due_date": "2026-09-14",
            "status": "Pending"
        }
    ]

    return assignments


def get_grades():
    """
    Return the student's current grades.
    """

    grades = [
        {
            "course": "Artificial Intelligence",
            "code": "AI101",
            "grade": 85,
            "status": "Passed"
        },
        {
            "course": "Database",
            "code": "DB201",
            "grade": 78,
            "status": "Passed"
        },
        {
            "course": "Python",
            "code": "PY101",
            "grade": 92,
            "status": "Passed"
        }
    ]

    return grades


def get_announcements():
    """
    Return the latest university announcements.
    """

    announcements = [
        {
            "course": "Artificial Intelligence",
            "title": "AI Lecture Postponed",
            "date": "2026-09-08",
            "message": "Today's AI lecture has been postponed to tomorrow."
        },
        {
            "course": "Database",
            "title": "SQL Assignment Reminder",
            "date": "2026-09-08",
            "message": "Remember to submit the SQL assignment before the due date."
        },
        {
            "course": "Python",
            "title": "Python Quiz",
            "date": "2026-09-08",
            "message": "A Python quiz will be available on the LMS tomorrow."
        }
    ]

    return announcements


def get_quizzes():
    """
    Return the current quizzes for the student's courses.
    """

    quizzes = [
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

    return quizzes


def get_upcoming_deadlines():
    """
    Return assignments and quizzes ordered by their due dates.
    """

    assignments = get_assignments()
    quizzes = get_quizzes()

    deadlines = []

    for assignment in assignments:
        deadlines.append({
            "course": assignment["course"],
            "title": assignment["title"],
            "type": "Assignment",
            "due_date": assignment["due_date"],
            "status": assignment["status"]
        })

    for quiz in quizzes:
        deadlines.append({
            "course": quiz["course"],
            "title": quiz["title"],
            "type": "Quiz",
            "due_date": quiz["due_date"],
            "status": quiz["status"]
        })

    deadlines.sort(key=lambda item: item["due_date"])

    return deadlines
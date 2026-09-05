def get_attendance(course_name):
    attendance_data = {
        "Artificial Intelligence": {
            "status": "Recorded",
            "message": "Your attendance has been recorded."
        },
        "Database": {
            "status": "Closed",
            "message": "Attendance is currently closed."
        },
        "Python": {
            "status": "Open",
            "message": "Attendance is currently open."
        }
    }

    return attendance_data.get(
        course_name,
        {
            "status": "Unknown",
            "message": "Course not found."
        }
    )


def get_course_schedule(course_name):
    schedule_data = {
        "Artificial Intelligence": {
            "day": "Sunday",
            "time": "10:00 AM",
            "room": "Lab 3"
        },
        "Database": {
            "day": "Monday",
            "time": "12:00 PM",
            "room": "Room 201"
        },
        "Python": {
            "day": "Tuesday",
            "time": "9:00 AM",
            "room": "Lab 1"
        }
    }

    return schedule_data.get(
        course_name,
        {
            "status": "Unknown",
            "message": "Course not found."
        }
    )


def get_course_info(course_name):
    course_data = {
        "Artificial Intelligence": {
            "credit_hours": 3,
            "instructor": "Dr. Ahmad",
            "section": 1,
            "room": "Lab 3"
        },
        "Database": {
            "credit_hours": 3,
            "instructor": "Dr. Mohammad",
            "section": 2,
            "room": "Room 201"
        },
        "Python": {
            "credit_hours": 3,
            "instructor": "Dr. Sara",
            "section": 1,
            "room": "Lab 1"
        }
    }

    return course_data.get(
        course_name,
        {
            "status": "Unknown",
            "message": "Course not found."
        }
    )
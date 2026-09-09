import ollama
import json
import time


from tools import (
    get_attendance,
    get_course_schedule,
    get_course_info,
    get_my_courses,
    get_assignments,
    get_grades,
    get_announcements,
    get_quizzes,
    get_upcoming_deadlines
)


# ============================================================
# PERFORMANCE SETTINGS
# ============================================================

MODEL_NAME = "llama3.2:3b"

# How long the course list stays in memory.
# This prevents repeated Moodle course discovery.
COURSE_CACHE_SECONDS = 60

_course_cache = None
_course_cache_time = 0


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a University AI Agent.

You help students with university information.

You have access to tools that can provide university data.

Use a tool only when the user's question requires specific university data.

When the user asks about attendance, use the attendance tool.

Important attendance rule:
- If taken_sessions is 0, do NOT say the student has perfect attendance.
- If taken_sessions is 0, do NOT say the student missed all sessions.
- Instead, say that there are currently no recorded attendance sessions.
- Do not infer attendance status when there are no recorded sessions.
- Use the exact attendance percentage returned by the tool.

When the user asks about a course schedule, use the schedule tool.
Schedule means days, times, lecture timing, or class timetable.

When the user asks about course information such as:
- credit hours
- instructor
- section
- room
- course sections
- course activities
- course materials
- available activities
- available content
use the course info tool.

When the user asks about their courses, current courses,
registered courses, or what courses they have,
use the my courses tool.

When the user asks about assignments, homework, tasks,
or assignment due dates, use the assignments tool.

Important assignments rule:
- If the user asks generally about assignments without naming a course,
  get assignments for all courses.
- If the user names a specific course, get assignments for that course.

When the user asks about grades, marks, scores,
or their current grades, use the grades tool.

When the user asks about announcements, university announcements,
course announcements, or latest announcements,
use the announcements tool.

When the user asks about quizzes, tests, or quiz dates,
use the quizzes tool.

Important quizzes rule:
- If the user asks generally about quizzes without naming a course,
  get quizzes for all courses.
- If the user names a specific course, get quizzes for that course.

When the user asks about upcoming deadlines,
what they need to submit soon, upcoming assignments and quizzes,
or what is due soon,
use the upcoming deadlines tool.

If the user is greeting you, asking what you can do,
or asking a general question that does not require university data,
do not use any tool.

If the user only provides a course name without saying
what information they want, do not guess.
Ask what they would like to know about that course.

Never invent university information.

Keep your final answers short and direct.
"""


# ============================================================
# OLLAMA TOOLS
# ============================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_attendance",
            "description": "Get the attendance status for a university course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "The name of the course."
                    }
                },
                "required": ["course_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_schedule",
            "description": (
                "Get the timetable/schedule of a university course. "
                "Use ONLY for class days, lecture times, timetable, "
                "or when the course is held."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "The name of the course."
                    }
                },
                "required": ["course_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_info",
            "description": (
                "Get detailed information about a university course, "
                "including credit hours, instructor, section, room, "
                "course sections, activities, course materials, "
                "available content, assignments, quizzes, forums, "
                "files, URLs, and other Moodle activities. "
                "Use this tool when the user asks what is available "
                "inside a course."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "The name of the course."
                    }
                },
                "required": ["course_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_courses",
            "description": "Get the list of the student's current university courses.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_assignments",
            "description": (
                "Get assignments for the student's university courses. "
                "If a specific course is mentioned, provide course_name. "
                "If no course is mentioned, get assignments for all courses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": (
                            "Optional course name. "
                            "Use it only when the user asks about "
                            "assignments for a specific course."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_grades",
            "description": "Get the student's current grades for their courses.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_announcements",
            "description": "Get the latest university and course announcements.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_quizzes",
            "description": (
                "Get quizzes for the student's university courses. "
                "If a specific course is mentioned, provide course_name. "
                "If no course is mentioned, get quizzes for all courses."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": (
                            "Optional course name. "
                            "Use it only when the user asks about "
                            "quizzes for a specific course."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_deadlines",
            "description": (
                "Get upcoming assignments and quizzes ordered by "
                "their due dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


# ============================================================
# AVAILABLE TOOLS
# ============================================================

available_tools = {
    "get_attendance": get_attendance,
    "get_course_schedule": get_course_schedule,
    "get_course_info": get_course_info,
    "get_my_courses": get_my_courses,
    "get_assignments": get_assignments,
    "get_grades": get_grades,
    "get_announcements": get_announcements,
    "get_quizzes": get_quizzes,
    "get_upcoming_deadlines": get_upcoming_deadlines
}


# ============================================================
# COURSE CACHE
# ============================================================

def get_cached_courses():
    """
    Return Moodle courses from a short-lived in-memory cache.

    This prevents repeated course discovery during the same
    agent session.
    """

    global _course_cache
    global _course_cache_time

    current_time = time.time()

    if (
        _course_cache is not None
        and current_time - _course_cache_time
        < COURSE_CACHE_SECONDS
    ):

        print("[DEBUG] Using cached Moodle courses.")

        return _course_cache

    print("[DEBUG] Loading courses from Moodle...")

    try:

        courses = get_my_courses()

    except Exception as error:

        print(
            f"[DEBUG] Could not load Moodle courses: "
            f"{error}"
        )

        return []

    _course_cache = courses
    _course_cache_time = current_time

    return courses


# ============================================================
# ROUTER
# ============================================================

def route_question(user_input):
    """
    Decide whether the user's message requires university data.
    """

    text = user_input.lower().strip()

    tool_keywords = [

        # ----------------------------------------------------
        # English
        # ----------------------------------------------------

        "attendance",
        "schedule",
        "timetable",
        "class time",
        "lecture time",
        "what time",

        "credit hours",
        "credit hour",

        "instructor",
        "teacher",

        "section",
        "sections",

        "room",

        "course information",
        "course info",

        "activities",
        "activity",
        "materials",
        "material",
        "course content",
        "available content",

        "my courses",
        "current courses",
        "registered courses",
        "my subjects",
        "what courses",

        "assignments",
        "assignment",
        "homework",
        "tasks",
        "due dates",

        "grades",
        "grade",
        "marks",
        "mark",
        "scores",
        "score",

        "announcements",
        "announcement",
        "latest announcements",

        "quizzes",
        "quiz",
        "tests",
        "test",
        "quiz dates",

        "deadlines",
        "deadline",
        "upcoming deadlines",
        "due soon",
        "submit soon",
        "what do i need to submit",

        # ----------------------------------------------------
        # Arabic
        # ----------------------------------------------------

        "حضور",
        "غياب",
        "الحضور",
        "الغياب",

        "جدول",
        "الجدول",
        "مواعيد",
        "موعد",
        "وقت",
        "متى",

        "ساعات",
        "ساعة",
        "ساعات معتمدة",

        "دكتور",
        "مدرس",
        "مدرس المادة",
        "المحاضر",

        "شعبة",
        "الشعبة",
        "شعب",

        "قاعة",
        "الغرفة",

        "معلومات المادة",
        "معلومات المساق",
        "تفاصيل المادة",

        "موادي",
        "مواد الفصل",
        "المساقات",
        "مساقاتي",

        "واجب",
        "واجبات",
        "وظائف",
        "تكاليف",

        "علامات",
        "علامة",
        "درجات",
        "معدلات",

        "إعلانات",
        "اعلانات",
        "إعلان",
        "اعلان",

        "كويز",
        "كويزات",
        "اختبار",
        "اختبارات",

        "تسليم",
        "التسليم",
        "مواعيد التسليم",
        "شو علي"
    ]

    for keyword in tool_keywords:

        if keyword in text:
            return True

    return False


# ============================================================
# SPECIFIC TOOL DETECTION
# ============================================================

def detect_specific_tool(user_input):
    """
    Deterministically identify obvious tool requests.
    """

    text = user_input.lower().strip()

    # --------------------------------------------------------
    # Upcoming deadlines
    # --------------------------------------------------------

    deadline_keywords = [
        "upcoming deadlines",
        "upcoming deadline",
        "due soon",
        "submit soon",
        "what do i need to submit",

        "مواعيد التسليم",
        "شو علي",
        "التسليم"
    ]

    if any(keyword in text for keyword in deadline_keywords):
        return "get_upcoming_deadlines"

    # --------------------------------------------------------
    # Attendance
    # --------------------------------------------------------

    attendance_keywords = [
        "attendance",
        "حضور",
        "غياب",
        "الحضور",
        "الغياب"
    ]

    if any(keyword in text for keyword in attendance_keywords):
        return "get_attendance"

    # --------------------------------------------------------
    # Quizzes
    # --------------------------------------------------------

    quiz_keywords = [
        "quizzes",
        "quiz",
        "tests",
        "test",
        "quiz dates",

        "كويز",
        "كويزات",
        "اختبار",
        "اختبارات"
    ]

    if any(keyword in text for keyword in quiz_keywords):
        return "get_quizzes"

    # --------------------------------------------------------
    # Assignments
    # --------------------------------------------------------

    assignment_keywords = [
        "assignments",
        "assignment",
        "homework",
        "tasks",
        "due dates",

        "واجب",
        "واجبات",
        "وظائف",
        "تكاليف"
    ]

    if any(keyword in text for keyword in assignment_keywords):
        return "get_assignments"

    # --------------------------------------------------------
    # Course information
    # --------------------------------------------------------

    course_info_keywords = [
        "credit hours",
        "credit hour",
        "instructor",
        "teacher",
        "section",
        "sections",
        "room",
        "course information",
        "course info",
        "activities",
        "activity",
        "materials",
        "material",
        "course content",
        "available content",

        "ساعات",
        "ساعة",
        "ساعات معتمدة",
        "دكتور",
        "مدرس",
        "مدرس المادة",
        "المحاضر",
        "شعبة",
        "الشعبة",
        "شعب",
        "قاعة",
        "الغرفة",
        "معلومات المادة",
        "معلومات المساق",
        "تفاصيل المادة"
    ]

    if any(keyword in text for keyword in course_info_keywords):
        return "get_course_info"

    # --------------------------------------------------------
    # Course schedule
    # --------------------------------------------------------

    schedule_keywords = [
        "schedule",
        "timetable",
        "class time",
        "lecture time",
        "what time",
        "when is",

        "جدول",
        "الجدول",
        "مواعيد",
        "موعد",
        "وقت",
        "متى"
    ]

    if any(keyword in text for keyword in schedule_keywords):
        return "get_course_schedule"

    return None


# ============================================================
# COURSE NAME EXTRACTION
# ============================================================

def extract_course_name(
    user_input,
    courses=None
):
    """
    Find the course mentioned in the user's question.

    If courses are supplied, use them directly instead of
    requesting the Moodle course list again.
    """

    text = user_input.lower().strip()

    if courses is None:

        courses = get_cached_courses()

    if not courses:

        print("[DEBUG] No courses found.")

        return None

    # --------------------------------------------------------
    # First: complete course name
    # --------------------------------------------------------

    for course in courses:

        course_name = course.get(
            "name",
            ""
        ).strip()

        if not course_name:
            continue

        if course_name.lower() in text:

            print(
                f"[DEBUG] Course found: "
                f"{course_name}"
            )

            return course_name

    # --------------------------------------------------------
    # Second: meaningful words
    # --------------------------------------------------------

    stop_words = {
        "the",
        "and",
        "of",
        "for",
        "in",
        "to",
        "a",
        "an",
        "course",
        "class"
    }

    for course in courses:

        course_name = course.get(
            "name",
            ""
        ).strip()

        if not course_name:
            continue

        words = (
            course_name
            .lower()
            .replace("-", " ")
            .split()
        )

        meaningful_words = [
            word
            for word in words
            if len(word) >= 5
            and word not in stop_words
        ]

        if not meaningful_words:
            continue

        matched_words = [
            word
            for word in meaningful_words
            if word in text
        ]

        if len(matched_words) >= 2:

            print(
                f"[DEBUG] Course found by word matching: "
                f"{course_name}"
            )

            return course_name

    print("[DEBUG] No matching course found.")

    return None


# ============================================================
# COURSE INFO FORMATTER
# ============================================================

def format_course_info_response(result):
    """
    Build a direct response from real Moodle course information.
    """

    if not isinstance(result, dict):

        return (
            "I could not read the course information."
        )

    course_name = result.get(
        "name",
        "Unknown course"
    )

    sections = result.get(
        "sections",
        []
    )

    lines = []

    lines.append(
        f"Course: {course_name}"
    )

    lines.append("")

    lines.append(
        f"Sections ({len(sections)}):"
    )

    total_activities = 0

    for index, section in enumerate(
        sections,
        start=1
    ):

        if not isinstance(section, dict):
            continue

        section_name = section.get(
            "name",
            "Unnamed section"
        )

        activities = section.get(
            "activities",
            []
        )

        total_activities += len(
            activities
        )

        lines.append(
            f"{index}. {section_name}"
        )

        if not activities:

            lines.append(
                "   - No activities"
            )

            continue

        for activity in activities:

            if not isinstance(
                activity,
                dict
            ):
                continue

            activity_name = activity.get(
                "name",
                "Unnamed activity"
            )

            activity_type = activity.get(
                "type",
                "Unknown"
            )

            lines.append(
                f"   - {activity_name} "
                f"[{activity_type}]"
            )

    lines.append("")

    lines.append(
        f"Total activities: "
        f"{total_activities}"
    )

    return "\n".join(lines)


# ============================================================
# GENERIC DATA HELPERS
# ============================================================

def get_result_list(result):
    """
    Convert common tool result structures into a list.

    This helps the direct-response system handle different
    Moodle tool response shapes.
    """

    if isinstance(result, list):
        return result

    if isinstance(result, dict):

        for key in [
            "assignments",
            "quizzes",
            "courses",
            "deadlines",
            "announcements",
            "grades",
            "items",
            "results"
        ]:

            value = result.get(key)

            if isinstance(value, list):
                return value

    return []


def get_first_value(item, keys, default=None):
    """
    Return the first existing value from a dictionary.
    """

    if not isinstance(item, dict):
        return default

    for key in keys:

        value = item.get(key)

        if value is not None and value != "":
            return value

    return default


# ============================================================
# DIRECT RESPONSE FORMATTERS
# ============================================================

def format_courses_response(result):
    """
    Build a direct response for the user's course list.
    """

    courses = get_result_list(result)

    if not courses:

        if isinstance(result, dict):

            if result.get("status") == "Error":

                return (
                    "I could not retrieve your courses "
                    "from Moodle."
                )

        return "No courses were found."

    lines = [
        f"You have {len(courses)} courses:"
    ]

    for index, course in enumerate(
        courses,
        start=1
    ):

        if isinstance(course, dict):

            name = get_first_value(
                course,
                ["name", "course_name"],
                "Unknown course"
            )

        else:

            name = str(course)

        lines.append(
            f"{index}. {name}"
        )

    return "\n".join(lines)


def format_assignments_response(result):
    """
    Build a concise direct response for assignments.

    The raw Moodle JSON is NOT sent to Ollama.
    """

    assignments = get_result_list(result)

    if not assignments:

        if isinstance(result, dict):

            if result.get("status") == "Error":

                return (
                    "I could not retrieve assignments "
                    "from Moodle."
                )

        return "You currently have no assignments found."


    # Group assignments by course.
    grouped = {}

    for assignment in assignments:

        if not isinstance(
            assignment,
            dict
        ):
            continue

        course = get_first_value(
            assignment,
            [
                "course",
                "course_name"
            ],
            "Unknown course"
        )

        grouped.setdefault(
            course,
            []
        ).append(
            assignment
        )

    total = len(assignments)

    lines = [
        f"I found {total} assignments:"
    ]

    for course, course_assignments in grouped.items():

        lines.append("")
        lines.append(
            f"{course}:"
        )

        for assignment in course_assignments:

            name = get_first_value(
                assignment,
                [
                    "name",
                    "assignment",
                    "title"
                ],
                "Unnamed assignment"
            )

            due = get_first_value(
                assignment,
                [
                    "due",
                    "due_date",
                    "deadline"
                ]
            )

            status = get_first_value(
                assignment,
                [
                    "submission_status",
                    "status"
                ]
            )

            line = f"- {name}"

            if due:
                line += f" | Due: {due}"

            if status:
                line += f" | {status}"

            lines.append(line)

    return "\n".join(lines)


def format_quizzes_response(result):
    """
    Build a concise direct response for quizzes.
    """

    quizzes = get_result_list(result)

    if not quizzes:

        if isinstance(result, dict):

            if result.get("status") == "Error":

                return (
                    "I could not retrieve quizzes "
                    "from Moodle."
                )

        return "You currently have no quizzes found."

    grouped = {}

    for quiz in quizzes:

        if not isinstance(
            quiz,
            dict
        ):
            continue

        course = get_first_value(
            quiz,
            [
                "course",
                "course_name"
            ],
            "Unknown course"
        )

        grouped.setdefault(
            course,
            []
        ).append(
            quiz
        )

    total = len(quizzes)

    lines = [
        f"I found {total} quizzes:"
    ]

    for course, course_quizzes in grouped.items():

        lines.append("")
        lines.append(
            f"{course}:"
        )

        for quiz in course_quizzes:

            name = get_first_value(
                quiz,
                [
                    "name",
                    "quiz",
                    "title"
                ],
                "Unnamed quiz"
            )

            due = get_first_value(
                quiz,
                [
                    "due",
                    "due_date",
                    "deadline",
                    "close"
                ]
            )

            status = get_first_value(
                quiz,
                [
                    "attempt_status",
                    "status"
                ]
            )

            line = f"- {name}"

            if due:
                line += f" | Due: {due}"

            if status:
                line += f" | {status}"

            lines.append(line)

    return "\n".join(lines)


def format_attendance_response(result):
    """
    Build a direct attendance response.
    """

    if not isinstance(result, dict):

        return "I could not read the attendance information."

    if result.get("status") == "Error":

        return (
            "I could not retrieve the attendance "
            "information."
        )

    course = result.get(
        "course",
        "Unknown course"
    )

    taken_sessions = result.get(
        "taken_sessions"
    )

    percentage = result.get(
        "percentage"
    )

    points = result.get(
        "points"
    )

    lines = [
        f"Course: {course}"
    ]

    if str(taken_sessions) == "0":

        lines.append(
            "There are currently no recorded "
            "attendance sessions."
        )

        return "\n".join(lines)

    if taken_sessions is not None:

        lines.append(
            f"Recorded sessions: {taken_sessions}"
        )

    if points is not None:

        lines.append(
            f"Attendance points: {points}"
        )

    if percentage is not None:

        lines.append(
            f"Attendance: {percentage}"
        )

    return "\n".join(lines)


def format_deadlines_response(result):
    """
    Build a concise direct response for upcoming deadlines.
    """

    deadlines = get_result_list(result)

    if not deadlines:

        if isinstance(result, dict):

            if result.get("status") == "Error":

                return (
                    "I could not retrieve upcoming deadlines."
                )

        return "There are no upcoming deadlines found."

    lines = [
        f"I found {len(deadlines)} upcoming deadlines:"
    ]

    for item in deadlines:

        if not isinstance(
            item,
            dict
        ):
            continue

        name = get_first_value(
            item,
            [
                "name",
                "title",
                "assignment",
                "quiz"
            ],
            "Unnamed item"
        )

        course = get_first_value(
            item,
            [
                "course",
                "course_name"
            ]
        )

        due = get_first_value(
            item,
            [
                "due",
                "due_date",
                "deadline"
            ]
        )

        line = f"- {name}"

        if course:
            line += f" | {course}"

        if due:
            line += f" | Due: {due}"

        lines.append(line)

    return "\n".join(lines)


def format_simple_tool_response(
    tool_name,
    result
):
    """
    Choose a fast deterministic formatter for a tool.

    Returns None when the tool should still use Ollama.
    """

    if tool_name == "get_my_courses":
        return format_courses_response(result)

    if tool_name == "get_assignments":
        return format_assignments_response(result)

    if tool_name == "get_quizzes":
        return format_quizzes_response(result)

    if tool_name == "get_attendance":
        return format_attendance_response(result)

    if tool_name == "get_upcoming_deadlines":
        return format_deadlines_response(result)

    if tool_name == "get_course_info":

        return format_course_info_response(
            result
        )

    return None


# ============================================================
# OLLAMA
# ============================================================

def ask_llm(messages):
    """
    Send messages to the local Ollama model.
    """

    response = ollama.chat(
        model=MODEL_NAME,
        messages=messages
    )

    return response[
        "message"
    ]["content"]


# ============================================================
# TOOL EXECUTION
# ============================================================

def execute_tool(
    tool_name,
    arguments
):
    """
    Execute a university tool safely.
    """

    tool_function = available_tools.get(
        tool_name
    )

    if tool_function is None:

        print(
            "[DEBUG] Unknown tool."
        )

        return {
            "status": "Error",
            "message": "Unknown tool."
        }

    print(
        f"[DEBUG] Tool: "
        f"{tool_name}"
    )

    print(
        f"[DEBUG] Arguments: "
        f"{arguments}"
    )

    start_tool = time.time()

    try:

        result = tool_function(
            **arguments
        )

    except TypeError as error:

        print(
            f"[DEBUG] Tool argument error: "
            f"{error}"
        )

        result = {
            "status": "Error",
            "message": (
                "Required tool arguments "
                "were missing."
            )
        }

    except Exception as error:

        print(
            f"[DEBUG] Tool execution error: "
            f"{error}"
        )

        result = {
            "status": "Error",
            "message": str(error)
        }

    tool_time = (
        time.time() - start_tool
    )

    print(
        f"[DEBUG] Tool execution time: "
        f"{tool_time:.2f} seconds"
    )

    print(
        f"[DEBUG] Tool result: "
        f"{result}"
    )

    return result


# ============================================================
# RUN TOOL AND RESPOND
# ============================================================

def run_tool_and_respond(
    tool_name,
    arguments,
    messages,
    start_total
):
    """
    Execute a tool.

    For simple university requests, return a direct response
    without using Ollama.

    For tools that still need natural-language interpretation,
    use Ollama.
    """

    result = execute_tool(
        tool_name,
        arguments
    )

    # --------------------------------------------------------
    # Unknown course
    # --------------------------------------------------------

    if (
        isinstance(result, dict)
        and result.get("status") == "Unknown"
    ):

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        course_name = arguments.get(
            "course_name",
            "the requested course"
        )

        return (
            f"The course '{course_name}' "
            "is not available in the "
            "university system."
        )

    # --------------------------------------------------------
    # FAST DIRECT RESPONSE
    # --------------------------------------------------------

    direct_response = format_simple_tool_response(
        tool_name,
        result
    )

    if direct_response is not None:

        print(
            "[DEBUG] Using direct response. "
            "Ollama final generation skipped."
        )

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        return direct_response

    # --------------------------------------------------------
    # FALLBACK TO OLLAMA
    # --------------------------------------------------------

    messages.append(
        {
            "role": "tool",
            "content": json.dumps(
                result,
                ensure_ascii=False
            )
        }
    )

    start_final = time.time()

    final_response = ask_llm(
        messages
    )

    final_time = (
        time.time() - start_final
    )

    print(
        f"[DEBUG] Final AI response time: "
        f"{final_time:.2f} seconds"
    )

    total_time = (
        time.time() - start_total
    )

    print(
        f"[DEBUG] Total time: "
        f"{total_time:.2f} seconds"
    )

    return final_response


# ============================================================
# MAIN PROCESS
# ============================================================

def process_user_message(user_input):
    """
    Main interface for the University AI Agent.

    This function receives a normal user message and returns
    the final response as text.

    It can be used by:
    - Terminal
    - Telegram
    - WhatsApp later
    - Web interface later
    """

    start_total = time.time()

    user_input = user_input.strip()

    if not user_input:

        return "Please enter a message."

    text = user_input.lower()

    # ========================================================
    # ROUTER
    # ========================================================

    needs_tool = route_question(
        user_input
    )

    print(
        f"[DEBUG] Router decision: "
        f"{'TOOL' if needs_tool else 'NO TOOL'}"
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_input
        }
    ]

    # ========================================================
    # NO TOOL
    # ========================================================

    if not needs_tool:

        start_ai = time.time()

        response_text = ask_llm(
            messages
        )

        ai_time = (
            time.time() - start_ai
        )

        print(
            f"[DEBUG] AI response time: "
            f"{ai_time:.2f} seconds"
        )

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        return response_text

    # ========================================================
    # MY COURSES
    # ========================================================

    my_courses_keywords = [
        "my courses",
        "current courses",
        "registered courses",
        "my subjects",
        "what courses",

        "موادي",
        "المواد",
        "مواد الفصل",
        "المساقات",
        "مساقاتي"
    ]

    if any(
        keyword in text
        for keyword in my_courses_keywords
    ):

        print(
            "[DEBUG] My courses requested."
        )

        return run_tool_and_respond(
            "get_my_courses",
            {},
            messages,
            start_total
        )

    # ========================================================
    # IDENTIFY SPECIFIC TOOL
    # ========================================================

    forced_tool = detect_specific_tool(
        user_input
    )

    print(
        f"[DEBUG] Detected tool: "
        f"{forced_tool}"
    )

    # ========================================================
    # DEADLINES
    # ========================================================

    if forced_tool == "get_upcoming_deadlines":

        print(
            "[DEBUG] Upcoming deadlines requested."
        )

        return run_tool_and_respond(
            "get_upcoming_deadlines",
            {},
            messages,
            start_total
        )

    # ========================================================
    # COURSE LIST
    #
    # Load it once only when a course-specific request
    # actually needs it.
    # ========================================================

    courses = None

    course_specific_tools = [
        "get_attendance",
        "get_course_schedule",
        "get_course_info"
    ]

    # ========================================================
    # COURSE-SPECIFIC TOOLS
    # ========================================================

    if forced_tool in course_specific_tools:

        print(
            "[DEBUG] This request requires a specific course."
        )

        print(
            "[DEBUG] Searching for course name..."
        )

        courses = get_cached_courses()

        course_name = extract_course_name(
            user_input,
            courses
        )

        if course_name is None:

            print(
                "[DEBUG] No course name found "
                "in user question."
            )

            total_time = (
                time.time() - start_total
            )

            print(
                f"[DEBUG] Total time: "
                f"{total_time:.2f} seconds"
            )

            return (
                "Please provide the course name."
            )

        print(
            f"[DEBUG] Course: "
            f"{course_name}"
        )

        return run_tool_and_respond(
            forced_tool,
            {
                "course_name": course_name
            },
            messages,
            start_total
        )

    # ========================================================
    # ASSIGNMENTS
    # ========================================================

    if forced_tool == "get_assignments":

        print(
            "[DEBUG] Assignments requested."
        )

        print(
            "[DEBUG] Checking whether a specific "
            "course was mentioned..."
        )

        courses = get_cached_courses()

        course_name = extract_course_name(
            user_input,
            courses
        )

        if course_name:

            print(
                f"[DEBUG] Specific course detected: "
                f"{course_name}"
            )

            arguments = {
                "course_name": course_name
            }

        else:

            print(
                "[DEBUG] No course specified. "
                "Getting assignments for all courses."
            )

            arguments = {}

        return run_tool_and_respond(
            "get_assignments",
            arguments,
            messages,
            start_total
        )

    # ========================================================
    # QUIZZES
    # ========================================================

    if forced_tool == "get_quizzes":

        print(
            "[DEBUG] Quizzes requested."
        )

        print(
            "[DEBUG] Checking whether a specific "
            "course was mentioned..."
        )

        courses = get_cached_courses()

        course_name = extract_course_name(
            user_input,
            courses
        )

        if course_name:

            print(
                f"[DEBUG] Specific course detected: "
                f"{course_name}"
            )

            arguments = {
                "course_name": course_name
            }

        else:

            print(
                "[DEBUG] No course specified. "
                "Getting quizzes for all courses."
            )

            arguments = {}

        return run_tool_and_respond(
            "get_quizzes",
            arguments,
            messages,
            start_total
        )

    # ========================================================
    # GRADES
    # ========================================================

    if any(
        keyword in text
        for keyword in [
            "grades",
            "grade",
            "marks",
            "mark",
            "scores",
            "score",

            "علامات",
            "علامة",
            "درجات",
            "معدلات"
        ]
    ):

        print(
            "[DEBUG] Grades requested."
        )

        return run_tool_and_respond(
            "get_grades",
            {},
            messages,
            start_total
        )

    # ========================================================
    # ANNOUNCEMENTS
    # ========================================================

    if any(
        keyword in text
        for keyword in [
            "announcements",
            "announcement",
            "latest announcements",

            "إعلانات",
            "اعلانات",
            "إعلان",
            "اعلان"
        ]
    ):

        print(
            "[DEBUG] Announcements requested."
        )

        return run_tool_and_respond(
            "get_announcements",
            {},
            messages,
            start_total
        )

    # ========================================================
    # COURSE NAME ONLY
    # ========================================================

    print(
        "[DEBUG] Checking whether user provided "
        "a course name only..."
    )

    courses = get_cached_courses()

    course_name_only = extract_course_name(
        user_input,
        courses
    )

    if course_name_only:

        print(
            "[DEBUG] User provided a course name "
            "without a specific request."
        )

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        return (
            f"I found the course "
            f"'{course_name_only}'.\n\n"
            "What would you like to know about it?\n"
            "For example: attendance, assignments, "
            "quizzes, schedule, or course information."
        )

    # ========================================================
    # AI TOOL DECISION
    # ========================================================

    start_ai = time.time()

    response = ollama.chat(
        model=MODEL_NAME,
        messages=messages,
        tools=tools
    )

    ai_decision_time = (
        time.time() - start_ai
    )

    print(
        f"[DEBUG] AI decision time: "
        f"{ai_decision_time:.2f} seconds"
    )

    tool_calls = response[
        "message"
    ].get(
        "tool_calls"
    )

    if tool_calls:

        print(
            "[DEBUG] Tool requested."
        )

        messages.append(
            response["message"]
        )

        for tool_call in tool_calls:

            tool_name = (
                tool_call["function"]["name"]
            )

            arguments = (
                tool_call["function"]["arguments"]
            )

            print(
                f"[DEBUG] Tool: "
                f"{tool_name}"
            )

            print(
                f"[DEBUG] Arguments: "
                f"{arguments}"
            )

            # ------------------------------------------------
            # Course-specific tools
            # ------------------------------------------------

            if tool_name in course_specific_tools:

                if courses is None:

                    courses = get_cached_courses()

                course_name = (
                    extract_course_name(
                        user_input,
                        courses
                    )
                )

                if course_name is None:

                    print(
                        "[DEBUG] AI selected a "
                        "course-specific tool, "
                        "but no course was provided."
                    )

                    return (
                        "Please provide the course name."
                    )

                arguments[
                    "course_name"
                ] = course_name

            # ------------------------------------------------
            # Assignments / quizzes
            # ------------------------------------------------

            elif tool_name in [
                "get_assignments",
                "get_quizzes"
            ]:

                if courses is None:

                    courses = get_cached_courses()

                course_name = extract_course_name(
                    user_input,
                    courses
                )

                if course_name:

                    arguments[
                        "course_name"
                    ] = course_name

                else:

                    arguments.pop(
                        "course_name",
                        None
                    )

            # ------------------------------------------------
            # Execute tool
            # ------------------------------------------------

            result = execute_tool(
                tool_name,
                arguments
            )

            print(
                f"[DEBUG] Tool result: "
                f"{result}"
            )

            # ------------------------------------------------
            # Unknown course
            # ------------------------------------------------

            if (
                isinstance(result, dict)
                and result.get("status") == "Unknown"
            ):

                total_time = (
                    time.time() - start_total
                )

                print(
                    f"[DEBUG] Total time: "
                    f"{total_time:.2f} seconds"
                )

                course_name = arguments.get(
                    "course_name",
                    "the requested course"
                )

                return (
                    f"The course '{course_name}' "
                    "is not available in the "
                    "university system."
                )

            # ------------------------------------------------
            # Direct response if possible
            # ------------------------------------------------

            direct_response = (
                format_simple_tool_response(
                    tool_name,
                    result
                )
            )

            if direct_response is not None:

                print(
                    "[DEBUG] Using direct response. "
                    "Ollama final generation skipped."
                )

                total_time = (
                    time.time() - start_total
                )

                print(
                    f"[DEBUG] Total time: "
                    f"{total_time:.2f} seconds"
                )

                return direct_response

            # ------------------------------------------------
            # Otherwise keep result for Ollama
            # ------------------------------------------------

            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        result,
                        ensure_ascii=False
                    )
                }
            )

        # ----------------------------------------------------
        # Final Ollama response
        # ----------------------------------------------------

        start_final = time.time()

        final_response = ask_llm(
            messages
        )

        final_time = (
            time.time() - start_final
        )

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        return final_response

    else:

        print(
            "[DEBUG] No tool requested by AI."
        )

        total_time = (
            time.time() - start_total
        )

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        return response[
            "message"
        ]["content"]


# ============================================================
# TERMINAL MODE
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 70
    )

    print(
        "UNIVERSITY AI AGENT"
    )

    print(
        "Terminal Mode"
    )

    print(
        "=" * 70
    )

    while True:

        user_input = input(
            "You: "
        )

        if user_input.lower() == "exit":

            print(
                "Agent: Goodbye!"
            )

            break

        response = process_user_message(
            user_input
        )

        print(
            "Agent:",
            response
        )
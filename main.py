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

When the user asks about grades, marks, scores,
or their current grades, use the grades tool.

When the user asks about announcements, university announcements,
course announcements, or latest announcements,
use the announcements tool.

When the user asks about quizzes, tests, or quiz dates,
use the quizzes tool.

When the user asks about upcoming deadlines,
what they need to submit soon, upcoming assignments and quizzes,
or what is due soon,
use the upcoming deadlines tool.

If the user is greeting you, asking what you can do,
or asking a general question that does not require university data,
do not use any tool.

If a tool requires a course name and the user did not provide one,
do not call the tool. Ask the user for the course name instead.

Never invent university information.

Keep your final answers short and direct.
"""


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
            "description": "Get the current assignments for the student's courses.",
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
            "description": "Get the current quizzes for the student's courses.",
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
            "name": "get_upcoming_deadlines",
            "description": "Get upcoming assignments and quizzes ordered by their due dates.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


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


def route_question(user_input):
    text = user_input.lower()

    tool_keywords = [
        "attendance",
        "طط¶ظˆط±",
        "ط؛ظٹط§ط¨",

        "schedule",
        "ط¬ط¯ظˆظ„",
        "when",
        "ظ…طھ‰",
        "ظˆظ‚طھ",

        "credit hours",
        "credit hour",
        "ط³ط§ط¹ط§طھ",

        "instructor",
        "ط¯ظƒطھظˆط±",
        "teacher",

        "section",
        "sections",
        "ط´ط¹ط¨ط©",

        "room",
        "ظ‚ط§ط¹ط©",

        "course information",
        "course info",
        "ظ…ط¹ظ„ظˆظ…ط§طھ ط§ظ„ظ…ط§ط©",

        "activities",
        "activity",
        "materials",
        "material",
        "content",
        "available",

        "my courses",
        "current courses",
        "registered courses",
        "my subjects",
        "what courses",
        "courses",

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
        "what do i need to submit"
    ]

    for keyword in tool_keywords:
        if keyword in text:
            return True

    return False


def detect_specific_tool(user_input):
    """
    Deterministically identify obvious tool requests.

    This prevents the small local LLM from choosing the wrong
    tool when the user's wording clearly identifies the request.
    """

    text = user_input.lower()

    # Attendance
    attendance_keywords = [
        "attendance"
    ]

    if any(keyword in text for keyword in attendance_keywords):
        return "get_attendance"

    # Course information
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
        "available content"
    ]

    if any(keyword in text for keyword in course_info_keywords):
        return "get_course_info"

    # Course schedule
    schedule_keywords = [
        "schedule",
        "timetable",
        "class time",
        "lecture time",
        "what time",
        "when is"
    ]

    if any(keyword in text for keyword in schedule_keywords):
        return "get_course_schedule"

    return None


def extract_course_name(user_input):
    """
    Find the course mentioned in the user's question
    using the real course list from Moodle.
    """

    text = user_input.lower().strip()

    print("[DEBUG] Searching for course name in Moodle courses...")

    try:
        courses = get_my_courses()
    except Exception as error:
        print(f"[DEBUG] Could not load Moodle courses: {error}")
        return None

    if not courses:
        print("[DEBUG] No courses found.")
        return None

    # First: try matching the complete course name
    for course in courses:
        course_name = course.get("name", "").strip()

        if not course_name:
            continue

        if course_name.lower() in text:
            print(f"[DEBUG] Course found: {course_name}")
            return course_name

    # Second: match meaningful words from course name
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
        course_name = course.get("name", "").strip()

        if not course_name:
            continue

        words = course_name.lower().replace("-", " ").split()

        meaningful_words = [
            word
            for word in words
            if len(word) >= 5 and word not in stop_words
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


def format_course_info_response(result):
    """
    Build a direct response from real Moodle course information.

    This avoids sending the complete course structure to the
    local LLM when the user explicitly asks for sections
    and activities.
    """

    if not isinstance(result, dict):
        return "I could not read the course information."

    course_name = result.get("name", "Unknown course")
    sections = result.get("sections", [])

    lines = []

    lines.append(
        f"Course: {course_name}"
    )

    lines.append("")
    lines.append(
        f"Sections ({len(sections)}):"
    )

    total_activities = 0

    for index, section in enumerate(sections, start=1):

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

        total_activities += len(activities)

        lines.append(
            f"{index}. {section_name}"
        )

        if not activities:

            lines.append(
                "   - No activities"
            )

            continue

        for activity in activities:

            if not isinstance(activity, dict):
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
                f"   - {activity_name} [{activity_type}]"
            )

    lines.append("")
    lines.append(
        f"Total activities: {total_activities}"
    )

    return "\n".join(lines)


while True:

    user_input = input("You: ")

    if user_input.lower() == "exit":
        print("Agent: Goodbye!")
        break

    start_total = time.time()

    needs_tool = route_question(user_input)

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

    # -----------------------------------
    # NO TOOL
    # -----------------------------------

    if not needs_tool:

        start_ai = time.time()

        response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        ai_time = time.time() - start_ai

        print(
            f"[DEBUG] AI response time: "
            f"{ai_time:.2f} seconds"
        )

        print(
            "Agent:",
            response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # MY COURSES
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "my courses",
            "current courses",
            "registered courses",
            "my subjects",
            "what courses",
            "courses"
        ]
    ):

        print("[DEBUG] My courses requested.")

        start_tool = time.time()

        result = get_my_courses()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # ASSIGNMENTS
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "assignments",
            "assignment",
            "homework",
            "tasks",
            "due dates"
        ]
    ):

        print("[DEBUG] Assignments requested.")

        start_tool = time.time()

        result = get_assignments()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # GRADES
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "grades",
            "grade",
            "marks",
            "mark",
            "scores",
            "score"
        ]
    ):

        print("[DEBUG] Grades requested.")

        start_tool = time.time()

        result = get_grades()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # ANNOUNCEMENTS
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "announcements",
            "announcement",
            "latest announcements"
        ]
    ):

        print("[DEBUG] Announcements requested.")

        start_tool = time.time()

        result = get_announcements()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # QUIZZES
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "quizzes",
            "quiz",
            "tests",
            "test",
            "quiz dates"
        ]
    ):

        print("[DEBUG] Quizzes requested.")

        start_tool = time.time()

        result = get_quizzes()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # UPCOMING DEADLINES
    # -----------------------------------

    if any(
        keyword in user_input.lower()
        for keyword in [
            "deadlines",
            "deadline",
            "upcoming deadlines",
            "due soon",
            "submit soon",
            "what do i need to submit"
        ]
    ):

        print("[DEBUG] Upcoming deadlines requested.")

        start_tool = time.time()

        result = get_upcoming_deadlines()

        tool_time = time.time() - start_tool

        print(
            f"[DEBUG] Tool execution time: "
            f"{tool_time:.2f} seconds"
        )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        messages.append(
            {
                "role": "tool",
                "content": json.dumps(result)
            }
        )

        start_final = time.time()

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # CHECK COURSE NAME
    # -----------------------------------

    course_name = extract_course_name(user_input)

    if course_name is None:

        print(
            "[DEBUG] No course name found in user question."
        )

        print(
            "Agent: Please provide the course name."
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # DETERMINE SPECIFIC TOOL
    # -----------------------------------

    forced_tool = detect_specific_tool(user_input)

    if forced_tool:

        print(
            f"[DEBUG] Deterministic tool selection: "
            f"{forced_tool}"
        )

        tool_name = forced_tool

        arguments = {
            "course_name": course_name
        }

        tool_function = available_tools.get(tool_name)

        if tool_function is None:

            result = {
                "status": "Error",
                "message": "Unknown tool."
            }

        else:

            print(f"[DEBUG] Tool: {tool_name}")
            print(f"[DEBUG] Arguments: {arguments}")

            start_tool = time.time()

            try:
                result = tool_function(**arguments)

            except TypeError as error:

                print(
                    f"[DEBUG] Tool argument error: "
                    f"{error}"
                )

                result = {
                    "status": "Error",
                    "message": "Required tool arguments were missing."
                }

            tool_time = time.time() - start_tool

            print(
                f"[DEBUG] Tool execution time: "
                f"{tool_time:.2f} seconds"
            )

        print(
            f"[DEBUG] Tool result: "
            f"{result}"
        )

        if result.get("status") == "Unknown":

            print(
                f"Agent: The course '{course_name}' "
                f"is not available in the university system."
            )

            continue

        # -----------------------------------
        # ATTENDANCE RESPONSE
        # -----------------------------------

        if tool_name == "get_attendance":

            taken_sessions = str(
                result.get("taken_sessions", "")
            ).strip()

            percentage = str(
                result.get("percentage", "")
            ).strip()

            returned_course = result.get(
                "course",
                course_name
            )

            if taken_sessions == "0":

                print(
                    "[DEBUG] Attendance has zero recorded sessions."
                )

                print(
                    "Agent:",
                    f"There are currently no recorded attendance "
                    f"sessions for {returned_course}. "
                    f"The recorded attendance percentage is "
                    f"{percentage}."
                )

                total_time = time.time() - start_total

                print(
                    f"[DEBUG] Total time: "
                    f"{total_time:.2f} seconds"
                )

                continue

        # -----------------------------------
        # DIRECT COURSE INFO RESPONSE
        # -----------------------------------

        if tool_name == "get_course_info":

            print(
                "[DEBUG] Building course information response "
                "directly from Moodle data..."
            )

            direct_response = format_course_info_response(
                result
            )

            print(
                "Agent:",
                direct_response
            )

            total_time = time.time() - start_total

            print(
                f"[DEBUG] Total time: "
                f"{total_time:.2f} seconds"
            )

            continue

        # -----------------------------------
        # PREPARE TOOL RESULT FOR AI
        # -----------------------------------

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

        final_response = ollama.chat(
            model="llama3.2:3b",
            messages=messages
        )

        final_time = time.time() - start_final

        print(
            f"[DEBUG] Final AI response time: "
            f"{final_time:.2f} seconds"
        )

        print(
            "Agent:",
            final_response["message"]["content"]
        )

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # AI TOOL DECISION
    # -----------------------------------

    start_ai = time.time()

    response = ollama.chat(
        model="llama3.2:3b",
        messages=messages,
        tools=tools
    )

    ai_decision_time = time.time() - start_ai

    print(
        f"[DEBUG] AI decision time: "
        f"{ai_decision_time:.2f} seconds"
    )

    tool_calls = response["message"].get("tool_calls")

    if tool_calls:

        print("[DEBUG] Tool requested.")

        messages.append(response["message"])

        for tool_call in tool_calls:

            tool_name = tool_call["function"]["name"]
            arguments = tool_call["function"]["arguments"]

            print(f"[DEBUG] Tool: {tool_name}")
            print(f"[DEBUG] Arguments: {arguments}")

            arguments["course_name"] = course_name

            tool_function = available_tools.get(tool_name)

            if tool_function is None:

                result = {
                    "status": "Error",
                    "message": "Unknown tool."
                }

            else:

                start_tool = time.time()

                try:
                    result = tool_function(**arguments)

                except TypeError as error:

                    print(
                        f"[DEBUG] Tool argument error: "
                        f"{error}"
                    )

                    result = {
                        "status": "Error",
                        "message": "Required tool arguments were missing."
                    }

                tool_time = time.time() - start_tool

                print(
                    f"[DEBUG] Tool execution time: "
                    f"{tool_time:.2f} seconds"
                )

            print(
                f"[DEBUG] Tool result: "
                f"{result}"
            )

            if result.get("status") == "Unknown":

                print(
                    f"Agent: The course '{course_name}' "
                    f"is not available in the university system."
                )

                break

            # -----------------------------------
            # DIRECT COURSE INFO RESPONSE
            # -----------------------------------

            if tool_name == "get_course_info":

                print(
                    "[DEBUG] Building course information response "
                    "directly from Moodle data..."
                )

                direct_response = format_course_info_response(
                    result
                )

                print(
                    "Agent:",
                    direct_response
                )

                total_time = time.time() - start_total

                print(
                    f"[DEBUG] Total time: "
                    f"{total_time:.2f} seconds"
                )

                break

            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(
                        result,
                        ensure_ascii=False
                    )
                }
            )

        else:

            print("[DEBUG] Messages before final response:")
            print(messages)

            # -----------------------------------
            # ATTENDANCE RESPONSE
            # -----------------------------------

            if tool_name == "get_attendance":

                taken_sessions = str(
                    result.get("taken_sessions", "")
                ).strip()

                percentage = str(
                    result.get("percentage", "")
                ).strip()

                returned_course = result.get(
                    "course",
                    course_name
                )

                if taken_sessions == "0":

                    print(
                        "[DEBUG] Attendance has zero recorded sessions."
                    )

                    print(
                        "Agent:",
                        f"There are currently no recorded attendance "
                        f"sessions for {returned_course}. "
                        f"The recorded attendance percentage is "
                        f"{percentage}."
                    )

                    total_time = time.time() - start_total

                    print(
                        f"[DEBUG] Total time: "
                        f"{total_time:.2f} seconds"
                    )

                    continue

            start_final = time.time()

            final_response = ollama.chat(
                model="llama3.2:3b",
                messages=messages
            )

            final_time = time.time() - start_final

            print(
                f"[DEBUG] Final AI response time: "
                f"{final_time:.2f} seconds"
            )

            print(
                "Agent:",
                final_response["message"]["content"]
            )

    else:

        print("[DEBUG] No tool requested by AI.")

        print(
            "Agent:",
            response["message"]["content"]
        )

    total_time = time.time() - start_total

    print(
        f"[DEBUG] Total time: "
        f"{total_time:.2f} seconds"
    )
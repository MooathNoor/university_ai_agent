import ollama
import json
import time

from tools import (
    get_attendance,
    get_course_schedule,
    get_course_info
)


SYSTEM_PROMPT = """
You are a University AI Agent.

You help students with university information.

You have access to tools that can provide university data.

Use a tool only when the user's question requires specific university data.

When the user asks about attendance, use the attendance tool.

When the user asks about a course schedule, use the schedule tool.

When the user asks about course information such as credit hours,
instructor, section, or room, use the course info tool.

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
            "description": "Get the schedule of a university course.",
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
            "description": "Get information about a university course, such as credit hours, instructor, section, and room.",
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
    }
]


available_tools = {
    "get_attendance": get_attendance,
    "get_course_schedule": get_course_schedule,
    "get_course_info": get_course_info
}


def route_question(user_input):
    text = user_input.lower()

    tool_keywords = [
        "attendance",
        "حضور",
        "غياب",

        "schedule",
        "جدول",
        "when",
        "متى",
        "وقت",

        "credit hours",
        "credit hour",
        "ساعات",

        "instructor",
        "دكتور",
        "teacher",

        "section",
        "شعبة",

        "room",
        "قاعة",

        "course information",
        "معلومات المادة"
    ]

    for keyword in tool_keywords:
        if keyword in text:
            return True

    return False


def extract_course_name(user_input):
    """
    Try to extract the course name from the user's question.

    This is a simple first version.
    Later we can replace this with a proper course database.
    """

    text = user_input.lower()

    known_courses = [
        "artificial intelligence",
        "data structures",
        "database management",
        "computer networks",
        "wireless networks",
        "object oriented programming",
        "internet programming",
        "robotics",
        "compilers"
    ]

    for course in known_courses:
        if course in text:
            return course.title()

    return None


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

        print("Agent:", response["message"]["content"])

        total_time = time.time() - start_total

        print(
            f"[DEBUG] Total time: "
            f"{total_time:.2f} seconds"
        )

        continue

    # -----------------------------------
    # TOOL
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

            # -----------------------------------
            # FIX: If AI did not provide course name
            # -----------------------------------

            if "course_name" not in arguments:

                course_name = extract_course_name(user_input)

                if course_name:

                    arguments["course_name"] = course_name

                    print(
                        f"[DEBUG] Extracted course name: "
                        f"{course_name}"
                    )

                else:

                    result = {
                        "status": "Error",
                        "message": "Course name was not provided."
                    }

                    messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(result)
                        }
                    )

                    continue

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

            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result)
                }
            )

        print("[DEBUG] Messages before final response:")
        print(messages)

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
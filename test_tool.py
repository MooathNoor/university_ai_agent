import ollama

messages = [
    {
        "role": "system",
        "content": "Answer briefly. Never invent information."
    },
    {
        "role": "user",
        "content": "Tell me about Mathematics."
    },
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "get_course_info",
                    "arguments": {
                        "course_name": "Mathematics"
                    }
                }
            }
        ]
    },
    {
        "role": "tool",
        "content": "Course not found"
    }
]

response = ollama.chat(
    model="llama3.2:3b",
    messages=messages
)

print("FULL RESPONSE:")
print(response)
import os
import requests
from dotenv import load_dotenv


# Load variables from .env
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


if not TOKEN:
    print("TELEGRAM_BOT_TOKEN was not found in .env")
    raise SystemExit()


url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"


print("Connecting to Telegram API...")

response = requests.get(url)

print(f"HTTP status: {response.status_code}")


if response.status_code != 200:
    print("Telegram API request failed.")
    print(response.text)
    raise SystemExit()


data = response.json()


if not data.get("ok"):
    print("Telegram API returned an error.")
    print(data)
    raise SystemExit()


updates = data.get("result", [])


if not updates:
    print("No messages found.")
    print("Make sure you sent a message to the bot.")
    raise SystemExit()


print("\nTelegram messages found:")
print("=" * 60)


for update in updates:

    message = update.get("message")

    if not message:
        continue

    chat = message.get("chat", {})

    chat_id = chat.get("id")
    username = chat.get("username")
    first_name = chat.get("first_name")
    text = message.get("text")

    print(f"Chat ID: {chat_id}")
    print(f"Username: {username}")
    print(f"First name: {first_name}")
    print(f"Message: {text}")
    print("=" * 60)
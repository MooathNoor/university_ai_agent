import os
import requests
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

CHAT_ID = "1707691637"


# ============================================================
# CHECK TOKEN
# ============================================================

if not TOKEN:

    print("TELEGRAM_BOT_TOKEN was not found in .env")
    raise SystemExit()


# ============================================================
# TELEGRAM API
# ============================================================

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


data = {
    "chat_id": CHAT_ID,
    "text": "Hello from University AI Agent! 🚀"
}


# ============================================================
# SEND MESSAGE
# ============================================================

print("Sending message to Telegram...")

response = requests.post(
    url,
    data=data
)


print(f"HTTP status: {response.status_code}")


# ============================================================
# CHECK RESPONSE
# ============================================================

if response.status_code != 200:

    print("Telegram API request failed.")
    print(response.text)

    raise SystemExit()


result = response.json()


if not result.get("ok"):

    print("Telegram API returned an error.")
    print(result)

    raise SystemExit()


print("\nMessage sent successfully!")
print("Check your Telegram bot.")
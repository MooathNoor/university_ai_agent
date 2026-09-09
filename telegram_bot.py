import os
import time

import requests
from dotenv import load_dotenv

from main import process_user_message


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)


# ============================================================
# TELEGRAM API CONFIGURATION
# ============================================================

TELEGRAM_API_URL = (
    f"https://api.telegram.org/"
    f"bot{TELEGRAM_BOT_TOKEN}"
)

REQUEST_TIMEOUT = 30

POLLING_DELAY = 1


# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(
    chat_id,
    text
):
    """
    Send a text message to a Telegram chat.

    This function communicates directly with
    the Telegram Bot API.
    """

    if not TELEGRAM_BOT_TOKEN:

        print(
            "Telegram bot token was not found in .env"
        )

        return False

    url = (
        f"{TELEGRAM_API_URL}/sendMessage"
    )

    data = {
        "chat_id": chat_id,
        "text": text
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=REQUEST_TIMEOUT
        )

    except requests.RequestException as error:

        print(
            f"[TELEGRAM] Send message failed: "
            f"{error}"
        )

        return False

    if response.status_code != 200:

        print(
            f"[TELEGRAM] Send message HTTP error: "
            f"{response.status_code}"
        )

        print(
            response.text
        )

        return False

    try:

        result = response.json()

    except ValueError:

        print(
            "[TELEGRAM] Invalid response from Telegram API."
        )

        return False

    if not result.get("ok"):

        print(
            "[TELEGRAM] Telegram API returned an error:"
        )

        print(
            result
        )

        return False

    return True


# ============================================================
# GET UPDATES
# ============================================================

def get_updates(
    offset=None
):
    """
    Ask Telegram for new incoming messages.

    This uses Telegram's long polling mechanism.
    """

    url = (
        f"{TELEGRAM_API_URL}/getUpdates"
    )

    params = {
        "timeout": 20
    }

    if offset is not None:

        params["offset"] = offset

    try:

        response = requests.get(
            url,
            params=params,
            timeout=25
        )

    except requests.RequestException as error:

        print(
            f"[TELEGRAM] getUpdates failed: "
            f"{error}"
        )

        return []

    if response.status_code != 200:

        print(
            f"[TELEGRAM] getUpdates HTTP error: "
            f"{response.status_code}"
        )

        print(
            response.text
        )

        return []

    try:

        result = response.json()

    except ValueError:

        print(
            "[TELEGRAM] Invalid getUpdates response."
        )

        return []

    if not result.get("ok"):

        print(
            "[TELEGRAM] Telegram API returned an error:"
        )

        print(
            result
        )

        return []

    return result.get(
        "result",
        []
    )


# ============================================================
# PROCESS TELEGRAM MESSAGE
# ============================================================

def process_telegram_message(
    update
):
    """
    Process one Telegram update.

    The user's message is sent to the University AI Agent,
    and the final response is sent back to Telegram.
    """

    message = update.get(
        "message"
    )

    if not message:

        return

    chat = message.get(
        "chat"
    )

    if not chat:

        return

    chat_id = chat.get(
        "id"
    )

    text = message.get(
        "text"
    )

    if not text:

        return

    text = text.strip()

    if not text:

        return

    print("\n")
    print("=" * 70)
    print("NEW TELEGRAM MESSAGE")
    print("=" * 70)

    print(
        f"Chat ID: {chat_id}"
    )

    print(
        f"User message: {text}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Special commands
    # --------------------------------------------------------

    if text.lower() == "/start":

        response_text = (
            "Welcome to University AI Agent.\n\n"
            "You can ask me about your university courses, "
            "attendance, assignments, quizzes, grades, "
            "announcements, and deadlines."
        )

        send_message(
            chat_id,
            response_text
        )

        return

    if text.lower() == "/help":

        response_text = (
            "I can help you with:\n\n"
            "- Your courses\n"
            "- Attendance\n"
            "- Course information\n"
            "- Assignments\n"
            "- Quizzes\n"
            "- Grades\n"
            "- Announcements\n"
            "- Upcoming deadlines\n\n"
            "Example:\n"
            "What courses do I have?"
        )

        send_message(
            chat_id,
            response_text
        )

        return

    # --------------------------------------------------------
    # Send message to University AI Agent
    # --------------------------------------------------------

    print(
        "[TELEGRAM] Sending message to University AI Agent..."
    )

    start_time = time.time()

    try:

        response_text = process_user_message(
            text
        )

    except Exception as error:

        print(
            f"[TELEGRAM] Agent processing error: "
            f"{error}"
        )

        response_text = (
            "Sorry, an error occurred while processing "
            "your request."
        )

    processing_time = (
        time.time() - start_time
    )

    print(
        f"[TELEGRAM] Agent processing time: "
        f"{processing_time:.2f} seconds"
    )

    # --------------------------------------------------------
    # Send Agent response back to Telegram
    # --------------------------------------------------------

    print(
        "[TELEGRAM] Sending Agent response..."
    )

    success = send_message(
        chat_id,
        response_text
    )

    if success:

        print(
            "[TELEGRAM] Response sent successfully."
        )

    else:

        print(
            "[TELEGRAM] Failed to send Agent response."
        )


# ============================================================
# START BOT
# ============================================================

def start_bot():
    """
    Start the Telegram conversational bot.

    The bot continuously checks Telegram for new messages.
    """

    if not TELEGRAM_BOT_TOKEN:

        print(
            "=" * 70
        )

        print(
            "TELEGRAM BOT ERROR"
        )

        print(
            "=" * 70
        )

        print(
            "TELEGRAM_BOT_TOKEN was not found in .env"
        )

        return

    print(
        "=" * 70
    )

    print(
        "UNIVERSITY AI AGENT"
    )

    print(
        "Telegram Conversational Mode"
    )

    print(
        "=" * 70
    )

    print(
        "Bot is starting..."
    )

    print(
        "Waiting for Telegram messages..."
    )

    print(
        "Press Ctrl+C to stop the bot."
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Telegram update offset
    # --------------------------------------------------------

    offset = None

    while True:

        try:

            updates = get_updates(
                offset
            )

            for update in updates:

                update_id = update.get(
                    "update_id"
                )

                if update_id is not None:

                    offset = update_id + 1

                process_telegram_message(
                    update
                )

        except KeyboardInterrupt:

            print(
                "\n"
            )

            print(
                "=" * 70
            )

            print(
                "Telegram bot stopped."
            )

            print(
                "=" * 70
            )

            break

        except Exception as error:

            print(
                f"\n[TELEGRAM] Unexpected error: "
                f"{error}"
            )

            print(
                "Bot will continue running..."
            )

            time.sleep(
                POLLING_DELAY
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    start_bot()
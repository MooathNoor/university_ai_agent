import os
import time

import requests
from dotenv import load_dotenv

from main import process_user_message


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# ============================================================
# TELEGRAM API CONFIGURATION
# ============================================================

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
REQUEST_TIMEOUT = 30
POLLING_DELAY = 1

# Telegram currently accepts text messages up to 4096 characters. Keep a
# safety margin so future formatting/escaping changes do not push a chunk over
# the limit.
TELEGRAM_SAFE_MESSAGE_LENGTH = 3800


# ============================================================
# MESSAGE CHUNKING
# ============================================================

def split_long_message(text, max_length=TELEGRAM_SAFE_MESSAGE_LENGTH):
    """Split a long response into Telegram-safe chunks.

    Prefer paragraph/newline boundaries, then spaces. If one token/line is
    still too large, hard-split it. Empty chunks are never returned.
    """
    text = "" if text is None else str(text)
    if len(text) <= max_length:
        return [text] if text else []

    chunks = []
    remaining = text

    while len(remaining) > max_length:
        window = remaining[: max_length + 1]

        # Prefer splitting at the latest newline, then at the latest space.
        split_at = window.rfind("\n")
        if split_at < max_length // 2:
            split_at = window.rfind(" ")
        if split_at <= 0:
            split_at = max_length

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            split_at = max_length

        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip("\n ")

    if remaining:
        chunks.append(remaining)

    return chunks


# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(chat_id, text):
    """Send one Telegram-safe text message to a Telegram chat."""

    if not TELEGRAM_BOT_TOKEN:
        print("Telegram bot token was not found in .env")
        return False

    url = f"{TELEGRAM_API_URL}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": str(text),
    }

    try:
        response = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as error:
        print(f"[TELEGRAM] Send message failed: {error}")
        return False

    if response.status_code != 200:
        print(f"[TELEGRAM] Send message HTTP error: {response.status_code}")
        print(response.text)
        return False

    try:
        result = response.json()
    except ValueError:
        print("[TELEGRAM] Invalid response from Telegram API.")
        return False

    if not result.get("ok"):
        print("[TELEGRAM] Telegram API returned an error:")
        print(result)
        return False

    return True


def send_long_message(chat_id, text):
    """Send an agent response safely even when it exceeds Telegram's limit."""
    chunks = split_long_message(text)

    if not chunks:
        chunks = ["ما طلع عندي رد واضح على طلبك هسا."]

    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        if total > 1:
            print(f"[TELEGRAM] Sending response chunk {index}/{total} ({len(chunk)} chars)...")

        if not send_message(chat_id, chunk):
            print(f"[TELEGRAM] Failed while sending response chunk {index}/{total}.")
            return False

    return True


# ============================================================
# GET UPDATES
# ============================================================

def get_updates(offset=None):
    """Ask Telegram for new incoming messages using long polling."""

    url = f"{TELEGRAM_API_URL}/getUpdates"
    params = {"timeout": 20}

    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params, timeout=25)
    except requests.RequestException as error:
        print(f"[TELEGRAM] getUpdates failed: {error}")
        return []

    if response.status_code != 200:
        print(f"[TELEGRAM] getUpdates HTTP error: {response.status_code}")
        print(response.text)
        return []

    try:
        result = response.json()
    except ValueError:
        print("[TELEGRAM] Invalid getUpdates response.")
        return []

    if not result.get("ok"):
        print("[TELEGRAM] Telegram API returned an error:")
        print(result)
        return []

    return result.get("result", [])


# ============================================================
# PROCESS TELEGRAM MESSAGE
# ============================================================

def process_telegram_message(update):
    """Process one Telegram update and send the agent's final response."""

    message = update.get("message")
    if not message:
        return

    chat = message.get("chat")
    if not chat:
        return

    chat_id = chat.get("id")
    text = message.get("text")
    if not text:
        return

    text = text.strip()
    if not text:
        return

    print("\n")
    print("=" * 70)
    print("NEW TELEGRAM MESSAGE")
    print("=" * 70)
    print(f"Chat ID: {chat_id}")
    print(f"User message: {text}")
    print("=" * 70)

    # --------------------------------------------------------
    # Special commands
    # --------------------------------------------------------

    if text.lower() == "/start":
        response_text = (
            "أهلا أخوي 👋 أنا وكيلك الجامعي الذكي. "
            "اسألني بشكل طبيعي عن موادك، الحضور، الواجبات، الكويزات، العلامات والملفات."
        )
        send_long_message(chat_id, response_text)
        return

    if text.lower() == "/help":
        response_text = (
            "احكي معي بشكل طبيعي عن أمور الجامعة. بقدر أساعدك بالمواد، الحضور، "
            "الواجبات، الكويزات وعلاماتها، المواعيد والملفات."
        )
        send_long_message(chat_id, response_text)
        return

    # --------------------------------------------------------
    # Send message to University AI Agent
    # --------------------------------------------------------

    print("[TELEGRAM] Sending message to University AI Agent...")
    start_time = time.time()

    try:
        response_text = process_user_message(text)
    except Exception as error:
        # Keep the detailed error in the console for debugging, but speak to the
        # user naturally instead of exposing an internal/technical error string.
        print(f"[TELEGRAM] Agent processing error: {error}")
        response_text = (
            "صار معي خلل وأنا بعالج طلبك هسا. جرّب تبعثه مرة ثانية، "
            "وإذا ضل نفس الإشي بنفحصه."
        )

    processing_time = time.time() - start_time
    print(f"[TELEGRAM] Agent processing time: {processing_time:.2f} seconds")

    # --------------------------------------------------------
    # Send Agent response back to Telegram
    # --------------------------------------------------------

    print("[TELEGRAM] Sending Agent response...")
    success = send_long_message(chat_id, response_text)

    if success:
        print("[TELEGRAM] Response sent successfully.")
    else:
        print("[TELEGRAM] Failed to send Agent response.")


# ============================================================
# START BOT
# ============================================================

def start_bot():
    """Start the Telegram conversational bot."""

    if not TELEGRAM_BOT_TOKEN:
        print("=" * 70)
        print("TELEGRAM BOT ERROR")
        print("=" * 70)
        print("TELEGRAM_BOT_TOKEN was not found in .env")
        return

    print("=" * 70)
    print("UNIVERSITY AI AGENT")
    print("Telegram Conversational Mode")
    print("=" * 70)
    print("Bot is starting...")
    print("Waiting for Telegram messages...")
    print("Press Ctrl+C to stop the bot.")
    print("=" * 70)

    offset = None

    while True:
        try:
            updates = get_updates(offset)

            for update in updates:
                update_id = update.get("update_id")
                if update_id is not None:
                    offset = update_id + 1

                process_telegram_message(update)

        except KeyboardInterrupt:
            print("\n")
            print("=" * 70)
            print("Telegram bot stopped.")
            print("=" * 70)
            break

        except Exception as error:
            print(f"\n[TELEGRAM] Unexpected error: {error}")
            print("Bot will continue running...")
            time.sleep(POLLING_DELAY)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    start_bot()

import os
import queue
import threading
import time

import requests
from dotenv import load_dotenv

from main import (
    get_fast_conversation_response,
    process_user_message,
)


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
# BACKGROUND PROCESSING QUEUE
# ============================================================

# Heavy agent turns are processed sequentially in one worker so conversation
# state remains ordered and race-free. The polling loop stays free to receive
# new Telegram updates while that worker is busy.
_MESSAGE_QUEUE = queue.Queue()
_WORKER_STOP = object()


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
# UPDATE HELPERS
# ============================================================

def _extract_text_message(update):
    """Return (chat_id, text) for a normal text message, otherwise (None, None)."""
    message = update.get("message")
    if not message:
        return None, None

    chat = message.get("chat")
    if not chat:
        return None, None

    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None or not text:
        return None, None

    text = text.strip()
    if not text:
        return None, None

    return chat_id, text


def _print_incoming(chat_id, text):
    print("\n")
    print("=" * 70)
    print("NEW TELEGRAM MESSAGE")
    print("=" * 70)
    print(f"Chat ID: {chat_id}")
    print(f"User message: {text}")
    print("=" * 70)


# ============================================================
# PROCESS TELEGRAM MESSAGE
# ============================================================

def process_telegram_message(update):
    """Process one queued Telegram update and send the agent's final response."""

    chat_id, text = _extract_text_message(update)
    if chat_id is None:
        return

    _print_incoming(chat_id, text)

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
# BACKGROUND WORKER
# ============================================================

def _message_worker():
    """Process heavy/user-stateful messages in arrival order."""
    while True:
        update = _MESSAGE_QUEUE.get()
        try:
            if update is _WORKER_STOP:
                return
            process_telegram_message(update)
        except Exception as error:
            print(f"[TELEGRAM] Worker error: {error}")
        finally:
            _MESSAGE_QUEUE.task_done()


def _start_message_worker():
    worker = threading.Thread(
        target=_message_worker,
        name="telegram-agent-worker",
        daemon=True,
    )
    worker.start()
    return worker


def _try_fast_response(update):
    """Reply immediately to side-effect-free social/control turns.

    This runs in the polling thread, so a greeting such as "مساء الخير" can be
    answered even while the background agent worker is handling a slow Moodle or
    local-LLM request. Stateful university turns are never handled here.
    """
    chat_id, text = _extract_text_message(update)
    if chat_id is None:
        return False

    if text.lower() in {"/start", "/help"}:
        return False

    try:
        response_text = get_fast_conversation_response(text)
    except Exception as error:
        print(f"[TELEGRAM] Fast-response check failed: {error}")
        return False

    if response_text is None:
        return False

    _print_incoming(chat_id, text)
    print("[TELEGRAM] Fast local response (no Moodle/Ollama).")
    success = send_long_message(chat_id, response_text)
    if success:
        print("[TELEGRAM] Fast response sent successfully.")
    else:
        print("[TELEGRAM] Fast response failed.")
    return True


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

    worker = _start_message_worker()
    offset = None

    try:
        while True:
            try:
                updates = get_updates(offset)

                for update in updates:
                    update_id = update.get("update_id")
                    if update_id is not None:
                        offset = update_id + 1

                    # Social/control messages can be answered immediately even
                    # while one heavy agent turn is running in the worker.
                    if _try_fast_response(update):
                        continue

                    _MESSAGE_QUEUE.put(update)

            except KeyboardInterrupt:
                raise

            except Exception as error:
                print(f"\n[TELEGRAM] Unexpected polling error: {error}")
                print("Bot will continue running...")
                time.sleep(POLLING_DELAY)

    except KeyboardInterrupt:
        print("\n")
        print("=" * 70)
        print("Telegram bot stopped.")
        print("=" * 70)

    finally:
        _MESSAGE_QUEUE.put(_WORKER_STOP)
        worker.join(timeout=2)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    start_bot()

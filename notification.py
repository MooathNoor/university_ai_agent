import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# RETRY CONFIGURATION
# ============================================================

MAX_RETRIES = 3

INITIAL_RETRY_DELAY = 2


# ============================================================
# NOTIFICATION PRIORITIES
# ============================================================

NOTIFICATION_PRIORITIES = {
    "NEW_ASSIGNMENT": "NORMAL",
    "ASSIGNMENT_CHANGED": "NORMAL",
    "NEW_QUIZ": "HIGH",
    "QUIZ_CHANGED": "NORMAL",
    "ATTENDANCE_CHANGED": "HIGH"
}


# ============================================================
# NOTIFICATION ROUTING
# ============================================================

NOTIFICATION_ROUTES = {
    "NORMAL": "console",
    "HIGH": "telegram"
}


# ============================================================
# GET NOTIFICATION PRIORITY
# ============================================================

def get_notification_priority(notification_type):
    """
    Get the priority of a notification type.

    If the notification type is not defined,
    NORMAL priority is used.
    """

    return NOTIFICATION_PRIORITIES.get(
        notification_type,
        "NORMAL"
    )


# ============================================================
# GET NOTIFICATION CHANNEL
# ============================================================

def get_notification_channel(priority):
    """
    Decide which notification channel should be used
    based on notification priority.

    Current routing:

    NORMAL -> Console
    HIGH   -> Telegram
    """

    return NOTIFICATION_ROUTES.get(
        priority,
        "console"
    )


# ============================================================
# FORMAT NOTIFICATION
# ============================================================

def format_notification(
    notification_type,
    message
):
    """
    Format a notification before sending it.

    This creates a cleaner and more professional
    notification message.

    The original message is preserved inside
    the formatted notification.
    """

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    if notification_type == "NEW_ASSIGNMENT":

        title = "📝 New Assignment"

    elif notification_type == "ASSIGNMENT_CHANGED":

        title = "🔄 Assignment Updated"

    elif notification_type == "NEW_QUIZ":

        title = "🧠 New Quiz"

    elif notification_type == "QUIZ_CHANGED":

        title = "🔄 Quiz Updated"

    elif notification_type == "ATTENDANCE_CHANGED":

        title = "⚠️ Attendance Update"

    else:

        title = "🔔 University AI Agent"

    formatted_message = (
        "🎓 University AI Agent\n"
        "\n"
        f"{title}\n"
        "\n"
        f"{message}\n"
        "\n"
        f"🕒 {timestamp}"
    )

    return formatted_message


# ============================================================
# CONSOLE NOTIFICATION
# ============================================================

def send_console_notification(
    notification_type,
    message
):
    """
    Send a notification to the console.

    The notification includes:
    - timestamp
    - notification type
    - priority
    - message
    """

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    priority = get_notification_priority(
        notification_type
    )

    print("\n")
    print("=" * 70)
    print("UNIVERSITY AI AGENT - NOTIFICATION")
    print("=" * 70)

    print(
        f"Time: {timestamp}"
    )

    print(
        f"Type: {notification_type}"
    )

    print(
        f"Priority: {priority}"
    )

    print(
        f"Message: {message}"
    )

    print("=" * 70)


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def send_telegram_notification(
    message
):
    """
    Send a notification through Telegram Bot API.

    The function automatically retries failed requests.

    Retry strategy:

    Attempt 1 -> immediate
    Attempt 2 -> wait 2 seconds
    Attempt 3 -> wait 4 seconds

    If all attempts fail, the function returns False.
    """

    if not TELEGRAM_BOT_TOKEN:

        print(
            "\nTelegram notification failed:"
        )

        print(
            "TELEGRAM_BOT_TOKEN was not found "
            "in .env"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "\nTelegram notification failed:"
        )

        print(
            "TELEGRAM_CHAT_ID was not found "
            "in .env"
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"\n[TELEGRAM] "
            f"Attempt {attempt}/{MAX_RETRIES}"
        )

        try:

            response = requests.post(
                url,
                data=data,
                timeout=15
            )

        except requests.RequestException as error:

            print(
                "\nTelegram API request failed:"
            )

            print(error)

            if attempt < MAX_RETRIES:

                retry_delay = (
                    INITIAL_RETRY_DELAY
                    * (2 ** (attempt - 1))
                )

                print(
                    f"\nRetrying in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(retry_delay)

                continue

            print(
                "\nTelegram notification failed "
                "after all retry attempts."
            )

            return False

        print(
            f"\nTelegram API status: "
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(
                "\nTelegram API returned an error:"
            )

            print(response.text)

            if attempt < MAX_RETRIES:

                retry_delay = (
                    INITIAL_RETRY_DELAY
                    * (2 ** (attempt - 1))
                )

                print(
                    f"\nRetrying in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(retry_delay)

                continue

            print(
                "\nTelegram notification failed "
                "after all retry attempts."
            )

            return False

        try:

            result = response.json()

        except ValueError:

            print(
                "\nTelegram API returned "
                "an invalid response."
            )

            if attempt < MAX_RETRIES:

                retry_delay = (
                    INITIAL_RETRY_DELAY
                    * (2 ** (attempt - 1))
                )

                print(
                    f"\nRetrying in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(retry_delay)

                continue

            print(
                "\nTelegram notification failed "
                "after all retry attempts."
            )

            return False

        if not result.get("ok"):

            print(
                "\nTelegram API reported a failure:"
            )

            print(result)

            if attempt < MAX_RETRIES:

                retry_delay = (
                    INITIAL_RETRY_DELAY
                    * (2 ** (attempt - 1))
                )

                print(
                    f"\nRetrying in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(retry_delay)

                continue

            print(
                "\nTelegram notification failed "
                "after all retry attempts."
            )

            return False

        print(
            "\nTelegram notification sent successfully."
        )

        return True

    return False


# ============================================================
# NOTIFICATION MANAGER
# ============================================================

def send_notification(
    notification_type,
    message,
    channel="auto"
):
    """
    Send a notification through the selected channel.

    If channel is "auto", the Notification Manager
    automatically chooses the channel based on priority.

    Current automatic routing:

    NORMAL -> Console
    HIGH   -> Telegram

    Supported explicit channels:
    - console
    - telegram
    - auto
    """

    priority = get_notification_priority(
        notification_type
    )

    # --------------------------------------------------------
    # Automatic routing
    # --------------------------------------------------------

    if channel == "auto":

        channel = get_notification_channel(
            priority
        )

    print(
        f"\n[NOTIFICATION MANAGER] "
        f"Type: {notification_type} | "
        f"Priority: {priority} | "
        f"Channel: {channel}"
    )

    # --------------------------------------------------------
    # Format message
    # --------------------------------------------------------

    formatted_message = format_notification(
        notification_type,
        message
    )

    # --------------------------------------------------------
    # Console channel
    # --------------------------------------------------------

    if channel == "console":

        send_console_notification(
            notification_type,
            formatted_message
        )

        return True

    # --------------------------------------------------------
    # Telegram channel
    # --------------------------------------------------------

    if channel == "telegram":

        return send_telegram_notification(
            formatted_message
        )

    # --------------------------------------------------------
    # Unsupported channel
    # --------------------------------------------------------

    print(
        f"\nUnsupported notification channel: "
        f"{channel}"
    )

    return False


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("\n")
    print("=" * 70)
    print("TESTING NOTIFICATION ROUTING")
    print("=" * 70)

    test_notifications = [
        (
            "NEW_ASSIGNMENT",
            "New assignment detected in Cloud Computing."
        ),
        (
            "NEW_QUIZ",
            "New quiz detected in Cloud Computing."
        ),
        (
            "ATTENDANCE_CHANGED",
            "Attendance is now open for Cloud Computing."
        ),
        (
            "QUIZ_CHANGED",
            "Quiz grade changed from 8.00 to 9.00."
        )
    ]

    all_passed = True

    # --------------------------------------------------------
    # Test automatic routing
    # --------------------------------------------------------

    for notification_type, message in test_notifications:

        priority = get_notification_priority(
            notification_type
        )

        expected_channel = get_notification_channel(
            priority
        )

        print(
            f"\nTesting: {notification_type}"
        )

        print(
            f"Priority: {priority}"
        )

        print(
            f"Expected channel: {expected_channel}"
        )

        success = send_notification(
            notification_type,
            message,
            channel="auto"
        )

        if not success:

            all_passed = False

    # --------------------------------------------------------
    # Test explicit console channel
    # --------------------------------------------------------

    print("\n")
    print("-" * 70)
    print("TESTING EXPLICIT CONSOLE CHANNEL")
    print("-" * 70)

    success = send_notification(
        "NEW_ASSIGNMENT",
        "Explicit console channel test.",
        channel="console"
    )

    if not success:

        all_passed = False

    # --------------------------------------------------------
    # Test explicit Telegram channel
    # --------------------------------------------------------

    print("\n")
    print("-" * 70)
    print("TESTING EXPLICIT TELEGRAM CHANNEL")
    print("-" * 70)

    success = send_notification(
        "NEW_QUIZ",
        "Explicit Telegram channel test from University AI Agent.",
        channel="telegram"
    )

    if not success:

        all_passed = False

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print("\n" + "=" * 70)

    if all_passed:

        print(
            "NOTIFICATION ROUTING TEST PASSED"
        )

    else:

        print(
            "NOTIFICATION ROUTING TEST FAILED"
        )

    print("=" * 70)
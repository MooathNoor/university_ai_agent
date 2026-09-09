import time

import notification


# ============================================================
# TEST CONFIGURATION
# ============================================================

TEST_MAX_RETRIES = 3
TEST_INITIAL_RETRY_DELAY = 2


# ============================================================
# FAKE TELEGRAM REQUEST
# ============================================================

class FakeResponse:
    """
    Simulates a Telegram API response.
    """

    def __init__(self, status_code=200, ok=True):
        self.status_code = status_code
        self._ok = ok
        self.text = "Simulated response"

    def json(self):
        return {
            "ok": self._ok
        }


# ============================================================
# RETRY SIMULATION
# ============================================================

def simulate_retry():

    print("\n")
    print("=" * 70)
    print("TESTING TELEGRAM RETRY LOGIC")
    print("=" * 70)

    print("\nScenario:")
    print("Attempt 1 -> Failure")
    print("Attempt 2 -> Failure")
    print("Attempt 3 -> Success")

    print("\nExpected retry delays:")
    print("After attempt 1 -> 2 seconds")
    print("After attempt 2 -> 4 seconds")

    attempts = 0
    attempt_times = []

    original_post = notification.requests.post
    original_sleep = notification.time.sleep

    # --------------------------------------------------------
    # Fake requests.post
    # --------------------------------------------------------

    def fake_post(url, data, timeout):

        nonlocal attempts

        attempts += 1

        attempt_times.append(
            time.time()
        )

        print(
            f"\n[TEST] Fake Telegram request "
            f"attempt {attempts}"
        )

        if attempts < 3:

            print(
                "[TEST] Simulated failure ❌"
            )

            return FakeResponse(
                status_code=500,
                ok=False
            )

        print(
            "[TEST] Simulated success ✅"
        )

        return FakeResponse(
            status_code=200,
            ok=True
        )

    # --------------------------------------------------------
    # Fake sleep
    # --------------------------------------------------------

    recorded_delays = []

    def fake_sleep(seconds):

        recorded_delays.append(seconds)

        print(
            f"[TEST] Simulated waiting: "
            f"{seconds} seconds"
        )

    # --------------------------------------------------------
    # Replace real functions temporarily
    # --------------------------------------------------------

    notification.requests.post = fake_post
    notification.time.sleep = fake_sleep

    notification.MAX_RETRIES = TEST_MAX_RETRIES
    notification.INITIAL_RETRY_DELAY = (
        TEST_INITIAL_RETRY_DELAY
    )

    try:

        # ----------------------------------------------------
        # Run notification
        # ----------------------------------------------------

        success = notification.send_telegram_notification(
            "Retry test message - University AI Agent"
        )

    finally:

        # ----------------------------------------------------
        # Restore original functions
        # ----------------------------------------------------

        notification.requests.post = original_post
        notification.time.sleep = original_sleep

    # ========================================================
    # VALIDATION
    # ========================================================

    print("\n")
    print("-" * 70)
    print("VALIDATING RETRY BEHAVIOR")
    print("-" * 70)

    all_passed = True

    # --------------------------------------------------------
    # Check final result
    # --------------------------------------------------------

    if success:

        print(
            "Final notification result: SUCCESS ✅"
        )

    else:

        print(
            "Final notification result: FAILED ❌"
        )

        all_passed = False

    # --------------------------------------------------------
    # Check number of attempts
    # --------------------------------------------------------

    print(
        f"Total attempts: {attempts}"
    )

    if attempts == 3:

        print(
            "Attempt count test: PASSED ✅"
        )

    else:

        print(
            "Attempt count test: FAILED ❌"
        )

        all_passed = False

    # --------------------------------------------------------
    # Check retry delays
    # --------------------------------------------------------

    print(
        f"Recorded retry delays: "
        f"{recorded_delays}"
    )

    expected_delays = [2, 4]

    if recorded_delays == expected_delays:

        print(
            "Exponential backoff test: PASSED ✅"
        )

    else:

        print(
            "Exponential backoff test: FAILED ❌"
        )

        all_passed = False

    # --------------------------------------------------------
    # Check no extra attempts
    # --------------------------------------------------------

    if attempts == 3:

        print(
            "Stops after successful retry: PASSED ✅"
        )

    else:

        print(
            "Stops after successful retry: FAILED ❌"
        )

        all_passed = False

    # ========================================================
    # FINAL RESULT
    # ========================================================

    print("\n" + "=" * 70)

    if all_passed:

        print(
            "TELEGRAM RETRY TEST PASSED"
        )

    else:

        print(
            "TELEGRAM RETRY TEST FAILED"
        )

    print("=" * 70)


# ============================================================
# RUN TEST
# ============================================================

if __name__ == "__main__":

    simulate_retry()
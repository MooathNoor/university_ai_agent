import requests

import lms_client


# ============================================================
# TEST CONFIGURATION
# ============================================================

TEST_TIMEOUT = 15


# ============================================================
# FAKE RESPONSE
# ============================================================

class FakeResponse:
    """
    Simulates a normal HTTP response.
    """

    def __init__(
        self,
        status_code=200,
        url="https://elearning3.bau.edu.jo/huson/my/"
    ):

        self.status_code = status_code
        self.url = url
        self.text = "<html></html>"


# ============================================================
# TEST safe_request()
# ============================================================

def test_safe_request_success():

    print("\n")
    print("=" * 70)
    print("TEST 1 - SUCCESSFUL REQUEST")
    print("=" * 70)

    original_request = lms_client.session.request

    received_timeout = None

    def fake_request(
        method,
        url,
        **kwargs
    ):

        nonlocal received_timeout

        received_timeout = kwargs.get(
            "timeout"
        )

        print(
            f"[TEST] Method: {method}"
        )

        print(
            f"[TEST] URL: {url}"
        )

        print(
            f"[TEST] Timeout: {received_timeout}"
        )

        return FakeResponse(
            status_code=200
        )

    lms_client.session.request = fake_request

    try:

        response = lms_client.safe_request(
            "GET",
            "https://example.com"
        )

    finally:

        lms_client.session.request = (
            original_request
        )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if response is not None:

        print(
            "Successful request returned response: PASSED ✅"
        )

    else:

        print(
            "Successful request returned response: FAILED ❌"
        )

        return False

    if response.status_code == 200:

        print(
            "HTTP status validation: PASSED ✅"
        )

    else:

        print(
            "HTTP status validation: FAILED ❌"
        )

        return False

    if received_timeout == TEST_TIMEOUT:

        print(
            "Request timeout validation: PASSED ✅"
        )

    else:

        print(
            "Request timeout validation: FAILED ❌"
        )

        print(
            f"Expected: {TEST_TIMEOUT}"
        )

        print(
            f"Received: {received_timeout}"
        )

        return False

    return True


# ============================================================
# TEST TIMEOUT
# ============================================================

def test_safe_request_timeout():

    print("\n")
    print("=" * 70)
    print("TEST 2 - REQUEST TIMEOUT")
    print("=" * 70)

    original_request = lms_client.session.request

    def fake_request(
        method,
        url,
        **kwargs
    ):

        print(
            "[TEST] Simulating request timeout..."
        )

        raise requests.Timeout(
            "Simulated timeout"
        )

    lms_client.session.request = fake_request

    try:

        response = lms_client.safe_request(
            "GET",
            "https://example.com"
        )

    finally:

        lms_client.session.request = (
            original_request
        )

    if response is None:

        print(
            "Timeout handled without crashing: PASSED ✅"
        )

        return True

    print(
        "Timeout handling: FAILED ❌"
    )

    return False


# ============================================================
# TEST CONNECTION ERROR
# ============================================================

def test_safe_request_connection_error():

    print("\n")
    print("=" * 70)
    print("TEST 3 - CONNECTION ERROR")
    print("=" * 70)

    original_request = lms_client.session.request

    def fake_request(
        method,
        url,
        **kwargs
    ):

        print(
            "[TEST] Simulating connection error..."
        )

        raise requests.ConnectionError(
            "Simulated connection error"
        )

    lms_client.session.request = fake_request

    try:

        response = lms_client.safe_request(
            "GET",
            "https://example.com"
        )

    finally:

        lms_client.session.request = (
            original_request
        )

    if response is None:

        print(
            "Connection error handled without crashing: PASSED ✅"
        )

        return True

    print(
        "Connection error handling: FAILED ❌"
    )

    return False


# ============================================================
# TEST GENERIC REQUEST ERROR
# ============================================================

def test_safe_request_generic_error():

    print("\n")
    print("=" * 70)
    print("TEST 4 - GENERIC REQUEST ERROR")
    print("=" * 70)

    original_request = lms_client.session.request

    def fake_request(
        method,
        url,
        **kwargs
    ):

        print(
            "[TEST] Simulating generic requests error..."
        )

        raise requests.RequestException(
            "Simulated request error"
        )

    lms_client.session.request = fake_request

    try:

        response = lms_client.safe_request(
            "GET",
            "https://example.com"
        )

    finally:

        lms_client.session.request = (
            original_request
        )

    if response is None:

        print(
            "Generic request error handled: PASSED ✅"
        )

        return True

    print(
        "Generic request error handling: FAILED ❌"
    )

    return False


# ============================================================
# TEST HTTP SERVER ERROR
# ============================================================

def test_safe_request_http_error():

    print("\n")
    print("=" * 70)
    print("TEST 5 - HTTP SERVER ERROR")
    print("=" * 70)

    original_request = lms_client.session.request

    def fake_request(
        method,
        url,
        **kwargs
    ):

        print(
            "[TEST] Simulating HTTP 500 response..."
        )

        return FakeResponse(
            status_code=500
        )

    lms_client.session.request = fake_request

    try:

        response = lms_client.safe_request(
            "GET",
            "https://example.com"
        )

    finally:

        lms_client.session.request = (
            original_request
        )

    # --------------------------------------------------------
    # IMPORTANT
    # --------------------------------------------------------
    #
    # HTTP 500 is not a requests exception.
    #
    # The request itself succeeded,
    # but the server returned an error status.
    #
    # safe_request() should return the response
    # so the calling function can decide what to do.
    # --------------------------------------------------------

    if response is not None:

        print(
            "HTTP 500 response returned correctly: PASSED ✅"
        )

    else:

        print(
            "HTTP 500 response handling: FAILED ❌"
        )

        return False

    if response.status_code == 500:

        print(
            "HTTP status preserved correctly: PASSED ✅"
        )

        return True

    print(
        "HTTP status preservation: FAILED ❌"
    )

    return False


# ============================================================
# TEST get_courses() AFTER REQUEST FAILURE
# ============================================================

def test_get_courses_timeout():

    print("\n")
    print("=" * 70)
    print("TEST 6 - get_courses() TIMEOUT")
    print("=" * 70)

    original_request = lms_client.session.request

    def fake_request(
        method,
        url,
        **kwargs
    ):

        print(
            "[TEST] Simulating timeout while loading courses..."
        )

        raise requests.Timeout(
            "Simulated courses timeout"
        )

    lms_client.session.request = fake_request

    try:

        courses = lms_client.get_courses()

    finally:

        lms_client.session.request = (
            original_request
        )

    if courses == []:

        print(
            "get_courses() returned empty list safely: PASSED ✅"
        )

        return True

    print(
        "get_courses() timeout handling: FAILED ❌"
    )

    print(
        f"Received: {courses}"
    )

    return False


# ============================================================
# RUN ALL TESTS
# ============================================================

def run_all_tests():

    print("\n")
    print("=" * 70)
    print("UNIVERSITY AI AGENT")
    print("LMS ERROR HANDLING TEST SUITE")
    print("=" * 70)

    results = []

    # --------------------------------------------------------
    # TEST 1
    # --------------------------------------------------------

    results.append(
        test_safe_request_success()
    )

    # --------------------------------------------------------
    # TEST 2
    # --------------------------------------------------------

    results.append(
        test_safe_request_timeout()
    )

    # --------------------------------------------------------
    # TEST 3
    # --------------------------------------------------------

    results.append(
        test_safe_request_connection_error()
    )

    # --------------------------------------------------------
    # TEST 4
    # --------------------------------------------------------

    results.append(
        test_safe_request_generic_error()
    )

    # --------------------------------------------------------
    # TEST 5
    # --------------------------------------------------------

    results.append(
        test_safe_request_http_error()
    )

    # --------------------------------------------------------
    # TEST 6
    # --------------------------------------------------------

    results.append(
        test_get_courses_timeout()
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    print("\n")
    print("=" * 70)
    print("FINAL TEST RESULTS")
    print("=" * 70)

    test_names = [
        "Successful request",
        "Request timeout",
        "Connection error",
        "Generic request error",
        "HTTP 500 response",
        "get_courses() timeout"
    ]

    passed = 0

    for name, result in zip(
        test_names,
        results
    ):

        if result:

            print(
                f"{name}: PASSED ✅"
            )

            passed += 1

        else:

            print(
                f"{name}: FAILED ❌"
            )

    print(
        f"\nTests passed: "
        f"{passed}/{len(results)}"
    )

    print("\n" + "=" * 70)

    if passed == len(results):

        print(
            "LMS ERROR HANDLING TEST SUITE PASSED"
        )

        print(
            "ALL TESTS PASSED ✅"
        )

    else:

        print(
            "LMS ERROR HANDLING TEST SUITE FAILED"
        )

        print(
            "SOME TESTS FAILED ❌"
        )

    print("=" * 70)

    return passed == len(results)


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    success = run_all_tests()

    if not success:

        raise SystemExit(1)
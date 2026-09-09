import lms_client


# ============================================================
# FAKE RESPONSE
# ============================================================

class FakeResponse:

    def __init__(
        self,
        status_code=200,
        url="https://elearning3.bau.edu.jo/huson/my/",
        text=""
    ):

        self.status_code = status_code
        self.url = url
        self.text = text


# ============================================================
# TEST 1 - NORMAL SESSION
# ============================================================

def test_normal_session():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 1 - NORMAL SESSION"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            print(
                "[TEST] Simulating normal authenticated request..."
            )

            return FakeResponse(
                status_code=200,
                url=lms_client.MY_COURSES_URL,
                text="<html>My Courses</html>"
            )

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = True

        response = lms_client.request_with_relogin(
            "GET",
            lms_client.MY_COURSES_URL
        )

        assert response is not None

        assert response.status_code == 200

        print(
            "Normal session request: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request


# ============================================================
# TEST 2 - SESSION EXPIRED
# ============================================================

def test_session_expired_and_relogin():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 2 - SESSION EXPIRED + AUTOMATIC RE-LOGIN"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request
    original_login = lms_client.login

    calls = []

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            calls.append(
                url
            )

            print(
                f"[TEST] Request #{len(calls)}: {url}"
            )

            # First request behaves like an expired session.
            if len(calls) == 1:

                print(
                    "[TEST] Simulating Moodle login-page redirect..."
                )

                return FakeResponse(
                    status_code=200,
                    url=lms_client.LOGIN_URL,
                    text="""
                    <html>
                        <form>
                            <input
                                name="username"
                                type="text"
                            >
                            <input
                                name="password"
                                type="password"
                            >
                        </form>
                    </html>
                    """
                )

            # Second request should happen after re-login.
            print(
                "[TEST] Simulating successful authenticated request..."
            )

            return FakeResponse(
                status_code=200,
                url=lms_client.MY_COURSES_URL,
                text="<html>My Courses</html>"
            )

        def fake_login():

            print(
                "[TEST] Simulating automatic Moodle re-login..."
            )

            lms_client._logged_in = True

            return True

        lms_client.safe_request = fake_safe_request
        lms_client.login = fake_login
        lms_client._logged_in = True

        response = lms_client.request_with_relogin(
            "GET",
            lms_client.MY_COURSES_URL
        )

        assert response is not None

        assert response.status_code == 200

        assert len(calls) == 2

        print(
            "Session expiration detected: PASSED ✅"
        )

        print(
            "Automatic re-login executed: PASSED ✅"
        )

        print(
            "Original request retried: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request
        lms_client.login = original_login


# ============================================================
# TEST 3 - RE-LOGIN FAILURE
# ============================================================

def test_relogin_failure():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 3 - RE-LOGIN FAILURE"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request
    original_login = lms_client.login

    calls = []

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            calls.append(
                url
            )

            print(
                f"[TEST] Request #{len(calls)}"
            )

            return FakeResponse(
                status_code=200,
                url=lms_client.LOGIN_URL,
                text=""
            )

        def fake_login():

            print(
                "[TEST] Simulating failed re-login..."
            )

            lms_client._logged_in = False

            return False

        lms_client.safe_request = fake_safe_request
        lms_client.login = fake_login
        lms_client._logged_in = True

        response = lms_client.request_with_relogin(
            "GET",
            lms_client.MY_COURSES_URL
        )

        assert response is None

        assert len(calls) == 1

        print(
            "Failed re-login handled safely: PASSED ✅"
        )

        print(
            "Request was not retried after failed login: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request
        lms_client.login = original_login


# ============================================================
# TEST 4 - PREVENT INFINITE RETRY
# ============================================================

def test_no_infinite_retry():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 4 - PREVENT INFINITE RETRY"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request
    original_login = lms_client.login

    calls = []
    login_calls = []

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            calls.append(
                url
            )

            print(
                f"[TEST] Request #{len(calls)}"
            )

            # Even after re-login, Moodle still returns
            # the login page.
            return FakeResponse(
                status_code=200,
                url=lms_client.LOGIN_URL,
                text=""
            )

        def fake_login():

            login_calls.append(
                True
            )

            print(
                "[TEST] Simulating successful re-login..."
            )

            lms_client._logged_in = True

            return True

        lms_client.safe_request = fake_safe_request
        lms_client.login = fake_login
        lms_client._logged_in = True

        response = lms_client.request_with_relogin(
            "GET",
            lms_client.MY_COURSES_URL
        )

        assert response is None

        # Only the original request + one retry.
        assert len(calls) == 2

        assert len(login_calls) == 1

        print(
            "Retry limit enforced: PASSED ✅"
        )

        print(
            "No infinite retry loop: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request
        lms_client.login = original_login


# ============================================================
# RUN ALL TESTS
# ============================================================

if __name__ == "__main__":

    print(
        "\n" + "=" * 70
    )

    print(
        "UNIVERSITY AI AGENT"
    )

    print(
        "LMS SESSION EXPIRATION TEST SUITE"
    )

    print(
        "=" * 70
    )

    test_normal_session()

    test_session_expired_and_relogin()

    test_relogin_failure()

    test_no_infinite_retry()

    print(
        "\n" + "=" * 70
    )

    print(
        "ALL SESSION EXPIRATION TESTS PASSED"
    )

    print(
        "=" * 70
    )
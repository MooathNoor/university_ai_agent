import lms_client


# ============================================================
# FAKE RESPONSE
# ============================================================

class FakeResponse:

    def __init__(
        self,
        status_code=200,
        url="",
        text=""
    ):

        self.status_code = status_code
        self.url = url
        self.text = text


# ============================================================
# TEST 1 - LOGIN TOKEN MISSING
# ============================================================

def test_login_token_missing():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 1 - LOGIN TOKEN MISSING"
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
                "[TEST] Simulating Moodle login page "
                "without login token..."
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

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = False

        result = lms_client.login()

        assert result is False

        print(
            "Missing login token handled safely: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request


# ============================================================
# TEST 2 - INVALID CREDENTIALS
# ============================================================

def test_invalid_credentials():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 2 - INVALID CREDENTIALS"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request

    calls = []

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            calls.append(
                method
            )

            # ----------------------------------------------
            # LOGIN PAGE
            # ----------------------------------------------

            if method == "GET":

                print(
                    "[TEST] Returning valid Moodle login page..."
                )

                return FakeResponse(
                    status_code=200,
                    url=lms_client.LOGIN_URL,
                    text="""
                    <html>
                        <form>
                            <input
                                name="logintoken"
                                value="fake-token"
                            >
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

            # ----------------------------------------------
            # FAILED LOGIN
            # ----------------------------------------------

            print(
                "[TEST] Simulating invalid username/password..."
            )

            return FakeResponse(
                status_code=200,
                url=lms_client.LOGIN_URL,
                text="""
                <html>
                    <div class="loginerrors">
                        Invalid login
                    </div>

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

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = False

        result = lms_client.login()

        assert result is False

        assert lms_client._logged_in is False

        assert len(calls) == 2

        print(
            "Invalid credentials detected safely: PASSED ✅"
        )

        print(
            "Login state remained logged out: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request


# ============================================================
# TEST 3 - SERVER ERROR DURING LOGIN
# ============================================================

def test_login_server_error():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 3 - SERVER ERROR DURING LOGIN"
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
                "[TEST] Simulating Moodle HTTP 500..."
            )

            return FakeResponse(
                status_code=500,
                url=lms_client.LOGIN_URL,
                text="Internal Server Error"
            )

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = False

        result = lms_client.login()

        assert result is False

        assert lms_client._logged_in is False

        print(
            "Login server error handled safely: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request


# ============================================================
# TEST 4 - LOGIN NETWORK FAILURE
# ============================================================

def test_login_network_failure():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 4 - LOGIN NETWORK FAILURE"
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
                "[TEST] Simulating network failure..."
            )

            return None

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = False

        result = lms_client.login()

        assert result is False

        assert lms_client._logged_in is False

        print(
            "Login network failure handled safely: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request


# ============================================================
# TEST 5 - LOGIN SUCCESS
# ============================================================

def test_login_success():

    print(
        "\n" + "=" * 70
    )

    print(
        "TEST 5 - SUCCESSFUL LOGIN"
    )

    print(
        "=" * 70
    )

    original_safe_request = lms_client.safe_request

    calls = []

    try:

        def fake_safe_request(
            method,
            url,
            **kwargs
        ):

            calls.append(
                method
            )

            # ----------------------------------------------
            # LOGIN PAGE
            # ----------------------------------------------

            if method == "GET":

                print(
                    "[TEST] Returning valid login page..."
                )

                return FakeResponse(
                    status_code=200,
                    url=lms_client.LOGIN_URL,
                    text="""
                    <html>
                        <form>
                            <input
                                name="logintoken"
                                value="fake-token"
                            >
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

            # ----------------------------------------------
            # SUCCESSFUL LOGIN
            # ----------------------------------------------

            print(
                "[TEST] Simulating successful Moodle login..."
            )

            return FakeResponse(
                status_code=200,
                url=lms_client.MY_COURSES_URL,
                text="<html>My Courses</html>"
            )

        lms_client.safe_request = fake_safe_request
        lms_client._logged_in = False

        result = lms_client.login()

        assert result is True

        assert lms_client._logged_in is True

        assert len(calls) == 2

        print(
            "Successful login detected: PASSED ✅"
        )

        print(
            "Login state updated correctly: PASSED ✅"
        )

    finally:

        lms_client.safe_request = original_safe_request
        lms_client._logged_in = False


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
        "LMS LOGIN FAILURE TEST SUITE"
    )

    print(
        "=" * 70
    )

    test_login_token_missing()

    test_invalid_credentials()

    test_login_server_error()

    test_login_network_failure()

    test_login_success()

    print(
        "\n" + "=" * 70
    )

    print(
        "ALL LOGIN FAILURE TESTS PASSED"
    )

    print(
        "=" * 70
    )
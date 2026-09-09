import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os


BASE_URL = "https://elearning3.bau.edu.jo/huson"
LOGIN_URL = f"{BASE_URL}/login/index.php"


def get_credentials():
    load_dotenv()

    username = (
        os.getenv("BAU_USERNAME")
        or os.getenv("BAU_USER")
        or os.getenv("USERNAME")
    )

    password = (
        os.getenv("BAU_PASSWORD")
        or os.getenv("BAU_PASS")
        or os.getenv("PASSWORD")
    )

    return username, password


def main():
    print("=" * 70)
    print("BAU ELEARNING3 MOODLE LOGIN TEST")
    print("=" * 70)

    username, password = get_credentials()

    if not username or not password:
        print("\n[ERROR] BAU credentials not found in .env")
        return

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        )
    })

    # ---------------------------------------------------------
    # STEP 1: Open Moodle login page
    # ---------------------------------------------------------

    print("\n[1] Opening Moodle login page...")
    print(LOGIN_URL)

    try:
        response = session.get(
            LOGIN_URL,
            timeout=20,
            allow_redirects=True
        )
    except requests.RequestException as e:
        print(f"\n[ERROR] Failed to open login page:")
        print(e)
        return

    print(f"Status: {response.status_code}")
    print(f"Final URL: {response.url}")

    if response.status_code != 200:
        print("\n[ERROR] Login page did not return HTTP 200.")
        return

    # ---------------------------------------------------------
    # STEP 2: Parse login form
    # ---------------------------------------------------------

    soup = BeautifulSoup(response.text, "html.parser")

    login_form = soup.find("form", id="login")

    if not login_form:
        print("\n[ERROR] Moodle login form not found.")
        return

    print("\n[OK] Moodle login form found.")

    # ---------------------------------------------------------
    # STEP 3: Extract hidden fields
    # ---------------------------------------------------------

    form_data = {}

    hidden_inputs = login_form.find_all(
        "input",
        type="hidden"
    )

    print("\nHidden fields:")

    for field in hidden_inputs:
        name = field.get("name")
        value = field.get("value", "")

        if name:
            form_data[name] = value

            if name == "logintoken":
                print("  logintoken: found")
            else:
                print(f"  {name}: found")

    if "logintoken" not in form_data:
        print("\n[ERROR] Moodle login token not found.")
        return

    # ---------------------------------------------------------
    # STEP 4: Add credentials
    # ---------------------------------------------------------

    form_data["username"] = username
    form_data["password"] = password

    print("\nUsername: loaded from .env")
    print("Password: loaded from .env")

    # ---------------------------------------------------------
    # STEP 5: Submit login
    # ---------------------------------------------------------

    print("\n[2] Submitting Moodle login...")

    try:
        login_response = session.post(
            LOGIN_URL,
            data=form_data,
            timeout=20,
            allow_redirects=True
        )
    except requests.RequestException as e:
        print("\n[ERROR] Login request failed:")
        print(e)
        return

    print(f"Login response status: {login_response.status_code}")
    print(f"Final URL: {login_response.url}")

    # ---------------------------------------------------------
    # STEP 6: Check login result
    # ---------------------------------------------------------

    final_url = login_response.url.lower()
    final_html = login_response.text.lower()

    print("\n" + "=" * 70)
    print("LOGIN RESULT")
    print("=" * 70)

    # Successful login usually takes us away from /login/
    if "/login/" not in final_url:
        print("\n[SUCCESS] Moodle login appears to be successful!")

        print("\nAuthenticated page:")
        print(login_response.url)

    else:
        print("\n[FAILED] Moodle still returned a login page.")

        # Try to find Moodle's error message
        error_selectors = [
            ".loginerrors",
            ".alert-danger",
            ".alert-error",
            "[role='alert']",
        ]

        error_found = False

        for selector in error_selectors:
            error_element = soup.select_one(selector)

            if error_element:
                error_text = error_element.get_text(
                    " ",
                    strip=True
                )

                if error_text:
                    print("\nMoodle message:")
                    print(error_text)

                    error_found = True
                    break

        if not error_found:
            final_soup = BeautifulSoup(
                login_response.text,
                "html.parser"
            )

            alerts = final_soup.select(
                ".alert, .loginerrors"
            )

            if alerts:
                print("\nMoodle messages:")

                for alert in alerts:
                    text = alert.get_text(
                        " ",
                        strip=True
                    )

                    if text:
                        print(text)
                        error_found = True

        if not error_found:
            print(
                "\n[INFO] No specific Moodle error message "
                "was detected."
            )

    # ---------------------------------------------------------
    # STEP 7: Show session cookies
    # ---------------------------------------------------------

    print("\nSession cookies received:")

    if session.cookies:
        for cookie in session.cookies:
            print(f"  {cookie.name}")
    else:
        print("  No cookies found.")

    # ---------------------------------------------------------
    # STEP 8: Check authenticated indicators
    # ---------------------------------------------------------

    print("\nAuthentication indicators:")

    indicators = [
        ("Dashboard URL", "/my/" in final_url),
        ("Logout link", "logout" in final_html),
        ("User menu", "usermenu" in final_html),
        ("Site home", "mycourses" in final_html),
    ]

    for name, found in indicators:
        status = "YES" if found else "NO"
        print(f"  {name}: {status}")

    print("\n" + "=" * 70)
    print("TEST FINISHED")
    print("=" * 70)


if __name__ == "__main__":
    main()
from bs4 import BeautifulSoup

from lms_client import (
    login,
    session,
    BASE_URL,
    get_courses
)


print("Testing Moodle Calendar HTML...")


if not login():
    raise SystemExit("Login failed.")


courses = get_courses()

if not courses:
    raise SystemExit("No courses found.")


selected_course = None

for course in courses:

    if "cloud computing" in course["name"].lower():
        selected_course = course
        break


if not selected_course:
    raise SystemExit("Cloud Computing course not found.")


course_id = selected_course["id"]
course_name = selected_course["name"]


print()
print("=" * 70)
print("COURSE")
print("=" * 70)
print(f"Name: {course_name}")
print(f"ID: {course_id}")


calendar_url = (
    f"{BASE_URL}/calendar/view.php"
    f"?view=month"
    f"&course={course_id}"
)


print()
print("=" * 70)
print("CALENDAR URL")
print("=" * 70)
print(calendar_url)


response = session.get(calendar_url)


print()
print("=" * 70)
print("CALENDAR RESPONSE")
print("=" * 70)
print(f"Status: {response.status_code}")
print(f"Final URL: {response.url}")


if response.status_code != 200:
    raise SystemExit("Could not open Calendar.")


soup = BeautifulSoup(
    response.text,
    "html.parser"
)


print()
print("=" * 70)
print("PAGE TITLE")
print("=" * 70)

if soup.title:
    print(soup.title.get_text(" ", strip=True))
else:
    print("No title found.")


print()
print("=" * 70)
print("ELEMENTS CONTAINING EVENT")
print("=" * 70)


elements = soup.find_all(
    string=lambda text:
        text and "event" in text.lower()
)


print(
    f"Text nodes containing 'event': "
    f"{len(elements)}"
)


for index, text in enumerate(elements[:30], start=1):

    print()
    print(f"--- Event match {index} ---")
    print(text.strip())


print()
print("=" * 70)
print("ELEMENTS WITH DATA-EVENT-ID")
print("=" * 70)


event_id_elements = soup.select(
    "[data-event-id]"
)


print(
    f"Found: "
    f"{len(event_id_elements)}"
)


for index, element in enumerate(
    event_id_elements[:30],
    start=1
):

    print()
    print(f"--- Event ID element {index} ---")
    print(
        element.prettify()[:3000]
    )


print()
print("=" * 70)
print("ELEMENTS WITH DATA-EVENTTYPE")
print("=" * 70)


event_type_elements = soup.select(
    "[data-eventtype]"
)


print(
    f"Found: "
    f"{len(event_type_elements)}"
)


for index, element in enumerate(
    event_type_elements[:30],
    start=1
):

    print()
    print(f"--- Event type element {index} ---")
    print(
        element.prettify()[:3000]
    )


print()
print("=" * 70)
print("CALENDAR EVENT CLASSES")
print("=" * 70)


for element in soup.find_all(
    class_=True
):

    classes = element.get("class", [])

    class_text = " ".join(classes).lower()

    if "calendar" in class_text or "event" in class_text:

        text = element.get_text(
            " ",
            strip=True
        )

        if text:

            print()
            print(
                f"Classes: {classes}"
            )

            print(
                f"Text: {text[:500]}"
            )


print()
print("=" * 70)
print("DONE")
print("=" * 70)
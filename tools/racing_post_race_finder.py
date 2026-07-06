import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


BASE = "https://www.racingpost.com"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def find_racing_post_races(course, date=None):
    """
    Finds Racing Post racecard links for a course/date page.

    Example:
    course = "Southwell AW"
    date = "2026-07-05"
    """

    date = date or datetime.now().strftime("%Y-%m-%d")
    course_slug = slug(course)

    url = f"{BASE}/racecards/{course_slug}/{date}"

    print(f"Trying: {url}")

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )

    print(f"Status: {response.status_code}")

    soup = BeautifulSoup(response.text, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/racecards/" not in href:
            continue

        if date not in href:
            continue

        full_url = href if href.startswith("http") else BASE + href

        text = " ".join(a.get_text(" ", strip=True).split())

        links.append({
            "text": text,
            "url": full_url,
        })

    unique = []
    seen = set()

    for item in links:
        if item["url"] in seen:
            continue

        seen.add(item["url"])
        unique.append(item)

    return unique


if __name__ == "__main__":
    course = input("Course: ").strip()
    date = input("Date YYYY-MM-DD: ").strip()

    races = find_racing_post_races(course, date)

    print()
    print(f"Found {len(races)} race links")
    print("-" * 70)

    for race in races:
        print(race["text"])
        print(race["url"])
        print()
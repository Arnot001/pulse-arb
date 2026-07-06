import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from app.modules.odds.url_builder import build_oddschecker_url


def accept_cookies(page):
    try:
        page.get_by_text("Accept all", exact=True).click(timeout=5000)
    except Exception:
        pass


course = input("Course: ").strip()
race_time = input("Race time: ").strip()
horse = input("Horse: ").strip()

url = build_oddschecker_url(course, race_time, horse)

print("Opening:")
print(url)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(url, wait_until="networkidle", timeout=60000)
    accept_cookies(page)

    print()
    print("TITLE:")
    print(page.title())

    print()
    print("VISIBLE TEXT SAMPLE:")
    print(page.locator("body").inner_text(timeout=15000)[:3000])

    input("Press ENTER to close...")
    browser.close()
from playwright.sync_api import sync_playwright


URL = "https://www.oddschecker.com/horse-racing"


with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    page.goto(
        URL,
        wait_until="networkidle",
        timeout=60000,
    )

    print(page.title())

    input("Press ENTER to close...")

    browser.close()
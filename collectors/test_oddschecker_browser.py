from playwright.sync_api import sync_playwright

URL = "https://www.oddschecker.com/horse-racing/kempton/20:15/winner"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    try:
        page.get_by_role("button", name="Accept all").click(timeout=8000)
    except Exception:
        pass

    page.wait_for_timeout(8000)

    text = page.locator("body").inner_text(timeout=10000)

    print(text[:8000])

    page.screenshot(path="oddschecker_test.png", full_page=True)

    input("Press Enter to close...")
    browser.close()
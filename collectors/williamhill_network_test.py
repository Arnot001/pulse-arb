from playwright.sync_api import sync_playwright

URL = "https://sports.williamhill.com/betting/en-gb/horse-racing"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    def log_response(response):
        url = response.url.lower()
        if any(x in url for x in ["horse", "racing", "event", "market", "price", "odds"]):
            print(response.status, response.url)

    page.on("response", log_response)

    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(15000)

    browser.close()
import json
from playwright.sync_api import sync_playwright

URL = "https://skybet.com/horse-racing/s-7"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    def log_response(response):
        if "getMarketPrices" not in response.url:
            return

        print("=" * 80)
        print(response.url)

        try:
            print(response.text())
        except Exception as exc:
            print(exc)
            
    page.on("response", log_response)

    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(20000)

    browser.close()
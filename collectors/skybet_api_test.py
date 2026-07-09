import json
from playwright.sync_api import sync_playwright

URL = "https://skybet.com/horse-racing/s-7"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    def log_response(response):
        url = response.url

        if "getMarketPrices" not in url:
            return

        try:
            data = response.json()
            print("=" * 80)
            print(response.status, url)
            print(json.dumps(data, indent=2)[:10000])
        except Exception as exc:
            print("FAILED TO READ JSON:", exc)

    page.on("response", log_response)

    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(15000)

    browser.close()
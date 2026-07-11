import re
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("data/debug/paddypower")
OUT.mkdir(parents=True, exist_ok=True)

URL = "https://www.paddypower.com/horse-racing"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    count = [0]

    def safe_name(url):
        return re.sub(r"[^a-zA-Z0-9]+", "_", url)[-120:]

    def log_response(response):
        if "content-managed-page/v7" not in response.url:
            return

        try:
            body = response.body()
        except Exception:
            return

        count[0] += 1

        file = OUT / f"pp_{count[0]}_{safe_name(response.url)}.json"
        file.write_bytes(body)

        print("SAVED:", file)
        print("BYTES:", len(body))

    page.on("response", log_response)

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(20000)

    browser.close()

print("DONE")
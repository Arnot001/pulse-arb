from playwright.sync_api import sync_playwright


URL = "https://www.oddschecker.com/horse-racing"


def accept_cookies(page):
    try:
        page.get_by_text("Accept all", exact=True).click(timeout=5000)
    except Exception:
        pass


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(URL, wait_until="networkidle", timeout=60000)
    accept_cookies(page)

    links = page.locator("a").evaluate_all("""
        els => els.map(a => ({
            text: a.innerText,
            href: a.href
        }))
    """)

    print("RACE LINKS")
    print("=" * 80)

    for link in links:
        href = link.get("href", "")
        text = (link.get("text") or "").strip()

        if "/horse-racing/" in href and "/winner" in href:
            print(text)
            print(href)
            print("-" * 80)

    input("Press ENTER to close...")
    browser.close()
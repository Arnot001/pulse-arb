from pathlib import Path

from playwright.sync_api import sync_playwright

from app.browser_manager import get_browser_manager


URL = "https://www.oddschecker.com/horse-racing"
OUTPUT_DIR = Path("data/debug/oddschecker")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def inspect_page(page, label):
    print("=" * 70)
    print(label)
    print("=" * 70)

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(12000)

    try:
        page.get_by_text(
            "Accept all",
            exact=True,
        ).click(timeout=8000)
    except Exception:
        pass

    page.wait_for_timeout(10000)

    print(f"Current URL: {page.url}")
    print(f"Title: {page.title()}")

    body_text = page.locator("body").inner_text(
        timeout=20000
    )

    links = page.locator("a").count()

    horse_links = page.locator(
        'a[href*="/horse-racing/"]'
    ).count()

    print(f"Body characters: {len(body_text)}")
    print(f"All links: {links}")
    print(f"Horse-racing links: {horse_links}")
    print()
    print("BODY PREVIEW:")
    print(body_text[:1000])

    html_path = OUTPUT_DIR / f"{label}.html"
    screenshot_path = OUTPUT_DIR / f"{label}.png"

    html_path.write_text(
        page.content(),
        encoding="utf-8",
    )

    page.screenshot(
        path=str(screenshot_path),
        full_page=True,
    )

    print()
    print(f"Saved HTML: {html_path}")
    print(f"Saved screenshot: {screenshot_path}")


def test_shared_browser():
    manager = get_browser_manager()
    page = manager.new_page(headless=False)

    try:
        inspect_page(
            page,
            "shared_browser",
        )
    finally:
        manager.close_page(page)
        manager.stop()


def test_fresh_browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000,
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/142.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            timezone_id="Europe/London",
        )

        page = context.new_page()

        try:
            inspect_page(
                page,
                "fresh_browser",
            )
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    test_shared_browser()
    test_fresh_browser()
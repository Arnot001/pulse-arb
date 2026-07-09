import re
from statistics import median
from datetime import datetime

from playwright.sync_api import sync_playwright

from app.modules.odds.url_builder import build_oddschecker_url


def fraction_to_decimal(value):
    value = str(value).strip()

    if not value:
        return None

    if "/" in value:
        left, right = value.split("/", 1)
        try:
            return round((float(left) / float(right)) + 1, 3)
        except Exception:
            return None

    try:
        return round(float(value) + 1, 3)
    except Exception:
        return None


def accept_cookies(page):
    try:
        page.get_by_text("Accept all", exact=True).click(timeout=5000)
    except Exception:
        pass


def extract_horse_row(body_text, horse):
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    horse_lower = horse.lower()

    for index, line in enumerate(lines):
        if line.lower().startswith(horse_lower):
            return " ".join(lines[index:index + 4])

    return ""


def extract_odds_from_row(row_text):
    values = re.findall(r"\b\d+/\d+\b", row_text)
    odds = []

    for value in values:
        decimal = fraction_to_decimal(value)

        if not decimal:
            continue

        if decimal < 1.2 or decimal > 51:
            continue

        odds.append({
            "fractional": value,
            "decimal": decimal,
        })

    return odds


def filter_suspicious_odds(odds):
    if len(odds) < 4:
        return odds

    decimals = [item["decimal"] for item in odds]
    mid = median(decimals)

    return [
        item for item in odds
        if item["decimal"] <= mid * 3
    ]


class OddscheckerSession:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.page = self.browser.new_page()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()

    def get_best_odds(self, course, race_time, horse):
        url = build_oddschecker_url(course, race_time, horse)
        row_text = ""

        try:
            self.page.goto(url, wait_until="networkidle", timeout=60000)
            accept_cookies(self.page)

            body_text = self.page.locator("body").inner_text(timeout=15000)
            if "you have been blocked" in body_text.lower():
                return {
                    "success": False,
                    "horse": horse,
                    "url": url,
                    "snapshot_time": datetime.now().isoformat(timespec="seconds"),
                    "best_odds": None,
                    "best_odds_decimal": None,
                    "bookmaker": None,
                    "row_text": "",
                    "error": "Oddschecker blocked by Cloudflare",
                }
            row_text = extract_horse_row(body_text, horse)

            odds = filter_suspicious_odds(
                extract_odds_from_row(row_text)
            )

        except Exception as exc:
            return {
                "success": False,
                "horse": horse,
                "url": url,
                "snapshot_time": datetime.now().isoformat(timespec="seconds"),
                "best_odds": None,
                "best_odds_decimal": None,
                "bookmaker": None,
                "row_text": row_text,
                "error": str(exc),
            }

        if not odds:
            return {
                "success": False,
                "horse": horse,
                "url": url,
                "snapshot_time": datetime.now().isoformat(timespec="seconds"),
                "best_odds": None,
                "best_odds_decimal": None,
                "bookmaker": None,
                "row_text": row_text,
                "error": "No odds found",
            }

        best = max(odds, key=lambda item: item["decimal"])

        return {
            "success": True,
            "horse": horse,
            "url": url,
            "snapshot_time": datetime.now().isoformat(timespec="seconds"),
            "best_odds": best["fractional"],
            "best_odds_decimal": best["decimal"],
            "bookmaker": "Oddschecker Best",
            "row_text": row_text,
            "error": None,
        }


def get_best_odds(course, race_time, horse, headless=False):
    with OddscheckerSession(headless=headless) as session:
        return session.get_best_odds(course, race_time, horse)


if __name__ == "__main__":
    print(get_best_odds("Ayr", "3:15", "Altareq"))
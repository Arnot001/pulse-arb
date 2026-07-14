import re
from datetime import datetime
from difflib import SequenceMatcher
from statistics import median
from typing import Optional

from playwright.sync_api import Page

from app.browser_manager import get_browser_manager
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


def normalise(value):
    value = str(value or "").lower().strip()

    for suffix in [
        "(aw)",
        "(gb)",
        "(ire)",
        "(fr)",
        "(usa)",
        "(aus)",
    ]:
        value = value.replace(suffix, "")

    for char in [
        "'",
        "’",
        "-",
        ".",
        ",",
        "(",
        ")",
        "/",
    ]:
        value = value.replace(char, " ")

    return " ".join(value.split())


def accept_cookies(page: Page):
    try:
        page.get_by_text(
            "Accept all",
            exact=True,
        ).click(timeout=5000)

    except Exception:
        pass


def is_match(line, horse):
    line_key = normalise(line)
    horse_key = normalise(horse)

    if not line_key or not horse_key:
        return False

    if line_key.startswith(horse_key):
        return True

    if horse_key in line_key[:80]:
        return True

    first_chunk = " ".join(line_key.split()[:6])

    return (
        SequenceMatcher(
            None,
            first_chunk,
            horse_key,
        ).ratio()
        >= 0.86
    )


def extract_horse_row(body_text, horse):
    lines = [
        line.strip()
        for line in body_text.splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        if is_match(line, horse):
            return " ".join(
                lines[index:index + 8]
            )

    return ""


def extract_odds_from_row(row_text):
    values = re.findall(
        r"\b\d+/\d+\b",
        row_text,
    )

    odds = []

    for value in values:
        decimal = fraction_to_decimal(value)

        if not decimal:
            continue

        if decimal < 1.2 or decimal > 101:
            continue

        odds.append(
            {
                "fractional": value,
                "decimal": decimal,
            }
        )

    return odds


def filter_suspicious_odds(odds):
    if len(odds) < 4:
        return odds

    decimals = [
        item["decimal"]
        for item in odds
    ]

    mid = median(decimals)

    return [
        item
        for item in odds
        if item["decimal"] <= mid * 3
    ]


def build_failure_result(
    horse,
    url,
    error,
    row_text="",
):
    return {
        "success": False,
        "horse": horse,
        "url": url,
        "snapshot_time": datetime.now().isoformat(
            timespec="seconds"
        ),
        "best_odds": None,
        "best_odds_decimal": None,
        "bookmaker": None,
        "row_text": row_text,
        "odds_source": "oddschecker",
        "error": error,
    }


class OddscheckerSession:
    """
    Uses the global shared Playwright browser.

    Entering the session creates a new page.
    Exiting closes only that page.

    The shared browser remains available for other collectors.
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
    ):
        self.headless = headless
        self.browser_manager = get_browser_manager()
        self.page: Optional[Page] = None

    def __enter__(self):
        self.page = self.browser_manager.new_page(
            headless=self.headless
        )

        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        self.browser_manager.close_page(
            self.page
        )

        self.page = None

    def get_best_odds(
        self,
        course,
        race_time,
        horse,
    ):
        if not self.page:
            raise RuntimeError(
                "OddscheckerSession must be opened "
                "before requesting odds."
            )

        url = build_oddschecker_url(
            course,
            race_time,
            horse,
        )

        row_text = ""

        try:
            self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=45000,
            )

            accept_cookies(self.page)

            self.page.wait_for_timeout(5000)

            body_text = self.page.locator(
                "body"
            ).inner_text(timeout=15000)

            if (
                "you have been blocked"
                in body_text.lower()
            ):
                return build_failure_result(
                    horse=horse,
                    url=url,
                    row_text="",
                    error=(
                        "Oddschecker blocked "
                        "by Cloudflare"
                    ),
                )

            row_text = extract_horse_row(
                body_text,
                horse,
            )

            odds = filter_suspicious_odds(
                extract_odds_from_row(
                    row_text
                )
            )

        except Exception as exc:
            return build_failure_result(
                horse=horse,
                url=url,
                row_text=row_text,
                error=str(exc),
            )

        if not odds:
            return build_failure_result(
                horse=horse,
                url=url,
                row_text=row_text,
                error="No odds found",
            )

        best = max(
            odds,
            key=lambda item: item["decimal"],
        )

        return {
            "success": True,
            "horse": horse,
            "url": url,
            "snapshot_time": (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
            "best_odds": best["fractional"],
            "best_odds_decimal": best["decimal"],
            "bookmaker": "Oddschecker Best",
            "row_text": row_text,
            "odds_source": "oddschecker",
            "error": None,
        }


def get_best_odds(
    course,
    race_time,
    horse,
    headless: Optional[bool] = None,
):
    with OddscheckerSession(
        headless=headless
    ) as session:
        return session.get_best_odds(
            course,
            race_time,
            horse,
        )


if __name__ == "__main__":
    print(
        get_best_odds(
            "Newmarket",
            "3:35",
            "Tenability",
        )
    )
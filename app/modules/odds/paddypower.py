import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from playwright.sync_api import sync_playwright


CACHE = {
    "loaded_at": None,
    "records": [],
}

CACHE_TTL_MINUTES = 10
DEBUG_DIR = Path("data/debug/paddypower")
PADDY_URL = "https://www.paddypower.com/horse-racing"


def normalise(value):
    value = str(value or "").lower().strip()

    for suffix in ["(aw)", "(gb)", "(ire)", "(fr)", "(usa)", "(aus)"]:
        value = value.replace(suffix, "")

    for char in ["'", "’", "-", ".", ",", "(", ")", "/"]:
        value = value.replace(char, " ")

    return " ".join(value.split())


def is_match(left, right):
    left = normalise(left)
    right = normalise(right)

    if not left or not right:
        return False

    if left == right:
        return True

    if right in left or left in right:
        return True

    return SequenceMatcher(None, left, right).ratio() >= 0.88


def fractional_from_runner(runner):
    odds = (
        runner.get("winRunnerOdds", {})
        .get("trueOdds", {})
        .get("fractionalOdds", {})
    )

    num = odds.get("numerator")
    den = odds.get("denominator")

    if num is None or den is None:
        return None

    return f"{num}/{den}"


def decimal_from_runner(runner):
    return (
        runner.get("winRunnerOdds", {})
        .get("trueOdds", {})
        .get("decimalOdds", {})
        .get("decimalOdds")
    )


def previous_prices(runner):
    prices = []

    for item in runner.get("previousWinRunnerOdds", []):
        true_odds = item.get("trueOdds", {})
        frac = true_odds.get("fractionalOdds", {})
        dec = true_odds.get("decimalOdds", {}).get("decimalOdds")

        if frac.get("numerator") is not None and frac.get("denominator") is not None:
            prices.append({
                "fractional": f"{frac.get('numerator')}/{frac.get('denominator')}",
                "decimal": dec,
            })

    return prices


def fetch_live_paddypower_data(headless=True):
    records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        def capture_response(response):
            if "content-managed-page/v7" not in response.url:
                return

            try:
                data = response.json()
            except Exception:
                return

            if data.get("attachments"):
                records.append(data)

        page.on("response", capture_response)

        page.goto(PADDY_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(15000)

        browser.close()

    return records


def load_debug_files():
    if not DEBUG_DIR.exists():
        return []

    records = []

    for file in DEBUG_DIR.glob("*.json"):
        try:
            records.append(json.loads(file.read_text(encoding="utf-8")))
        except Exception:
            pass

    return records


def load_paddypower_data(force_refresh=False):
    now = datetime.now()

    if (
        not force_refresh
        and CACHE["loaded_at"]
        and CACHE["records"]
        and now - CACHE["loaded_at"] < timedelta(minutes=CACHE_TTL_MINUTES)
    ):
        return CACHE["records"]

    try:
        records = fetch_live_paddypower_data(headless=True)
    except Exception as exc:
        print(f"Paddy Power live fetch failed: {exc}")
        records = []

    if not records:
        records = load_debug_files()

    CACHE["loaded_at"] = now
    CACHE["records"] = records

    return records


def search_records(records, course, horse):
    for data in records:
        attachments = data.get("attachments", {})
        races = attachments.get("races", {})
        markets = attachments.get("markets", {})

        for market in markets.values():
            race = races.get(market.get("raceId"), {})
            venue = race.get("venue") or market.get("venue")
            start_time = race.get("startTime") or market.get("marketTime")

            if course and venue and not is_match(venue, course):
                continue

            for runner in market.get("runners", []):
                if runner.get("runnerStatus") != "ACTIVE":
                    continue

                if not is_match(runner.get("runnerName"), horse):
                    continue

                decimal_odds = decimal_from_runner(runner)
                fractional_odds = fractional_from_runner(runner)

                if not decimal_odds or not fractional_odds:
                    continue

                return {
                    "success": True,
                    "horse": horse,
                    "matched_horse": runner.get("runnerName"),
                    "url": PADDY_URL,
                    "snapshot_time": datetime.now().isoformat(timespec="seconds"),
                    "best_odds": fractional_odds,
                    "best_odds_decimal": decimal_odds,
                    "bookmaker": "Paddy Power",
                    "odds_source": "paddypower",
                    "event_id": market.get("eventId"),
                    "race_id": market.get("raceId"),
                    "market_id": market.get("marketId"),
                    "selection_id": runner.get("selectionId"),
                    "course": venue,
                    "start_time": start_time,
                    "price_history": previous_prices(runner),
                    "error": None,
                }

    return None


def get_best_odds(course, race_time, horse, force_refresh=False):
    records = load_paddypower_data(force_refresh=force_refresh)
    result = search_records(records, course, horse)

    if result:
        return result

    return {
        "success": False,
        "horse": horse,
        "best_odds": None,
        "best_odds_decimal": None,
        "bookmaker": None,
        "odds_source": "paddypower",
        "error": "Horse not found in Paddy Power data",
    }


if __name__ == "__main__":
    print(get_best_odds("ParisLongchamp", "4:05", "Marsiho", force_refresh=True))
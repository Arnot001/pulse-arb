import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.data_store import append_jsonl


DEFAULT_INTERVAL_SECONDS = 300

TEST_URL = "https://www.oddschecker.com/horse-racing/kempton/20:15/winner"
HOME_URL = "https://www.oddschecker.com/horse-racing"

def now_utc():
    return datetime.now(timezone.utc).isoformat()

def split_jockey_form(value):
    value = clean(value)

    if not value:
        return "", ""

    i = len(value)

    while i > 0 and value[i - 1] in "0123456789-URFP":
        i -= 1

    jockey = value[:i].strip()
    recent_form = value[i:].strip()

    return jockey, recent_form

def clean(value):
    return str(value or "").strip()

def odds_to_decimal(value):
    value = clean(value).replace(" ", "")

    if not value:
        return None

    try:
        if "/" in value:
            a, b = value.split("/", 1)
            return round((float(a) / float(b)) + 1, 4)

        return round(float(value) + 1, 4)
    except Exception:
        return None


def get_latest_snapshot_for_url(url):
    live_market_dir = Path("data/horses/live_market")

    if not live_market_dir.exists():
        return None

    files = sorted(live_market_dir.glob("*.jsonl"))

    for file in reversed(files):
        with file.open("r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]

        for line in reversed(lines):
            try:
                record = json.loads(line)
            except Exception:
                continue

            if record.get("url") == url and record.get("runners"):
                return record

    return None


def compare_market(previous, current):
    if not previous:
        return current

    previous_by_horse = {
        clean(r.get("horse")).lower(): r
        for r in previous.get("runners", [])
    }

    for runner in current.get("runners", []):
        key = clean(runner.get("horse")).lower()
        old_runner = previous_by_horse.get(key)

        if not old_runner:
            runner["market_movement"] = "new_runner"
            continue

        old_decimal = old_runner.get("best_odds_decimal")
        new_decimal = runner.get("best_odds_decimal")

        if not old_decimal or not new_decimal:
            runner["market_movement"] = "unknown"
            continue

        change_pct = round(((new_decimal - old_decimal) / old_decimal) * 100, 2)

        runner["previous_best_odds"] = old_runner.get("best_odds")
        runner["previous_best_odds_decimal"] = old_decimal
        runner["movement_pct"] = change_pct

        if change_pct <= -3:
            runner["market_movement"] = "shortening"
        elif change_pct >= 3:
            runner["market_movement"] = "drifting"
        else:
            runner["market_movement"] = "stable"

    return current

def save_market_events(snapshot):
    saved = 0

    for runner in snapshot.get("runners", []):
        movement = runner.get("market_movement")

        if movement not in ("shortening", "drifting"):
            continue

        event = {
            "source": "oddschecker_browser",
            "event_type": f"market_{movement}",
            "detected_at": snapshot.get("collected_at"),
            "url": snapshot.get("url"),
            "horse": runner.get("horse"),
            "card_number": runner.get("card_number"),
            "draw": runner.get("draw"),
            "jockey": runner.get("jockey"),
            "jockey_raw": runner.get("jockey_raw"),
            "jockey_recent_form": runner.get("jockey_recent_form"),
            "market_rank": runner.get("market_rank"),
            "previous_best_odds": runner.get("previous_best_odds"),
            "previous_best_odds_decimal": runner.get("previous_best_odds_decimal"),
            "best_odds": runner.get("best_odds"),
            "best_odds_decimal": runner.get("best_odds_decimal"),
            "movement_pct": runner.get("movement_pct"),
        }

        append_jsonl(
            sport="horses",
            data_type="market_events",
            record=event,
        )

        print(
            f"MARKET EVENT | {event['event_type']} | "
            f"{event['horse']} | "
            f"{event['previous_best_odds']} -> {event['best_odds']} | "
            f"{event['movement_pct']}%"
        )

        saved += 1

    return saved


def extract_race_text(page):
    return page.locator("body").inner_text(timeout=15000)



def parse_runner_table_lines(runner_lines):
    runners = []
    i = 0
    market_rank = 1

    while i < len(runner_lines):
        position = None

        if runner_lines[i].lower().endswith(("st", "nd", "rd", "th")):
            position = runner_lines[i]
            i += 1

        if i + 3 >= len(runner_lines):
            break

        card_number = runner_lines[i]
        horse_line = runner_lines[i + 1]
        jockey_raw = runner_lines[i + 2]
        jockey, jockey_recent_form = split_jockey_form(jockey_raw)
        odds_line = runner_lines[i + 3]

        odds_list = [clean(x) for x in odds_line.split("\t") if clean(x)]

        horse = horse_line
        draw = None

        if "(" in horse_line and ")" in horse_line:
            before = horse_line.rsplit("(", 1)[0].strip()
            inside = horse_line.rsplit("(", 1)[1].replace(")", "").strip()
            horse = before
            draw = inside

        best_odds = odds_list[-1] if odds_list else None

        runners.append(
            {
            "market_rank": market_rank,
            "position": position,
            "card_number": card_number,
            "horse": horse,
            "draw": draw,
            "jockey": jockey,
            "jockey_raw": jockey_raw,
            "jockey_recent_form": jockey_recent_form,
            "odds_list": odds_list,
            "best_odds": best_odds,
            "best_odds_decimal": odds_to_decimal(best_odds),
        }
    )

        market_rank += 1
        i += 4

    return runners


def parse_visible_market_text(text, url):
    lines = [clean(line) for line in text.splitlines() if clean(line)]

    runner_lines = []
    in_table = False

    for line in lines:
        if line == "QuickBet":
            in_table = True
            continue

        if line.startswith("Non-Runners:"):
            break

        if not in_table:
            continue

        runner_lines.append(line)

    structured_runners = parse_runner_table_lines(runner_lines)

    return {
        "source": "oddschecker_browser",
        "collected_at": now_utc(),
        "url": url,
        "raw_text": text[:20000],
        "runner_table_lines": runner_lines[:500],
        "runners": structured_runners,
    }

def discover_race_urls(headless=False, limit=20):
    urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
        )

        page.goto(
            HOME_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        try:
            page.get_by_role(
                "button",
                name="Accept all",
            ).click(timeout=8000)
        except Exception:
            pass

        # Give the client-rendered race links time to appear.
        page.wait_for_timeout(10000)

        links = page.locator("a").evaluate_all(
            """
            links => links
                .map(a => a.href)
                .filter(Boolean)
                .filter(h => h.includes('/horse-racing/'))
                .filter(h => /\\/\\d{1,2}:\\d{2}(\\/|$)/.test(h))
            """
        )

        for link in links:
            clean_link = link.split("?")[0].split("#")[0].rstrip("/")

            if not clean_link.endswith("/winner"):
                clean_link += "/winner"

            if clean_link not in urls:
                urls.append(clean_link)

            if len(urls) >= limit:
                break

        print(f"Race links found on page: {len(links)}")

        browser.close()

    return urls

def collect_oddschecker_race(url=TEST_URL, headless=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        try:
            page.get_by_role("button", name="Accept all").click(timeout=8000)
        except Exception:
            pass

        page.wait_for_timeout(8000)

        text = extract_race_text(page)
        snapshot = parse_visible_market_text(text, url)
        previous_snapshot = get_latest_snapshot_for_url(url)
        snapshot = compare_market(previous_snapshot, snapshot)

        append_jsonl(
            sport="horses",
            data_type="live_market",
            record=snapshot,
        )

        market_events_saved = save_market_events(snapshot)

        print(f"Saved Oddschecker market snapshot.")
        print(f"Runner table lines: {len(snapshot['runner_table_lines'])}")
        print(f"Structured runners: {len(snapshot['runners'])}")
        print(f"Market events saved: {market_events_saved}")
        #input("Press Enter to close...")
        browser.close()

        return snapshot

def collect_all_discovered_races(headless=False, limit=10):
    urls = discover_race_urls(headless=headless, limit=limit)

    print(f"Discovered {len(urls)} race URLs.")

    saved = 0

    for url in urls:
        try:
            snapshot = collect_oddschecker_race(url=url, headless=headless)

            if snapshot.get("runners"):
                saved += 1

        except Exception as e:
            print(f"Skipped {url}: {e}")

    print(f"Saved live market snapshots for {saved}/{len(urls)} races.")
    return saved

def monitor_oddschecker_race(
    url=TEST_URL,
    interval_seconds=DEFAULT_INTERVAL_SECONDS,
    headless=False,
):
    print("Pulse Oddschecker Live Market Monitor started.")
    print(f"URL: {url}")
    print(f"Checking every {interval_seconds} seconds.")

    while True:
        try:
            collect_oddschecker_race(url=url, headless=headless)
        except KeyboardInterrupt:
            print("Pulse Oddschecker Live Market Monitor stopped.")
            break
        except Exception as e:
            print(f"Oddschecker monitor error: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    collect_all_discovered_races(
        headless=True,
        limit=10,
    )
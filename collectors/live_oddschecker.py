import json
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from app.browser_manager import get_browser_manager
from app.data_store import append_jsonl


DEFAULT_INTERVAL_SECONDS = 300

TEST_URL = (
    "https://www.oddschecker.com/"
    "horse-racing/kempton/20:15/winner"
)

HOME_URL = (
    "https://www.oddschecker.com/"
    "horse-racing"
)


def now_utc():
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value):
    return str(
        value or ""
    ).strip()


def split_jockey_form(value):
    value = clean(value)

    if not value:
        return "", ""

    i = len(value)

    while (
        i > 0
        and value[i - 1]
        in "0123456789-URFP"
    ):
        i -= 1

    jockey = value[:i].strip()
    recent_form = value[i:].strip()

    return jockey, recent_form


def odds_to_decimal(value):
    value = clean(value).replace(
        " ",
        "",
    )

    if not value:
        return None

    try:
        if "/" in value:
            a, b = value.split(
                "/",
                1,
            )

            return round(
                (float(a) / float(b)) + 1,
                4,
            )

        return round(
            float(value) + 1,
            4,
        )

    except Exception:
        return None


def accept_cookies(page: Page):
    """
    Click the Oddschecker consent button only when it is already visible.

    This avoids waiting for two long timeouts on every race page after
    consent has already been stored in the shared browser context.
    """

    selectors = [
        page.get_by_text(
            "Accept all",
            exact=True,
        ),
        page.get_by_role(
            "button",
            name="Accept all",
        ),
    ]

    for selector in selectors:
        try:
            if selector.count() == 0:
                continue

            first = selector.first

            if not first.is_visible(
                timeout=250
            ):
                continue

            first.click(
                timeout=1000
            )

            print(
                "Oddschecker cookies accepted."
            )

            return True

        except Exception:
            continue

    return False

def wait_for_oddschecker_access(
    page: Page,
    timeout_seconds=180,
):
    """
    Wait for Oddschecker to finish any Cloudflare verification.

    In visible debug mode, the user can complete the verification once.
    The same shared browser session then continues normally.
    """

    deadline = time.time() + timeout_seconds
    challenge_reported = False

    while time.time() < deadline:
        try:
            title = page.title().lower()

            body_text = page.locator("body").inner_text(
                timeout=10000
            )

            body_lower = body_text.lower()

        except Exception:
            page.wait_for_timeout(2000)
            continue

        challenge_detected = any(
            marker in title or marker in body_lower
            for marker in (
                "just a moment",
                "performing security verification",
                "verify you are human",
                "checking your browser",
            )
        )

        if not challenge_detected:
            return True

        if not challenge_reported:
            print(
                "Oddschecker security verification detected."
            )
            print(
                "Complete the verification in the browser window once."
            )
            print(
                f"Waiting up to {timeout_seconds} seconds..."
            )

            challenge_reported = True

        page.wait_for_timeout(2000)

    print(
        "Oddschecker verification was not completed "
        f"within {timeout_seconds} seconds."
    )

    return False

def get_latest_snapshot_for_url(url):
    live_market_dir = Path(
        "data/horses/live_market"
    )

    if not live_market_dir.exists():
        return None

    files = sorted(
        live_market_dir.glob(
            "*.jsonl"
        )
    )

    for file in reversed(files):
        with file.open(
            "r",
            encoding="utf-8",
        ) as file_handle:
            lines = [
                line
                for line in file_handle
                if line.strip()
            ]

        for line in reversed(lines):
            try:
                record = json.loads(
                    line
                )

            except Exception:
                continue

            if (
                record.get("url") == url
                and record.get("runners")
            ):
                return record

    return None


def compare_market(
    previous,
    current,
):
    if not previous:
        return current

    previous_by_horse = {
        clean(
            runner.get("horse")
        ).lower(): runner
        for runner in previous.get(
            "runners",
            [],
        )
    }

    for runner in current.get(
        "runners",
        [],
    ):
        key = clean(
            runner.get("horse")
        ).lower()

        old_runner = (
            previous_by_horse.get(
                key
            )
        )

        if not old_runner:
            runner[
                "market_movement"
            ] = "new_runner"

            continue

        old_decimal = (
            old_runner.get(
                "best_odds_decimal"
            )
        )

        new_decimal = (
            runner.get(
                "best_odds_decimal"
            )
        )

        if (
            not old_decimal
            or not new_decimal
        ):
            runner[
                "market_movement"
            ] = "unknown"

            continue

        change_pct = round(
            (
                (
                    new_decimal
                    - old_decimal
                )
                / old_decimal
            )
            * 100,
            2,
        )

        runner[
            "previous_best_odds"
        ] = old_runner.get(
            "best_odds"
        )

        runner[
            "previous_best_odds_decimal"
        ] = old_decimal

        runner[
            "movement_pct"
        ] = change_pct

        if change_pct <= -3:
            runner[
                "market_movement"
            ] = "shortening"

        elif change_pct >= 3:
            runner[
                "market_movement"
            ] = "drifting"

        else:
            runner[
                "market_movement"
            ] = "stable"

    return current


def save_market_events(
    snapshot,
):
    saved = 0

    for runner in snapshot.get(
        "runners",
        [],
    ):
        movement = runner.get(
            "market_movement"
        )

        if movement not in (
            "shortening",
            "drifting",
        ):
            continue

        event = {
            "source": (
                "oddschecker_browser"
            ),
            "event_type": (
                f"market_{movement}"
            ),
            "detected_at": (
                snapshot.get(
                    "collected_at"
                )
            ),
            "url": snapshot.get(
                "url"
            ),
            "horse": runner.get(
                "horse"
            ),
            "card_number": (
                runner.get(
                    "card_number"
                )
            ),
            "draw": runner.get(
                "draw"
            ),
            "jockey": runner.get(
                "jockey"
            ),
            "jockey_raw": (
                runner.get(
                    "jockey_raw"
                )
            ),
            "jockey_recent_form": (
                runner.get(
                    "jockey_recent_form"
                )
            ),
            "market_rank": (
                runner.get(
                    "market_rank"
                )
            ),
            "previous_best_odds": (
                runner.get(
                    "previous_best_odds"
                )
            ),
            "previous_best_odds_decimal": (
                runner.get(
                    "previous_best_odds_decimal"
                )
            ),
            "best_odds": (
                runner.get(
                    "best_odds"
                )
            ),
            "best_odds_decimal": (
                runner.get(
                    "best_odds_decimal"
                )
            ),
            "movement_pct": (
                runner.get(
                    "movement_pct"
                )
            ),
        }

        append_jsonl(
            sport="horses",
            data_type=(
                "market_events"
            ),
            record=event,
        )

        print(
            "MARKET EVENT | "
            f"{event['event_type']} | "
            f"{event['horse']} | "
            f"{event['previous_best_odds']} "
            "-> "
            f"{event['best_odds']} | "
            f"{event['movement_pct']}%"
        )

        saved += 1

    return saved


def extract_race_text(
    page: Page,
):
    return page.locator(
        "body"
    ).inner_text(
        timeout=15000
    )


def parse_runner_table_lines(
    runner_lines,
):
    runners = []
    i = 0
    market_rank = 1

    fractional_pattern = re.compile(
        r"\b\d+/\d+\b"
    )

    while i < len(runner_lines):
        position = None
        current_line = clean(
            runner_lines[i]
        )

        if current_line.lower().endswith(
            (
                "st",
                "nd",
                "rd",
                "th",
            )
        ):
            position = current_line
            i += 1

        if i + 3 >= len(runner_lines):
            break

        card_number = clean(
            runner_lines[i]
        )

        horse_line = clean(
            runner_lines[i + 1]
        )

        jockey_raw = clean(
            runner_lines[i + 2]
        )

        odds_line = clean(
            runner_lines[i + 3]
        )

        # Genuine runner rows begin with a numeric card number.
        if not re.fullmatch(
            r"\d+[A-Za-z]?",
            card_number,
        ):
            i += 1
            continue

        # Genuine odds rows must contain at least one fractional price.
        if not fractional_pattern.search(
            odds_line
        ):
            i += 1
            continue

        # Reject obvious footer/navigation content.
        if horse_line.lower() in {
            "horse racing",
            "football",
            "betting offers",
            "popular sports",
            "free bets",
            "help",
            "feedback",
        }:
            i += 1
            continue

        jockey, jockey_recent_form = (
            split_jockey_form(
                jockey_raw
            )
        )

        odds_list = [
            clean(value)
            for value in odds_line.split("\t")
            if clean(value)
            and fractional_pattern.search(
                clean(value)
            )
        ]

        if not odds_list:
            i += 1
            continue

        horse = horse_line
        draw = None

        if (
            "(" in horse_line
            and ")" in horse_line
        ):
            before = horse_line.rsplit(
                "(",
                1,
            )[0].strip()

            inside = (
                horse_line.rsplit(
                    "(",
                    1,
                )[1]
                .replace(
                    ")",
                    "",
                )
                .strip()
            )

            horse = before
            draw = inside

        best_odds = odds_list[-1]

        runners.append(
            {
                "market_rank": market_rank,
                "position": position,
                "card_number": card_number,
                "horse": horse,
                "draw": draw,
                "jockey": jockey,
                "jockey_raw": jockey_raw,
                "jockey_recent_form": (
                    jockey_recent_form
                ),
                "odds_list": odds_list,
                "best_odds": best_odds,
                "best_odds_decimal": (
                    odds_to_decimal(
                        best_odds
                    )
                ),
            }
        )

        market_rank += 1
        i += 4

    return runners


def parse_visible_market_text(
    text,
    url,
):
    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    runner_lines = []
    in_table = False

    stop_markers = (
        "Non-Runners:",
        "Race Result",
        "Related Markets",
        "Betting Offers",
        "Horse Racing Betting",
        "Popular Sports",
        "Safer Gambling",
        "Terms & Conditions",
        "Oddschecker Ltd",
    )

    for line in lines:
        if line == "QuickBet":
            if not in_table:
                in_table = True
            continue

        if not in_table:
            continue

        if line.startswith(
            stop_markers
        ):
            break

        runner_lines.append(
            line
        )

    structured_runners = (
        parse_runner_table_lines(
            runner_lines
        )
    )

    return {
        "source": "oddschecker_browser",
        "collected_at": now_utc(),
        "url": url,
        "raw_text": text[:20000],
        "runner_table_lines": (
            runner_lines[:500]
        ),
        "runners": structured_runners,
    }

def race_url_is_current(
    url,
    grace_minutes=10,
):
    """
    Return True when the race time in an Oddschecker URL is still
    upcoming or has started within the configured grace period.

    Oddschecker is being viewed in Europe/London time, so URL times are
    compared against the current UK time.
    """

    match = re.search(
        r"/(\d{1,2}):(\d{2})/winner(?:$|\?)",
        url,
        flags=re.IGNORECASE,
    )

    if not match:
        return False

    race_hour = int(match.group(1))
    race_minute = int(match.group(2))

    uk_timezone = ZoneInfo("Europe/London")
    now_uk = datetime.now(uk_timezone)

    race_datetime = now_uk.replace(
        hour=race_hour,
        minute=race_minute,
        second=0,
        microsecond=0,
    )

    cutoff = now_uk - timedelta(
        minutes=grace_minutes
    )

    return race_datetime >= cutoff

def discover_race_urls(
    headless: Optional[bool] = None,
    limit=20,
):
    urls = []
    skipped_past = 0

    browser_manager = get_browser_manager()

    page = browser_manager.new_page(
        headless=headless
    )

    try:
        page.goto(
            HOME_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(5000)

        if not wait_for_oddschecker_access(
            page,
            timeout_seconds=180,
        ):
            return []

        accept_cookies(page)

        try:
            page.wait_for_function(
                """
                () => document.querySelectorAll(
                    'a[href*="/horse-racing/"]'
                ).length > 100
                """,
                timeout=30000,
            )
        except Exception:
            print(
                "Timed out waiting for Oddschecker "
                "race links to populate."
            )

        page.wait_for_timeout(1000)

        body_text = page.locator(
            "body"
        ).inner_text(timeout=20000)

        if "you have been blocked" in body_text.lower():
            print(
                "Oddschecker blocked the discovery browser."
            )
            return []

        # Collect links only from the UK & Ireland section.
        section_links = page.evaluate(
            """
            () => {
                const elements = Array.from(
                    document.querySelectorAll("body *")
                );

                const startIndex = elements.findIndex(
                    element =>
                        (element.innerText || "").trim()
                        === "UK & Ireland Horse Racing"
                );

                const endIndex = elements.findIndex(
                    (element, index) =>
                        index > startIndex &&
                        (element.innerText || "").trim()
                        === "International Horse Racing"
                );

                if (startIndex === -1) {
                    return [];
                }

                const stopIndex = (
                    endIndex === -1
                    ? elements.length
                    : endIndex
                );

                const results = [];
                const seen = new Set();

                for (
                    let index = startIndex;
                    index < stopIndex;
                    index += 1
                ) {
                    const element = elements[index];

                    if (
                        element.tagName !== "A" ||
                        !element.href.includes(
                            "/horse-racing/"
                        )
                    ) {
                        continue;
                    }

                    const href = element.href || "";

                    if (seen.has(href)) {
                        continue;
                    }

                    seen.add(href);

                    results.push({
                        href,
                        text: (
                            element.innerText || ""
                        ).trim(),
                    });
                }

                return results;
            }
            """
        )

        print(
            "UK & Ireland horse-racing links found: "
            f"{len(section_links)}"
        )

        for item in section_links:
            link = clean(
                item.get("href", "")
            )

            text = clean(
                item.get("text", "")
            )

            if not re.search(
                r"/\d{1,2}:\d{2}/winner(?:$|\?)",
                link,
                flags=re.IGNORECASE,
            ):
                continue

            clean_link = (
                link.split("?")[0]
                .split("#")[0]
                .rstrip("/")
            )

            # Skip tomorrow/future countdown cards.
            if text.lower().startswith("in "):
                continue

            # Skip completed UK/Irish races.
            if not race_url_is_current(
                clean_link,
                grace_minutes=10,
            ):
                skipped_past += 1
                continue

            if clean_link not in urls:
                urls.append(clean_link)

            if len(urls) >= limit:
                break

        print(
            f"Past UK/Irish race links skipped: "
            f"{skipped_past}"
        )

        print(
            f"Usable current UK/Irish race links: "
            f"{len(urls)}"
        )

        return urls

    finally:
        browser_manager.close_page(page)

def collect_oddschecker_race_with_page(
    page: Page,
    url=TEST_URL,
):
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    accept_cookies(page)

    if not wait_for_oddschecker_access(
        page,
        timeout_seconds=180,
    ):
        raise RuntimeError(
            "Oddschecker access verification did not complete."
        )

    try:
        page.wait_for_function(
            """
            () => {
                const body = document.body.innerText;

                const hasQuickBet =
                    body.includes("QuickBet");

                const hasFractionalOdds =
                    /\\b\\d+\\/\\d+\\b/.test(body);

                return (
                    hasQuickBet &&
                    hasFractionalOdds
                );
            }
            """,
            timeout=4000,
        )
    except Exception:
        pass

    page.wait_for_timeout(250)

    text = extract_race_text(page)

    snapshot = parse_visible_market_text(
        text,
        url,
    )

    runner_count = len(
        snapshot.get(
            "runners",
            [],
        )
    )

    if runner_count == 0:
        raise RuntimeError(
            "No runners parsed."
        )

    if runner_count > 30:
        raise RuntimeError(
            f"Impossible runner count: {runner_count}"
        )

    previous_snapshot = get_latest_snapshot_for_url(
        url
    )

    snapshot = compare_market(
        previous_snapshot,
        snapshot,
    )

    append_jsonl(
        sport="horses",
        data_type="live_market",
        record=snapshot,
    )

    market_events_saved = save_market_events(
        snapshot
    )

    print(
        "Saved Oddschecker market snapshot."
    )
    print(
        "Runner table lines: "
        f"{len(snapshot['runner_table_lines'])}"
    )
    print(
        "Structured runners: "
        f"{len(snapshot['runners'])}"
    )
    print(
        "Market events saved: "
        f"{market_events_saved}"
    )

    return snapshot

def collect_all_discovered_races(
    headless: Optional[bool] = None,
    limit=10,
):
    urls = discover_race_urls(
        headless=headless,
        limit=limit,
    )

    print(
        f"Discovered {len(urls)} race URLs."
    )

    if not urls:
        return {
            "discovered": 0,
            "saved": 0,
        }

    browser_manager = get_browser_manager()

    page = browser_manager.new_page(
        headless=headless
    )

    saved = 0
    failed = 0

    try:
        for index, url in enumerate(
            urls,
            start=1,
        ):
            print(
                f"Collecting race "
                f"{index}/{len(urls)} | "
                f"{url}"
            )

            snapshot = None
            last_error = None

            for attempt in range(1, 4):
                try:
                    snapshot = (
                        collect_oddschecker_race_with_page(
                            page=page,
                            url=url,
                        )
                    )

                    break

                except Exception as exc:
                    last_error = exc

                    print(
                        f"Attempt {attempt}/3 failed | "
                        f"{url} | "
                        f"{exc}"
                    )

                    try:
                        page.goto(
                            "about:blank",
                            wait_until="domcontentloaded",
                            timeout=10000,
                        )
                    except Exception:
                        pass

                    if attempt < 3:
                        page.wait_for_timeout(
                            500
                        )

            if (
                snapshot
                and snapshot.get("runners")
            ):
                saved += 1

            else:
                failed += 1

                print(
                    "FAILED AFTER 3 ATTEMPTS | "
                    f"{url} | "
                    f"{last_error}"
                )

    finally:
        browser_manager.close_page(
            page
        )

    print(
        "Saved live market snapshots for "
        f"{saved}/{len(urls)} races."
    )

    if failed:
        print(
            f"Failed races: {failed}"
        )

    return {
        "discovered": len(urls),
        "saved": saved,
        "failed": failed,
    }

def monitor_all_discovered_races(
    interval_seconds=DEFAULT_INTERVAL_SECONDS,
    headless: Optional[bool] = None,
    limit=20,
):
    """
    Keep one shared Playwright browser alive and repeatedly collect
    every discovered Oddschecker race.

    Scans target a start-to-start cadence. If a scan takes longer than
    the configured interval, the next scan starts immediately.
    """

    browser_manager = get_browser_manager()
    browser_manager.start(
        headless=headless
    )

    scan_number = 0

    print("=" * 70)
    print("PULSE ODDSCHECKER MARKET MONITOR STARTED")
    print("=" * 70)
    print(f"Target interval: {interval_seconds} seconds")
    print(f"Race limit per scan: {limit}")
    print("Browser will remain alive between scans.")
    print("Press Ctrl+C to stop.")
    print("=" * 70)

    try:
        while True:
            scan_number += 1
            scan_started = datetime.now()
            scan_started_monotonic = time.monotonic()

            print()
            print("=" * 70)
            print(f"MARKET SCAN #{scan_number}")
            print(
                "Started: "
                f"{scan_started.isoformat(timespec='seconds')}"
            )
            print("=" * 70)

            result = {
                "discovered": 0,
                "saved": 0,
            }

            try:
                result = collect_all_discovered_races(
                    headless=headless,
                    limit=limit,
                )
            except Exception as exc:
                print(
                    f"Market scan #{scan_number} failed: {exc}"
                )

            elapsed_seconds = (
                time.monotonic() - scan_started_monotonic
            )

            sleep_seconds = max(
                0.0,
                interval_seconds - elapsed_seconds,
            )

            next_scan_time = datetime.fromtimestamp(
                time.time() + sleep_seconds
            )

            print()
            print(
                f"Scan #{scan_number} complete | "
                f"Discovered: {result['discovered']} | "
                f"Saved: {result['saved']} | "
                f"Duration: {elapsed_seconds:.1f}s"
            )

            if sleep_seconds > 0:
                print(
                    f"Sleeping: {sleep_seconds:.1f}s | "
                    "Next scan: "
                    f"{next_scan_time.isoformat(timespec='seconds')}"
                )
            else:
                print(
                    "Scan exceeded the target interval; "
                    "starting the next scan immediately."
                )

            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print("PULSE ODDSCHECKER MARKET MONITOR STOPPED")
        print("=" * 70)

    finally:
        browser_manager.stop()

def monitor_oddschecker_race(
    url=TEST_URL,
    interval_seconds=(
        DEFAULT_INTERVAL_SECONDS
    ),
    headless: Optional[bool] = None,
):
    browser_manager = (
        get_browser_manager()
    )

    browser_manager.start(
        headless=headless
    )

    print(
        "Pulse Oddschecker Live "
        "Market Monitor started."
    )

    print(
        f"URL: {url}"
    )

    print(
        "Checking every "
        f"{interval_seconds} seconds."
    )

    while True:
        try:
            collect_oddschecker_race(
                url=url,
                headless=headless,
            )

        except KeyboardInterrupt:
            print(
                "Pulse Oddschecker Live "
                "Market Monitor stopped."
            )

            break

        except Exception as exc:
            print(
                "Oddschecker monitor "
                f"error: {exc}"
            )

        time.sleep(
            interval_seconds
        )


if __name__ == "__main__":
    monitor_all_discovered_races(
        interval_seconds=DEFAULT_INTERVAL_SECONDS,
        headless=None,
        limit=20,
    )

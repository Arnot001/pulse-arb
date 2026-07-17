import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import Page

from app.browser_manager import get_browser_manager
from app.data_store import append_jsonl
from app.modules.market.analytics import analyse_market


DEFAULT_INTERVAL_SECONDS = 300

TEST_URL = (
    "https://www.oddschecker.com/"
    "horse-racing/kempton/20:15/winner"
)

HOME_URL = (
    "https://www.oddschecker.com/"
    "horse-racing"
)

EXCHANGE_BOOKMAKER_CODES = {
    "BF",
    "MA",
    "MB",
    "SM",
    "BFX",
}


def now_utc():
    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value):
    return str(
        value or ""
    ).strip()


def odds_to_decimal(value):
    value = clean(value).replace(
        " ",
        "",
    )

    if not value:
        return None

    upper_value = value.upper()

    if upper_value in {
        "SP",
        "N/A",
        "NA",
        "-",
    }:
        return None

    if upper_value in {
        "EVS",
        "EVENS",
        "EVEN",
    }:
        return 2.0

    try:
        if "/" in value:
            numerator, denominator = value.split(
                "/",
                1,
            )

            return round(
                (
                    float(numerator)
                    / float(denominator)
                )
                + 1,
                4,
            )

        return round(
            float(value),
            4,
        )

    except Exception:
        return None


def normalize_bookmaker_name(value):
    value = clean(value)

    aliases = {
        "B3": "Bet365",
        "B365": "Bet365",
        "WH": "William Hill",
        "UN": "Unibet",
        "FR": "Betfred",
        "SX": "Spreadex",
        "LD": "Ladbrokes",
        "LB": "Ladbrokes",
        "VC": "BetVictor",
        "KN": "BetMGM",
        "BY": "Boylesports",
        "OE": "10Bet",
        "S6": "Star Sports",
        "PUP": "Virgin Bet",
        "SI": "Betway",
        "G5": "Grosvenor Sport",
        "VE": "VBet",
        "QN": "QuinnBet",
        "WA": "BetGoodwin",
        "CE": "Coral",
        "BAH": "Bet At Home",
        "BTT": "BetTUK",
        "BRS": "BetRivers",
        "SK": "Sky Bet",
        "PP": "Paddy Power",
        "AKB": "AK Bets",
        "BF": "Betfair Exchange",
        "BFX": "Betfair Exchange",
        "MA": "Matchbook",
        "MB": "Matchbook",
        "SM": "Smarkets",
    }

    return aliases.get(
        value.upper(),
        value,
    )


def bookmaker_market_type(
    bookmaker_code,
):
    if clean(bookmaker_code).upper() in (
        EXCHANGE_BOOKMAKER_CODES
    ):
        return "exchange"

    return "sportsbook"


def summarize_prices(
    prices,
    market_type=None,
):
    valid_prices = [
        price
        for price in prices
        if price.get("decimal")
        and (
            market_type is None
            or price.get("market_type")
            == market_type
        )
    ]

    if not valid_prices:
        return {
            "best_price": None,
            "worst_price": None,
            "average_decimal": None,
            "bookmaker_count": 0,
        }

    best_price = max(
        valid_prices,
        key=lambda price: price["decimal"],
    )

    worst_price = min(
        valid_prices,
        key=lambda price: price["decimal"],
    )

    average_decimal = round(
        sum(
            price["decimal"]
            for price in valid_prices
        )
        / len(valid_prices),
        4,
    )

    return {
        "best_price": best_price,
        "worst_price": worst_price,
        "average_decimal": average_decimal,
        "bookmaker_count": len(
            valid_prices
        ),
    }


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

    deadline = (
        time.time()
        + timeout_seconds
    )

    challenge_reported = False

    while time.time() < deadline:
        try:
            title = page.title().lower()

            body_text = page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            body_lower = (
                body_text.lower()
            )

        except Exception:
            page.wait_for_timeout(
                2000
            )
            continue

        challenge_detected = any(
            marker in title
            or marker in body_lower
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

        page.wait_for_timeout(
            2000
        )

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
            "best_bookmaker": (
                runner.get(
                    "best_bookmaker"
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


def extract_race_dom(
    page: Page,
):
    """
    Read the rendered Oddschecker comparison table directly.

    Runner names, bookmaker codes, fractional odds and decimal odds are
    taken from DOM data attributes. This avoids parsing flattened page
    text, which previously produced malformed prices such as 142/25
    being split into unrelated numbers.
    """

    return page.evaluate(
        """
        () => {
            const rows = Array.from(
                document.querySelectorAll(
                    'tr.diff-row.evTabRow[data-bname][data-bid]'
                )
            );

            return rows.map((row) => {
                const runnerName = (
                    row.getAttribute('data-bname')
                    || row.querySelector(
                        'a.selTxt[data-name]'
                    )?.getAttribute('data-name')
                    || row.querySelector(
                        'a.selTxt'
                    )?.textContent
                    || ''
                ).trim();

                const jockeyNode = row.querySelector(
                    '.bottom-row.jockey'
                );

                let jockey = '';

                if (jockeyNode) {
                    const clone = jockeyNode.cloneNode(true);

                    clone.querySelectorAll(
                        '.current-form'
                    ).forEach(
                        (node) => node.remove()
                    );

                    jockey = (
                        clone.textContent
                        || ''
                    ).trim();
                }

                const currentForm = (
                    row.querySelector(
                        '.bottom-row.jockey .current-form'
                    )?.textContent
                    || ''
                ).trim();

                const cardNumber = (
                    row.querySelector(
                        'td.cardnum'
                    )?.textContent
                    || ''
                ).trim();

                const prices = Array.from(
                    row.querySelectorAll(
                        'td[data-bk][data-o][data-odig]'
                    )
                ).map((cell) => ({
                    bookmaker_code: (
                        cell.getAttribute(
                            'data-bk'
                        )
                        || ''
                    ).trim(),
                    odds: (
                        cell.getAttribute(
                            'data-o'
                        )
                        || ''
                    ).trim(),
                    decimal: (
                        cell.getAttribute(
                            'data-odig'
                        )
                        || ''
                    ).trim(),
                    opening_decimal: (
                        cell.getAttribute(
                            'data-fodds'
                        )
                        || ''
                    ).trim(),
                    best_each_way: (
                        cell.getAttribute(
                            'data-best-ew'
                        )
                        || ''
                    ).trim(),
                    best_win_only: (
                        cell.getAttribute(
                            'data-best-wo'
                        )
                        || ''
                    ).trim(),
                    each_way_denominator: (
                        cell.getAttribute(
                            'data-ew-denom'
                        )
                        || ''
                    ).trim(),
                    each_way_places: (
                        cell.getAttribute(
                            'data-ew-places'
                        )
                        || ''
                    ).trim(),
                    exchange_selection: (
                        cell.getAttribute(
                            'data-x-selection'
                        )
                        || ''
                    ).trim(),
                }));

                return {
                    runner_id: (
                        row.getAttribute(
                            'data-bid'
                        )
                        || ''
                    ).trim(),
                    market_rank: (
                        row.getAttribute(
                            'data-hcap-sort'
                        )
                        || ''
                    ).trim(),
                    horse: runnerName,
                    card_number: cardNumber,
                    draw: (
                        row.getAttribute(
                            'data-stall'
                        )
                        || ''
                    ).trim(),
                    handicap: (
                        row.getAttribute(
                            'data-hcap'
                        )
                        || ''
                    ).trim(),
                    jockey,
                    jockey_recent_form: currentForm,
                    best_bookmaker_codes: (
                        row.getAttribute(
                            'data-best-bks'
                        )
                        || ''
                    ).trim(),
                    best_sportsbook_decimal: (
                        row.getAttribute(
                            'data-best-dig'
                        )
                        || ''
                    ).trim(),
                    best_exchange_decimal: (
                        row.getAttribute(
                            'data-best-dig-wo'
                        )
                        || ''
                    ).trim(),
                    prices,
                };
            });
        }
        """
    )


def parse_dom_market(
    dom_rows,
    url,
):
    runners = []

    for fallback_rank, raw_runner in enumerate(
        dom_rows,
        start=1,
    ):
        horse = clean(
            raw_runner.get("horse")
        )

        if not horse:
            continue

        prices = []

        for raw_price in raw_runner.get(
            "prices",
            [],
        ):
            bookmaker_code = clean(
                raw_price.get(
                    "bookmaker_code"
                )
            ).upper()

            fractional_odds = clean(
                raw_price.get("odds")
            ).replace(
                " ",
                "",
            )

            if (
                not bookmaker_code
                or not fractional_odds
                or fractional_odds.upper()
                == "SP"
            ):
                continue

            decimal_odds = None

            try:
                decimal_odds = float(
                    raw_price.get(
                        "decimal"
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                decimal_odds = (
                    odds_to_decimal(
                        fractional_odds
                    )
                )

            if (
                not decimal_odds
                or decimal_odds <= 1
            ):
                continue

            opening_decimal = None

            try:
                opening_decimal = float(
                    raw_price.get(
                        "opening_decimal"
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                opening_decimal = None

            market_type = (
                bookmaker_market_type(
                    bookmaker_code
                )
            )

            prices.append(
                {
                    "bookmaker_code": (
                        bookmaker_code
                    ),
                    "bookmaker": (
                        normalize_bookmaker_name(
                            bookmaker_code
                        )
                    ),
                    "market_type": (
                        market_type
                    ),
                    "odds": (
                        fractional_odds
                    ),
                    "decimal": round(
                        decimal_odds,
                        4,
                    ),
                    "implied_probability": round(
                        1 / decimal_odds,
                        6,
                    ),
                    "opening_decimal": (
                        round(
                            opening_decimal,
                            4,
                        )
                        if opening_decimal
                        else None
                    ),
                    "best_each_way": (
                        clean(
                            raw_price.get(
                                "best_each_way"
                            )
                        ).lower()
                        == "true"
                    ),
                    "best_win_only": (
                        clean(
                            raw_price.get(
                                "best_win_only"
                            )
                        ).lower()
                        == "true"
                    ),
                    "each_way_denominator": (
                        clean(
                            raw_price.get(
                                "each_way_denominator"
                            )
                        )
                        or None
                    ),
                    "each_way_places": (
                        clean(
                            raw_price.get(
                                "each_way_places"
                            )
                        )
                        or None
                    ),
                    "exchange_selection": (
                        clean(
                            raw_price.get(
                                "exchange_selection"
                            )
                        )
                        or None
                    ),
                }
            )

        sportsbook_summary = (
            summarize_prices(
                prices,
                market_type="sportsbook",
            )
        )

        exchange_summary = (
            summarize_prices(
                prices,
                market_type="exchange",
            )
        )

        all_summary = (
            summarize_prices(
                prices
            )
        )

        best_price = (
            sportsbook_summary.get(
                "best_price"
            )
            or all_summary.get(
                "best_price"
            )
        )

        worst_price = (
            sportsbook_summary.get(
                "worst_price"
            )
            or all_summary.get(
                "worst_price"
            )
        )

        exchange_best = (
            exchange_summary.get(
                "best_price"
            )
        )

        market_rank_value = clean(
            raw_runner.get(
                "market_rank"
            )
        )

        try:
            market_rank = int(
                market_rank_value
            )
        except (
            TypeError,
            ValueError,
        ):
            market_rank = fallback_rank

        runners.append(
            {
                "runner_id": clean(
                    raw_runner.get(
                        "runner_id"
                    )
                ),
                "market_rank": (
                    market_rank
                ),
                "position": None,
                "card_number": clean(
                    raw_runner.get(
                        "card_number"
                    )
                ),
                "horse": horse,
                "draw": (
                    clean(
                        raw_runner.get(
                            "draw"
                        )
                    )
                    or None
                ),
                "handicap": (
                    clean(
                        raw_runner.get(
                            "handicap"
                        )
                    )
                    or None
                ),
                "jockey": clean(
                    raw_runner.get(
                        "jockey"
                    )
                ),
                "jockey_recent_form": (
                    clean(
                        raw_runner.get(
                            "jockey_recent_form"
                        )
                    )
                    or None
                ),
                "prices": prices,
                "sportsbook_count": (
                    sportsbook_summary.get(
                        "bookmaker_count",
                        0,
                    )
                ),
                "exchange_count": (
                    exchange_summary.get(
                        "bookmaker_count",
                        0,
                    )
                ),
                "bookmaker_count": (
                    all_summary.get(
                        "bookmaker_count",
                        0,
                    )
                ),
                "odds_list": [
                    price.get("odds")
                    for price in prices
                ],
                "best_bookmaker": (
                    best_price.get(
                        "bookmaker"
                    )
                    if best_price
                    else None
                ),
                "best_bookmaker_code": (
                    best_price.get(
                        "bookmaker_code"
                    )
                    if best_price
                    else None
                ),
                "best_odds": (
                    best_price.get(
                        "odds"
                    )
                    if best_price
                    else None
                ),
                "best_odds_decimal": (
                    best_price.get(
                        "decimal"
                    )
                    if best_price
                    else None
                ),
                "worst_bookmaker": (
                    worst_price.get(
                        "bookmaker"
                    )
                    if worst_price
                    else None
                ),
                "worst_odds": (
                    worst_price.get(
                        "odds"
                    )
                    if worst_price
                    else None
                ),
                "worst_odds_decimal": (
                    worst_price.get(
                        "decimal"
                    )
                    if worst_price
                    else None
                ),
                "average_odds_decimal": (
                    sportsbook_summary.get(
                        "average_decimal"
                    )
                    or all_summary.get(
                        "average_decimal"
                    )
                ),
                "best_exchange": (
                    exchange_best.get(
                        "bookmaker"
                    )
                    if exchange_best
                    else None
                ),
                "best_exchange_odds": (
                    exchange_best.get(
                        "odds"
                    )
                    if exchange_best
                    else None
                ),
                "best_exchange_decimal": (
                    exchange_best.get(
                        "decimal"
                    )
                    if exchange_best
                    else None
                ),
                "oddschecker_best_bookmaker_codes": [
                    normalize_bookmaker_name(
                        code
                    )
                    for code in clean(
                        raw_runner.get(
                            "best_bookmaker_codes"
                        )
                    ).split(",")
                    if clean(code)
                ],
            }
        )

    runners.sort(
        key=lambda runner: (
            runner.get(
                "market_rank",
                999,
            ),
            runner.get(
                "best_odds_decimal"
            )
            or 9999,
        )
    )

    return {
        "source": (
            "oddschecker_browser_dom"
        ),
        "parser_version": (
            "oddschecker_dom_v1"
        ),
        "collected_at": now_utc(),
        "url": url,
        "runner_count": len(
            runners
        ),
        "runners": runners,
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

    race_hour = int(
        match.group(1)
    )

    race_minute = int(
        match.group(2)
    )

    uk_timezone = ZoneInfo(
        "Europe/London"
    )

    now_uk = datetime.now(
        uk_timezone
    )

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

    browser_manager = (
        get_browser_manager()
    )

    page = browser_manager.new_page(
        headless=headless
    )

    try:
        page.goto(
            HOME_URL,
            wait_until=(
                "domcontentloaded"
            ),
            timeout=60000,
        )

        page.wait_for_timeout(
            5000
        )

        if not wait_for_oddschecker_access(
            page,
            timeout_seconds=180,
        ):
            return []

        accept_cookies(
            page
        )

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

        page.wait_for_timeout(
            1000
        )

        body_text = page.locator(
            "body"
        ).inner_text(
            timeout=20000
        )

        if (
            "you have been blocked"
            in body_text.lower()
        ):
            print(
                "Oddschecker blocked the discovery browser."
            )
            return []

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
                item.get(
                    "href",
                    "",
                )
            )

            text = clean(
                item.get(
                    "text",
                    "",
                )
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

            if text.lower().startswith(
                "in "
            ):
                continue

            if not race_url_is_current(
                clean_link,
                grace_minutes=10,
            ):
                skipped_past += 1
                continue

            if clean_link not in urls:
                urls.append(
                    clean_link
                )

            if len(urls) >= limit:
                break

        print(
            "Past UK/Irish race links skipped: "
            f"{skipped_past}"
        )

        print(
            "Usable current UK/Irish race links: "
            f"{len(urls)}"
        )

        return urls

    finally:
        browser_manager.close_page(
            page
        )


def collect_oddschecker_race_with_page(
    page: Page,
    url=TEST_URL,
):
    page.goto(
        url,
        wait_until=(
            "domcontentloaded"
        ),
        timeout=60000,
    )

    accept_cookies(
        page
    )

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
            () => (
                document.querySelectorAll(
                    'tr.diff-row.evTabRow[data-bname][data-bid]'
                ).length > 0
                &&
                document.querySelectorAll(
                    'tr.diff-row.evTabRow td[data-bk][data-o][data-odig]'
                ).length > 0
            )
            """,
            timeout=12000,
        )

    except Exception as exc:
        raise RuntimeError(
            "Oddschecker runner table did not populate."
        ) from exc

    page.wait_for_timeout(
        250
    )

    dom_rows = extract_race_dom(
        page
    )

    snapshot = parse_dom_market(
        dom_rows,
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
            "No DOM runners parsed."
        )

    if runner_count > 40:
        raise RuntimeError(
            f"Impossible runner count: {runner_count}"
        )

    previous_snapshot = (
        get_latest_snapshot_for_url(
            url
        )
    )

    snapshot = compare_market(
        previous_snapshot,
        snapshot,
    )

    snapshot["market"] = analyse_market(
        snapshot.get(
            "runners",
            [],
        )
    )

    append_jsonl(
        sport="horses",
        data_type=(
            "live_market"
        ),
        record=snapshot,
    )

    market_events_saved = (
        save_market_events(
            snapshot
        )
    )

    bookmaker_price_count = sum(
        len(
            runner.get(
                "prices",
                [],
            )
        )
        for runner in snapshot.get(
            "runners",
            [],
        )
    )

    print(
        "Saved Oddschecker DOM market snapshot."
    )

    print(
        "Structured runners: "
        f"{runner_count}"
    )

    print(
        "Bookmaker prices: "
        f"{bookmaker_price_count}"
    )

    print(
        "Market events saved: "
        f"{market_events_saved}"
    )

    market = snapshot.get(
        "market",
        {},
    )

    print(
        "Best-price market: "
        f"{market.get('market_percentage')}% | "
        "Overround: "
        f"{market.get('overround')}% | "
        "Arbitrage: "
        f"{market.get('is_arbitrage')}"
    )

    return snapshot


def collect_oddschecker_race(
    url=TEST_URL,
    headless: Optional[bool] = None,
):
    browser_manager = (
        get_browser_manager()
    )

    page = browser_manager.new_page(
        headless=headless
    )

    try:
        return (
            collect_oddschecker_race_with_page(
                page=page,
                url=url,
            )
        )

    finally:
        browser_manager.close_page(
            page
        )


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
            "failed": 0,
        }

    browser_manager = (
        get_browser_manager()
    )

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

            for attempt in range(
                1,
                4,
            ):
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
                            wait_until=(
                                "domcontentloaded"
                            ),
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
                and snapshot.get(
                    "runners"
                )
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
        "discovered": len(
            urls
        ),
        "saved": saved,
        "failed": failed,
    }


def monitor_all_discovered_races(
    interval_seconds=(
        DEFAULT_INTERVAL_SECONDS
    ),
    headless: Optional[bool] = None,
    limit=20,
):
    """
    Keep one shared Playwright browser alive and repeatedly collect
    every discovered Oddschecker race.

    Scans target a start-to-start cadence. If a scan takes longer than
    the configured interval, the next scan starts immediately.
    """

    browser_manager = (
        get_browser_manager()
    )

    browser_manager.start(
        headless=headless
    )

    scan_number = 0

    print(
        "=" * 70
    )

    print(
        "PULSE ODDSCHECKER MARKET MONITOR STARTED"
    )

    print(
        "=" * 70
    )

    print(
        f"Target interval: {interval_seconds} seconds"
    )

    print(
        f"Race limit per scan: {limit}"
    )

    print(
        "Browser will remain alive between scans."
    )

    print(
        "Press Ctrl+C to stop."
    )

    print(
        "=" * 70
    )

    try:
        while True:
            scan_number += 1

            scan_started = (
                datetime.now()
            )

            scan_started_monotonic = (
                time.monotonic()
            )

            print()

            print(
                "=" * 70
            )

            print(
                f"MARKET SCAN #{scan_number}"
            )

            print(
                "Started: "
                f"{scan_started.isoformat(timespec='seconds')}"
            )

            print(
                "=" * 70
            )

            result = {
                "discovered": 0,
                "saved": 0,
                "failed": 0,
            }

            try:
                result = (
                    collect_all_discovered_races(
                        headless=headless,
                        limit=limit,
                    )
                )

            except Exception as exc:
                print(
                    f"Market scan #{scan_number} failed: {exc}"
                )

            elapsed_seconds = (
                time.monotonic()
                - scan_started_monotonic
            )

            sleep_seconds = max(
                0.0,
                interval_seconds
                - elapsed_seconds,
            )

            next_scan_time = (
                datetime.fromtimestamp(
                    time.time()
                    + sleep_seconds
                )
            )

            print()

            print(
                f"Scan #{scan_number} complete | "
                f"Discovered: {result['discovered']} | "
                f"Saved: {result['saved']} | "
                f"Failed: {result.get('failed', 0)} | "
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

            time.sleep(
                sleep_seconds
            )

    except KeyboardInterrupt:
        print()

        print(
            "=" * 70
        )

        print(
            "PULSE ODDSCHECKER MARKET MONITOR STOPPED"
        )

        print(
            "=" * 70
        )

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

    try:
        while True:
            try:
                collect_oddschecker_race(
                    url=url,
                    headless=headless,
                )

            except KeyboardInterrupt:
                raise

            except Exception as exc:
                print(
                    "Oddschecker monitor "
                    f"error: {exc}"
                )

            time.sleep(
                interval_seconds
            )

    except KeyboardInterrupt:
        print(
            "Pulse Oddschecker Live "
            "Market Monitor stopped."
        )

    finally:
        browser_manager.stop()


if __name__ == "__main__":
    monitor_all_discovered_races(
        interval_seconds=(
            DEFAULT_INTERVAL_SECONDS
        ),
        headless=None,
        limit=20,
    )
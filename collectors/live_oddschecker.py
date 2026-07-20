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
from app.modules.arbitrage.store import record_snapshot


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

    upper_value = value.upper()

    if upper_value in {
        "EVS",
        "EVENS",
        "EVEN",
    }:
        return 2.0

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

        # Decimal prices are already inclusive of stake.
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
        "LD": "Ladbrokes",
        "LB": "Ladbrokes",
        "VC": "BetVictor",
        "BV": "BetVictor",
        "BY": "BoyleSports",
        "S6": "Star Sports",
        "WA": "Betway",
        "CE": "Coral",
        "SK": "Sky Bet",
        "PP": "Paddy Power",
        "BF": "Betfair",
        "BFX": "Betfair Exchange",
        "MA": "Matchbook",
        "MB": "Matchbook",
        "SM": "Smarkets",
        "BRS": "BresBet",
    }

    return aliases.get(
        value.upper(),
        value,
    )


EXCHANGE_CODES = {
    "BFX",
    "SM",
    "MA",
    "MB",
}

SPORTSBOOK_CODES = {
    "AKB",   # AK Bets
    "B3",    # bet365
    "B365",
    "BAH",   # BetAhoy
    "BF",    # Betfair Sportsbook
    "BRS",   # BresBet
    "BTT",   # BetTom
    "BY",    # BOYLE Sports
    "CE",    # Coral
    "FR",    # Betfred
    "G5",    # BetGoodwin
    "KN",    # BetMGM UK
    "LD",    # Ladbrokes
    "LB",
    "OE",    # 10bet
    "PP",    # Paddy Power
    "PUP",   # PricedUp
    "QN",    # QuinnBet
    "S6",    # Star Sports
    "SI",    # Sporting Index
    "SK",    # Sky Bet
    "SX",    # Spreadex
    "UN",    # Unibet
    "VC",    # BetVictor
    "BV",
    "VE",    # Virgin Bet
    "WA",    # Betway
    "WH",    # William Hill
}

EXCHANGE_NAMES = {
    "betfair exchange",
    "matchbook",
    "smarkets",
}


SEEN_BOOKMAKER_CODES = {}


def classify_price_source(
    bookmaker_code,
    bookmaker_name,
):
    """
    Classify an Oddschecker price as sportsbook, exchange, or unknown.

    The bookmaker code is treated as the strongest signal. Display names
    are only used as a fallback because Oddschecker labels Betfair
    Sportsbook as "Betfair" and Betfair Exchange separately.
    """

    code = clean(
        bookmaker_code
    ).upper()

    name = clean(
        bookmaker_name
    ).lower()

    if (
        code in EXCHANGE_CODES
        or name in EXCHANGE_NAMES
    ):
        return "exchange"

    if code in SPORTSBOOK_CODES:
        return "sportsbook"

    # Unknown bookmaker codes are retained but are not trusted as
    # sportsbook prices for verified back/back arbitrage.
    return "unknown"


def extract_bookmaker_headers(
    runner_lines,
):
    """
    Find the bookmaker header row shown above the runners.

    Oddschecker usually renders this as one tab-separated line. The
    function deliberately ignores generic market labels and falls back
    safely when the header cannot be identified.
    """

    ignored = {
        "odds",
        "best odds",
        "best",
        "quickbet",
        "runner",
        "horse",
        "draw",
        "jockey",
        "form",
    }

    for line in runner_lines:
        if re.fullmatch(
            r"\d+[A-Za-z]?",
            clean(line),
        ):
            break

        if "\t" not in line:
            continue

        tokens = [
            normalize_bookmaker_name(token)
            for token in line.split("\t")
            if clean(token)
        ]

        tokens = [
            token
            for token in tokens
            if token.lower() not in ignored
            and not re.search(
                r"\b\d+/\d+\b",
                token,
            )
        ]

        if len(tokens) >= 2:
            return tokens

    return []


def build_price_records(
    odds_line,
    bookmaker_headers,
):
    raw_cells = [
        clean(value)
        for value in odds_line.split("\t")
    ]

    odds_cells = [
        value
        for value in raw_cells
        if value
        and (
            re.search(
                r"\b\d+/\d+\b",
                value,
            )
            or value.upper() in {
                "EVS",
                "EVENS",
                "EVEN",
            }
            or re.fullmatch(
                r"\d+(?:\.\d+)?",
                value,
            )
        )
    ]

    if not odds_cells:
        return [], []

    bookmaker_odds = list(odds_cells)

    if (
        bookmaker_headers
        and len(bookmaker_odds)
        == len(bookmaker_headers) + 1
    ):
        bookmaker_odds = bookmaker_odds[
            :len(bookmaker_headers)
        ]

    prices = []

    for index, odds in enumerate(
        bookmaker_odds
    ):
        bookmaker = (
            bookmaker_headers[index]
            if index < len(bookmaker_headers)
            else f"Bookmaker {index + 1}"
        )

        decimal_odds = odds_to_decimal(
            odds
        )

        if not decimal_odds:
            continue

        prices.append(
            {
                "bookmaker": bookmaker,
                "odds": odds,
                "decimal": decimal_odds,
                "implied_probability": round(
                    1 / decimal_odds,
                    6,
                ),
            }
        )

    return prices, odds_cells


def summarize_prices(prices):
    valid_prices = [
        price
        for price in prices
        if price.get("decimal")
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



def report_bookmaker_codes(
    headers,
    race_url="",
):
    """
    Print the definitive Oddschecker bookmaker-code map.

    The complete table is printed on the first successful race. Later races
    only print codes whose name or classification is new or has changed.
    Unknown sources are always clearly separated so they can be added to the
    permanent sportsbook/exchange maps without guesswork.
    """

    current = {}

    for header in headers or []:
        code = clean(
            header.get("code")
        ).upper()

        if not code:
            continue

        raw_name = clean(
            header.get("raw_name")
        )

        bookmaker = clean(
            header.get("bookmaker")
        )

        source_type = clean(
            header.get("source_type")
        ) or "unknown"

        current[code] = {
            "code": code,
            "raw_name": raw_name,
            "bookmaker": bookmaker,
            "source_type": source_type,
        }

    if not current:
        return

    changed_codes = []

    for code, record in current.items():
        previous = SEEN_BOOKMAKER_CODES.get(
            code
        )

        signature = (
            record["raw_name"],
            record["bookmaker"],
            record["source_type"],
        )

        if previous != signature:
            changed_codes.append(code)

        SEEN_BOOKMAKER_CODES[code] = (
            signature
        )

    first_report = (
        len(SEEN_BOOKMAKER_CODES)
        == len(current)
        and len(changed_codes)
        == len(current)
    )

    if not first_report and not changed_codes:
        return

    print()
    print("=" * 70)

    if first_report:
        print(
            "ODDSCHECKER BOOKMAKER CODE MAP"
        )
    else:
        print(
            "ODDSCHECKER BOOKMAKER CODE MAP UPDATED"
        )

    if race_url:
        print(
            f"Source race: {race_url}"
        )

    print("-" * 70)
    print(
        f"{'CODE':<8}"
        f"{'RAW NAME':<24}"
        f"{'NORMALIZED NAME':<24}"
        f"SOURCE"
    )
    print("-" * 70)

    codes_to_print = (
        sorted(current)
        if first_report
        else sorted(changed_codes)
    )

    for code in codes_to_print:
        record = current[code]

        print(
            f"{record['code']:<8}"
            f"{record['raw_name'][:22]:<24}"
            f"{record['bookmaker'][:22]:<24}"
            f"{record['source_type']}"
        )

    unknown = [
        current[code]
        for code in sorted(current)
        if current[code][
            "source_type"
        ] == "unknown"
    ]

    print("-" * 70)
    print(
        "UNKNOWN BOOKMAKER CODES: "
        f"{len(unknown)}"
    )

    if unknown:
        for record in unknown:
            print(
                "  "
                f"{record['code']} -> "
                f"raw='{record['raw_name']}' | "
                f"normalized='{record['bookmaker']}'"
            )
    else:
        print(
            "  None"
        )

    print("=" * 70)
    print()


def extract_dom_market_prices(
    page: Page,
    expected_runner_count=None,
):
    """
    Extract bookmaker prices from the Oddschecker DOM.

    The previous parser required several bookmaker cells before a row was
    accepted and used the maximum bookmaker-header bottom position. On live
    pages this could remove runners with only one or two available prices, or
    incorrectly place the first runner above a duplicated/sticky header.

    This version:
    - identifies the main bookmaker-header band instead of using the maximum
      header position;
    - keeps sparse runner rows;
    - uses the parsed runner count to remove unrelated price rows;
    - preserves source classification for sportsbook/exchange validation.
    """

    dom_result = page.evaluate(
        """
        (expectedRunnerCount) => {
            const fractionalPattern =
                /^(?:\\d+\\/\\d+|EVS|EVENS|EVEN)$/i;

            const visible = element => {
                const rect =
                    element.getBoundingClientRect();

                const style =
                    window.getComputedStyle(element);

                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    Number.isFinite(rect.x) &&
                    Number.isFinite(rect.y)
                );
            };

            const median = values => {
                if (!values.length) {
                    return 0;
                }

                const sorted = [...values].sort(
                    (left, right) => left - right
                );

                const middle = Math.floor(
                    sorted.length / 2
                );

                if (sorted.length % 2) {
                    return sorted[middle];
                }

                return (
                    sorted[middle - 1] +
                    sorted[middle]
                ) / 2;
            };

            const headerElements = Array.from(
                document.querySelectorAll(
                    'a.bk-logo-main-90[data-bk], ' +
                    'a.bk-logo-click[data-bk]'
                )
            ).filter(visible);

            const rawHeaders = [];

            for (const element of headerElements) {
                const rect =
                    element.getBoundingClientRect();

                const code = (
                    element.getAttribute("data-bk") ||
                    ""
                ).trim();

                const image =
                    element.querySelector("img");

                const name = (
                    element.getAttribute("title") ||
                    element.getAttribute("aria-label") ||
                    image?.getAttribute("alt") ||
                    code
                ).trim();

                if (!code || !name) {
                    continue;
                }

                rawHeaders.push(
                    {
                        code,
                        name,
                        x:
                            rect.x +
                            (rect.width / 2),
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        bottom:
                            rect.y +
                            rect.height
                    }
                );
            }

            if (rawHeaders.length === 0) {
                return {
                    headers: [],
                    rows: [],
                    diagnostics: {
                        rawHeaderCount: 0,
                        rawPriceCount: 0,
                        groupedRowCount: 0
                    }
                };
            }

            /*
             * Oddschecker can expose duplicate logo bands. Select the densest
             * vertical band, then deduplicate bookmaker codes inside that band.
             */
            const headerBands = [];

            for (const header of rawHeaders) {
                let nearest = null;
                let nearestDistance = Number.MAX_VALUE;

                for (const band of headerBands) {
                    const distance = Math.abs(
                        band.y - header.y
                    );

                    if (
                        distance <= 18 &&
                        distance < nearestDistance
                    ) {
                        nearest = band;
                        nearestDistance = distance;
                    }
                }

                if (!nearest) {
                    nearest = {
                        y: header.y,
                        headers: []
                    };

                    headerBands.push(nearest);
                }

                nearest.headers.push(header);

                nearest.y = median(
                    nearest.headers.map(
                        item => item.y
                    )
                );
            }

            headerBands.sort(
                (left, right) =>
                    right.headers.length -
                    left.headers.length ||
                    left.y - right.y
            );

            const mainHeaderBand =
                headerBands[0];

            const headersByCode =
                new Map();

            for (
                const header
                of mainHeaderBand.headers
            ) {
                if (!headersByCode.has(header.code)) {
                    headersByCode.set(
                        header.code,
                        header
                    );
                }
            }

            const headers = Array.from(
                headersByCode.values()
            ).sort(
                (left, right) =>
                    left.x - right.x
            );

            const headerCodes = new Set(
                headers.map(
                    header => header.code
                )
            );

            const headerBottom = median(
                headers.map(
                    header => header.bottom
                )
            );

            const candidateElements = Array.from(
                document.querySelectorAll(
                    "[data-bk]"
                )
            );

            const rawPrices = [];

            for (const element of candidateElements) {
                if (!visible(element)) {
                    continue;
                }

                if (
                    element.classList.contains(
                        "bk-logo-main-90"
                    ) ||
                    element.classList.contains(
                        "bk-logo-click"
                    )
                ) {
                    continue;
                }

                const code = (
                    element.getAttribute("data-bk") ||
                    ""
                ).trim();

                if (!headerCodes.has(code)) {
                    continue;
                }

                const text = (
                    element.innerText ||
                    element.textContent ||
                    ""
                ).trim();

                if (!fractionalPattern.test(text)) {
                    continue;
                }

                const rect =
                    element.getBoundingClientRect();

                const centreY =
                    rect.y +
                    (rect.height / 2);

                /*
                 * Use a small tolerance rather than the old maximum-header
                 * bottom. This prevents duplicated/sticky logos from removing
                 * the first runner while still excluding header content.
                 */
                if (centreY < headerBottom - 4) {
                    continue;
                }

                rawPrices.push(
                    {
                        code,
                        odds: text,
                        x:
                            rect.x +
                            (rect.width / 2),
                        y: centreY,
                        width: rect.width,
                        height: rect.height,
                        area:
                            rect.width *
                            rect.height
                    }
                );
            }

            const dedupedPrices = [];

            rawPrices.sort(
                (left, right) =>
                    left.area - right.area
            );

            for (const price of rawPrices) {
                const duplicate =
                    dedupedPrices.some(
                        existing =>
                            existing.code ===
                                price.code &&
                            existing.odds ===
                                price.odds &&
                            Math.abs(
                                existing.x -
                                price.x
                            ) <= 4 &&
                            Math.abs(
                                existing.y -
                                price.y
                            ) <= 4
                    );

                if (!duplicate) {
                    dedupedPrices.push(price);
                }
            }

            dedupedPrices.sort(
                (left, right) =>
                    left.y - right.y ||
                    left.x - right.x
            );

            const groupedRows = [];

            for (const price of dedupedPrices) {
                let nearest = null;
                let nearestDistance =
                    Number.MAX_VALUE;

                for (
                    const candidate
                    of groupedRows
                ) {
                    const distance = Math.abs(
                        candidate.y -
                        price.y
                    );

                    const tolerance = Math.max(
                        7,
                        Math.min(
                            18,
                            Math.max(
                                candidate.maxHeight,
                                price.height
                            ) * 0.95
                        )
                    );

                    if (
                        distance <= tolerance &&
                        distance < nearestDistance
                    ) {
                        nearest = candidate;
                        nearestDistance = distance;
                    }
                }

                if (!nearest) {
                    nearest = {
                        y: price.y,
                        maxHeight:
                            price.height,
                        prices: []
                    };

                    groupedRows.push(nearest);
                }

                const existingCode =
                    nearest.prices.some(
                        existing =>
                            existing.code ===
                            price.code
                    );

                if (!existingCode) {
                    nearest.prices.push(
                        price
                    );

                    nearest.y = median(
                        nearest.prices.map(
                            item => item.y
                        )
                    );

                    nearest.maxHeight =
                        Math.max(
                            nearest.maxHeight,
                            price.height
                        );
                }
            }

            let rows = groupedRows
                .filter(
                    row =>
                        row.prices.length >= 1
                )
                .sort(
                    (left, right) =>
                        left.y - right.y
                );

            /*
             * If extra unrelated rows are present, retain the expected number
             * with the strongest bookmaker coverage, then restore page order.
             * Sparse genuine runners remain eligible.
             */
            if (
                Number.isInteger(
                    expectedRunnerCount
                ) &&
                expectedRunnerCount > 0 &&
                rows.length >
                    expectedRunnerCount
            ) {
                rows = rows
                    .map(
                        (row, index) => ({
                            ...row,
                            originalIndex: index
                        })
                    )
                    .sort(
                        (left, right) =>
                            right.prices.length -
                            left.prices.length ||
                            left.originalIndex -
                            right.originalIndex
                    )
                    .slice(
                        0,
                        expectedRunnerCount
                    )
                    .sort(
                        (left, right) =>
                            left.y - right.y
                    );
            }

            rows = rows.map(
                row => ({
                    y: row.y,
                    price_count:
                        row.prices.length,
                    prices:
                        row.prices.sort(
                            (left, right) =>
                                left.x -
                                right.x
                        )
                })
            );

            return {
                headers,
                rows,
                diagnostics: {
                    rawHeaderCount:
                        rawHeaders.length,
                    selectedHeaderCount:
                        headers.length,
                    headerBandCount:
                        headerBands.length,
                    headerBottom,
                    rawPriceCount:
                        rawPrices.length,
                    dedupedPriceCount:
                        dedupedPrices.length,
                    groupedRowCount:
                        groupedRows.length,
                    returnedRowCount:
                        rows.length,
                    expectedRunnerCount:
                        expectedRunnerCount || 0
                }
            };
        }
        """,
        expected_runner_count,
    )

    headers = []

    for header in dom_result.get(
        "headers",
        [],
    ):
        code = clean(
            header.get("code")
        )

        raw_name = clean(
            header.get("name")
        )

        bookmaker = normalize_bookmaker_name(
            raw_name or code
        )

        source_type = classify_price_source(
            code,
            bookmaker,
        )

        headers.append(
            {
                "code": code,
                "raw_name": raw_name,
                "bookmaker": bookmaker,
                "source_type": source_type,
                "is_exchange": (
                    source_type == "exchange"
                ),
                "x": header.get("x"),
            }
        )

    bookmaker_by_code = {
        header["code"]: header[
            "bookmaker"
        ]
        for header in headers
        if header.get("code")
    }

    rows = []

    for dom_row in dom_result.get(
        "rows",
        [],
    ):
        prices = []

        for price_data in dom_row.get(
            "prices",
            [],
        ):
            code = clean(
                price_data.get("code")
            )

            odds = clean(
                price_data.get("odds")
            )

            bookmaker = (
                bookmaker_by_code.get(code)
                or normalize_bookmaker_name(
                    code
                )
            )

            decimal_odds = odds_to_decimal(
                odds
            )

            if (
                not bookmaker
                or not decimal_odds
                or decimal_odds <= 1
            ):
                continue

            source_type = classify_price_source(
                code,
                bookmaker,
            )

            prices.append(
                {
                    "bookmaker": bookmaker,
                    "bookmaker_code": code,
                    "source_type": source_type,
                    "is_exchange": (
                        source_type == "exchange"
                    ),
                    "is_sportsbook": (
                        source_type == "sportsbook"
                    ),
                    "odds": odds,
                    "decimal": decimal_odds,
                    "implied_probability": round(
                        1 / decimal_odds,
                        6,
                    ),
                }
            )

        if prices:
            rows.append(
                {
                    "y": dom_row.get("y"),
                    "price_count": len(
                        prices
                    ),
                    "prices": prices,
                }
            )

    return {
        "headers": headers,
        "rows": rows,
        "diagnostics": dom_result.get(
            "diagnostics",
            {},
        ),
    }

def apply_dom_prices_to_snapshot(
    snapshot,
    dom_market,
):
    """
    Apply confirmed DOM prices to each runner.

    The runner's primary best-price fields are deliberately populated
    from sportsbook prices only. Exchange prices remain available in
    runner["exchange_prices"] for future back/lay analysis.
    """

    runners = snapshot.get(
        "runners",
        [],
    )

    dom_rows = dom_market.get(
        "rows",
        [],
    )

    headers = dom_market.get(
        "headers",
        [],
    )

    snapshot["bookmaker_headers"] = [
        header.get("bookmaker")
        for header in headers
        if header.get("bookmaker")
    ]

    snapshot["dom_price_row_count"] = len(
        dom_rows
    )

    snapshot["dom_parser_diagnostics"] = (
        dom_market.get(
            "diagnostics",
            {},
        )
    )

    snapshot["dom_complete_market"] = (
        len(dom_rows) == len(runners)
        and len(runners) > 0
    )

    snapshot["dom_bookmaker_count"] = len(
        headers
    )

    snapshot["dom_sportsbook_count"] = sum(
        1
        for header in headers
        if header.get("source_type")
        == "sportsbook"
    )

    snapshot["dom_exchange_count"] = sum(
        1
        for header in headers
        if header.get("source_type")
        == "exchange"
    )

    snapshot["dom_unknown_source_count"] = sum(
        1
        for header in headers
        if header.get("source_type")
        == "unknown"
    )

    if not runners:
        return snapshot

    for runner in runners:
        runner["confirmed_dom_prices"] = False
        runner["confirmed_sportsbook_prices"] = False

    if not dom_rows:
        print(
            "DOM parser found no bookmaker price rows."
        )

        return snapshot

    if len(dom_rows) != len(runners):
        diagnostics = dom_market.get(
            "diagnostics",
            {},
        )

        print(
            "DOM row warning | "
            f"Text runners: {len(runners)} | "
            f"DOM price rows: {len(dom_rows)} | "
            f"Raw prices: "
            f"{diagnostics.get('rawPriceCount', 0)} | "
            f"Grouped rows: "
            f"{diagnostics.get('groupedRowCount', 0)}"
        )

    dom_rows = sorted(
        dom_rows,
        key=lambda row: (
            row.get("y")
            if row.get("y") is not None
            else float("inf")
        ),
    )

    aligned_count = min(
        len(runners),
        len(dom_rows),
    )

    for index in range(
        aligned_count
    ):
        runner = runners[index]

        all_prices = dom_rows[index].get(
            "prices",
            [],
        )

        if not all_prices:
            continue

        sportsbook_prices = [
            price
            for price in all_prices
            if price.get("source_type")
            == "sportsbook"
        ]

        exchange_prices = [
            price
            for price in all_prices
            if price.get("source_type")
            == "exchange"
        ]

        unknown_prices = [
            price
            for price in all_prices
            if price.get("source_type")
            == "unknown"
        ]

        runner["prices"] = all_prices
        runner["sportsbook_prices"] = (
            sportsbook_prices
        )
        runner["exchange_prices"] = (
            exchange_prices
        )
        runner["unknown_source_prices"] = (
            unknown_prices
        )

        runner["confirmed_dom_prices"] = True
        runner[
            "confirmed_sportsbook_prices"
        ] = bool(sportsbook_prices)

        runner["exchange_price_count"] = len(
            exchange_prices
        )

        runner["unknown_source_price_count"] = len(
            unknown_prices
        )

        # Preserve the best price from any source for diagnostics only.
        all_summary = summarize_prices(
            all_prices
        )

        all_best = all_summary.get(
            "best_price"
        )

        runner["best_any_bookmaker"] = (
            all_best.get("bookmaker")
            if all_best
            else None
        )

        runner["best_any_odds"] = (
            all_best.get("odds")
            if all_best
            else None
        )

        runner["best_any_odds_decimal"] = (
            all_best.get("decimal")
            if all_best
            else None
        )

        sportsbook_summary = summarize_prices(
            sportsbook_prices
        )

        best_price = sportsbook_summary.get(
            "best_price"
        )

        worst_price = sportsbook_summary.get(
            "worst_price"
        )

        runner["bookmaker_count"] = (
            sportsbook_summary.get(
                "bookmaker_count",
                0,
            )
        )

        runner["odds_list"] = [
            price.get("odds")
            for price in sportsbook_prices
            if price.get("odds")
        ]

        runner["best_bookmaker"] = (
            best_price.get("bookmaker")
            if best_price
            else None
        )

        runner["best_bookmaker_code"] = (
            best_price.get(
                "bookmaker_code"
            )
            if best_price
            else None
        )

        runner["best_price_source_type"] = (
            best_price.get("source_type")
            if best_price
            else None
        )

        runner["best_odds"] = (
            best_price.get("odds")
            if best_price
            else None
        )

        runner["best_odds_decimal"] = (
            best_price.get("decimal")
            if best_price
            else None
        )

        runner["worst_bookmaker"] = (
            worst_price.get("bookmaker")
            if worst_price
            else None
        )

        runner["worst_odds"] = (
            worst_price.get("odds")
            if worst_price
            else None
        )

        runner["worst_odds_decimal"] = (
            worst_price.get("decimal")
            if worst_price
            else None
        )

        runner["average_odds_decimal"] = (
            sportsbook_summary.get(
                "average_decimal"
            )
        )

    return snapshot

def parse_runner_table_lines(
    runner_lines,
    bookmaker_headers=None,
):
    runners = []
    i = 0
    market_rank = 1

    bookmaker_headers = (
        bookmaker_headers or []
    )

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

        if not re.fullmatch(
            r"\d+[A-Za-z]?",
            card_number,
        ):
            i += 1
            continue

        has_supported_odds = (
            fractional_pattern.search(
                odds_line
            )
            or re.search(
                r"\bEVS|EVENS|EVEN\b",
                odds_line,
                flags=re.IGNORECASE,
            )
        )

        if not has_supported_odds:
            i += 1
            continue

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

        prices, odds_list = (
            build_price_records(
                odds_line=odds_line,
                bookmaker_headers=(
                    bookmaker_headers
                ),
            )
        )

        if not odds_list:
            i += 1
            continue

        price_summary = summarize_prices(
            prices
        )

        best_price = price_summary.get(
            "best_price"
        )

        worst_price = price_summary.get(
            "worst_price"
        )

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

        fallback_best_odds = max(
            odds_list,
            key=lambda value: (
                odds_to_decimal(value) or 0
            ),
        )

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
                "prices": prices,
                "bookmaker_count": (
                    price_summary.get(
                        "bookmaker_count",
                        0,
                    )
                ),
                "odds_list": odds_list,
                "best_bookmaker": (
                    best_price.get(
                        "bookmaker"
                    )
                    if best_price
                    else None
                ),
                "best_odds": (
                    best_price.get("odds")
                    if best_price
                    else fallback_best_odds
                ),
                "best_odds_decimal": (
                    best_price.get(
                        "decimal"
                    )
                    if best_price
                    else odds_to_decimal(
                        fallback_best_odds
                    )
                ),
                "worst_bookmaker": (
                    worst_price.get(
                        "bookmaker"
                    )
                    if worst_price
                    else None
                ),
                "worst_odds": (
                    worst_price.get("odds")
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
                    price_summary.get(
                        "average_decimal"
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

    bookmaker_headers = (
        extract_bookmaker_headers(
            runner_lines
        )
    )

    structured_runners = (
        parse_runner_table_lines(
            runner_lines,
            bookmaker_headers=(
                bookmaker_headers
            ),
        )
    )

    return {
        "source": "oddschecker_browser",
        "collected_at": now_utc(),
        "url": url,
        "bookmaker_headers": (
            bookmaker_headers
        ),
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
    Decide whether a race should still be scanned.

    UK & Ireland races use UK time.

    International races are allowed through because the URL
    does not contain enough information to safely convert the
    meeting's local time into UK time.
    """

    lower_url = url.lower()

    international_markers = (
        "/usa/",
        "/canada/",
        "/australia/",
        "/new-zealand/",
        "/hong-kong/",
        "/singapore/",
        "/france/",
        "/germany/",
        "/south-africa/",
        "/uae/",
        "/japan/",
        "/argentina/",
        "/brazil/",
        "/chile/",
    )

    if any(
        marker in lower_url
        for marker in international_markers
    ):
        return True

    match = re.search(
        r"/(\d{1,2}):(\d{2})/winner(?:$|\?)",
        url,
        flags=re.IGNORECASE,
    )

    if not match:
        return True

    race_hour = int(match.group(1))
    race_minute = int(match.group(2))

    now_uk = datetime.now(
        ZoneInfo("Europe/London")
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
    limit=50,
):
    """
    Discover every horse-racing winner market currently exposed by
    Oddschecker.

    UK and Irish races are filtered using UK time. International races
    are retained because their URL times may be local to the meeting and
    cannot safely be compared with UK time.
    """

    urls = []
    skipped_past = 0
    skipped_countdown = 0
    skipped_invalid = 0

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
                ).length > 20
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

        race_links = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();

                const links = Array.from(
                    document.querySelectorAll(
                        'a[href*="/horse-racing/"]'
                    )
                );

                for (const element of links) {
                    const rawHref =
                        element.href || "";

                    if (
                        !/\\/\\d{1,2}:\\d{2}\\/winner(?:[/?#]|$)/i
                            .test(rawHref)
                    ) {
                        continue;
                    }

                    const cleanHref = rawHref
                        .split("?")[0]
                        .split("#")[0]
                        .replace(/\\/$/, "");

                    if (seen.has(cleanHref)) {
                        continue;
                    }

                    seen.add(cleanHref);

                    results.push({
                        href: cleanHref,
                        text: (
                            element.innerText ||
                            element.textContent ||
                            ""
                        ).trim(),
                    });
                }

                return results;
            }
            """
        )

        print(
            "All horse-racing winner links found: "
            f"{len(race_links)}"
        )

        for item in race_links:
            link = clean(
                item.get("href", "")
            )

            text = clean(
                item.get("text", "")
            )

            if not link:
                skipped_invalid += 1
                continue

            if not re.search(
                r"/\d{1,2}:\d{2}/winner$",
                link,
                flags=re.IGNORECASE,
            ):
                skipped_invalid += 1
                continue

            if text.lower().startswith(
                "in "
            ):
                skipped_countdown += 1
                continue

            if not race_url_is_current(
                link,
                grace_minutes=10,
            ):
                skipped_past += 1
                continue

            if link not in urls:
                urls.append(link)

            if len(urls) >= limit:
                break

        print(
            f"Past race links skipped: "
            f"{skipped_past}"
        )

        print(
            f"Countdown race links skipped: "
            f"{skipped_countdown}"
        )

        print(
            f"Invalid race links skipped: "
            f"{skipped_invalid}"
        )

        print(
            f"Usable worldwide race links: "
            f"{len(urls)}"
        )

        return urls

    finally:
        browser_manager.close_page(
            page
        )


def calculate_canonical_sportsbook_arb(
    snapshot,
    total_stake=100.0,
):
    """
    Build the single authoritative sportsbook back/back market result.

    Every downstream consumer uses this exact dictionary: validation,
    console output, stake allocation, stored JSON and later performance
    tracking. No other function should independently recalculate the
    market percentage or arbitrage margin.
    """

    runners = snapshot.get("runners", [])

    if not isinstance(runners, list):
        runners = []

    total_runner_count = len(runners)
    market_runners = []
    missing_runners = []

    for runner in runners:
        if not isinstance(runner, dict):
            missing_runners.append("Invalid runner record")
            continue

        horse = clean(runner.get("horse")) or "Unknown runner"
        decimal = runner.get("best_odds_decimal")

        try:
            decimal = float(decimal)
        except (TypeError, ValueError):
            decimal = None

        valid = (
            runner.get("confirmed_sportsbook_prices") is True
            and runner.get("best_price_source_type") == "sportsbook"
            and decimal is not None
            and decimal > 1
            and clean(runner.get("best_bookmaker"))
        )

        if not valid:
            missing_runners.append(horse)
            continue

        market_runners.append(
            {
                "horse": horse,
                "card_number": runner.get("card_number"),
                "bookmaker": runner.get("best_bookmaker"),
                "bookmaker_code": runner.get("best_bookmaker_code"),
                "source_type": "sportsbook",
                "fractional_odds": runner.get("best_odds"),
                "decimal_odds": decimal,
                "implied_probability": 1 / decimal,
            }
        )

    confirmed_runner_count = len(market_runners)
    complete_market = (
        total_runner_count > 0
        and confirmed_runner_count == total_runner_count
    )

    result = {
        "calculation_version": "canonical_sportsbook_arb_v1",
        "market_type": "sportsbook_back_back",
        "runner_count": total_runner_count,
        "confirmed_runner_count": confirmed_runner_count,
        "complete_market": complete_market,
        "missing_runners": missing_runners,
        "requested_total_stake": round(float(total_stake), 2),
        "market_percentage": None,
        "arb_margin_percent": None,
        "is_arbitrage": False,
        "exact_guaranteed_return": None,
        "rounded_guaranteed_return": None,
        "exact_profit": None,
        "rounded_profit": None,
        "exact_roi_percent": None,
        "rounded_roi_percent": None,
        "rounded_total_stake": None,
        "legs": [],
    }

    if not complete_market:
        result["status"] = "INCOMPLETE_SPORTSBOOK_MARKET"
        snapshot["canonical_arb"] = result
        snapshot["arb_analysis"] = result
        return result

    implied_probability_total = sum(
        runner["implied_probability"]
        for runner in market_runners
    )

    if implied_probability_total <= 0:
        result["status"] = "INVALID_MARKET_PERCENTAGE"
        snapshot["canonical_arb"] = result
        snapshot["arb_analysis"] = result
        return result

    market_percentage = implied_probability_total * 100
    arb_margin_percent = 100 - market_percentage
    is_arbitrage = market_percentage < 100

    exact_guaranteed_return = (
        float(total_stake) / implied_probability_total
    )
    exact_profit = exact_guaranteed_return - float(total_stake)
    exact_roi = (
        exact_profit / float(total_stake) * 100
        if total_stake
        else 0.0
    )

    legs = []

    for runner in market_runners:
        exact_stake = (
            float(total_stake)
            * runner["implied_probability"]
            / implied_probability_total
        )
        rounded_stake = round(exact_stake, 2)
        rounded_return = round(
            rounded_stake * runner["decimal_odds"],
            2,
        )

        legs.append(
            {
                **runner,
                "implied_probability": round(
                    runner["implied_probability"],
                    6,
                ),
                "stake": rounded_stake,
                "return": rounded_return,
            }
        )

    rounded_total_stake = round(
        sum(leg["stake"] for leg in legs),
        2,
    )
    rounded_guaranteed_return = min(
        (leg["return"] for leg in legs),
        default=0.0,
    )
    rounded_profit = round(
        rounded_guaranteed_return - rounded_total_stake,
        2,
    )
    rounded_roi = (
        round(
            rounded_profit / rounded_total_stake * 100,
            2,
        )
        if rounded_total_stake
        else 0.0
    )

    result.update(
        {
            "status": (
                "ARBITRAGE"
                if is_arbitrage
                else "NO_ARBITRAGE"
            ),
            "market_percentage": round(market_percentage, 4),
            "arb_margin_percent": round(arb_margin_percent, 4),
            "is_arbitrage": is_arbitrage,
            "exact_guaranteed_return": round(
                exact_guaranteed_return,
                2,
            ),
            "rounded_guaranteed_return": round(
                rounded_guaranteed_return,
                2,
            ),
            "exact_profit": round(exact_profit, 2),
            "rounded_profit": rounded_profit,
            "exact_roi_percent": round(exact_roi, 4),
            "rounded_roi_percent": rounded_roi,
            "rounded_total_stake": rounded_total_stake,
            "legs": legs,
        }
    )

    snapshot["canonical_arb"] = result
    snapshot["arb_analysis"] = result

    return result


def validate_snapshot_for_arbitrage(
    snapshot,
    maximum_verified_margin=5.0,
    maximum_best_to_median_ratio=1.35,
):
    """
    Conservative structural trust gate for the canonical sportsbook market.

    One genuine sportsbook price per runner is sufficient. Sparse coverage is
    recorded for diagnostics but does not automatically block verification.
    Missing runners, duplicate codes, implausible outliers, bad DOM alignment
    and extreme market percentages remain hard failures.
    """

    def normalise_runner_name(value):
        return re.sub(
            r"[^a-z0-9]",
            "",
            clean(value).lower(),
        )

    def safe_int(value, default=0):
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    def safe_float(value):
        try:
            number = float(value)
            return number if number > 1 else None
        except (TypeError, ValueError):
            return None

    runners = snapshot.get("runners", [])
    if not isinstance(runners, list):
        runners = []

    canonical = snapshot.get("canonical_arb")
    if not isinstance(canonical, dict):
        canonical = calculate_canonical_sportsbook_arb(snapshot)

    runner_count = len(runners)
    dom_row_count = safe_int(snapshot.get("dom_price_row_count"))
    bookmaker_count = safe_int(snapshot.get("dom_bookmaker_count"))
    sportsbook_count = safe_int(snapshot.get("dom_sportsbook_count"))
    exchange_count = safe_int(snapshot.get("dom_exchange_count"))
    unknown_count = safe_int(snapshot.get("dom_unknown_source_count"))

    failures = []
    warnings = []
    checks = []

    def add_check(name, passed, detail, severity="failure"):
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "detail": detail,
                "severity": severity,
            }
        )
        if passed:
            return
        if severity == "warning":
            warnings.append(detail)
        else:
            failures.append(detail)

    runner_names = [
        clean(runner.get("horse"))
        for runner in runners
        if isinstance(runner, dict)
    ]
    normalised_names = [
        normalise_runner_name(name)
        for name in runner_names
        if name
    ]

    add_check(
        "runner_count",
        runner_count > 0,
        f"Parsed runners: {runner_count}" if runner_count else "No runners were parsed.",
    )
    add_check(
        "dom_row_count",
        runner_count > 0 and dom_row_count == runner_count,
        f"DOM price rows match parsed runners: {dom_row_count}/{runner_count}",
    )

    names_are_valid = (
        len(normalised_names) == runner_count
        and len(normalised_names) == len(set(normalised_names))
    )
    add_check(
        "unique_runner_names",
        names_are_valid,
        (
            "Runner names are unique and non-empty."
            if names_are_valid
            else "Duplicate or empty runner names detected."
        ),
    )
    add_check(
        "bookmaker_headers",
        bookmaker_count >= 2,
        f"Bookmaker headers detected: {bookmaker_count}",
    )
    add_check(
        "sportsbook_headers",
        sportsbook_count >= 2,
        f"Sportsbook headers detected: {sportsbook_count}",
    )
    add_check(
        "unknown_sources",
        unknown_count == 0,
        f"Unknown bookmaker sources: {unknown_count}",
    )
    add_check(
        "exchange_separation",
        exchange_count >= 0,
        f"Exchange headers separated: {exchange_count}",
    )

    complete_dom_runners = 0
    complete_sportsbook_runners = 0
    sparse_price_runners = []
    price_outlier_runners = []
    duplicate_code_runners = []
    invalid_price_runners = []

    for runner in runners:
        if not isinstance(runner, dict):
            invalid_price_runners.append("Invalid runner record")
            continue

        horse = clean(runner.get("horse")) or "Unknown runner"

        if runner.get("confirmed_dom_prices") is True:
            complete_dom_runners += 1

        raw_prices = runner.get("sportsbook_prices", [])
        if not isinstance(raw_prices, list):
            raw_prices = []

        sportsbook_prices = []
        for price in raw_prices:
            if not isinstance(price, dict):
                continue
            if price.get("source_type") != "sportsbook":
                continue
            decimal = safe_float(price.get("decimal"))
            if decimal is None:
                continue
            sportsbook_prices.append({**price, "decimal": decimal})

        if (
            runner.get("confirmed_sportsbook_prices") is True
            and sportsbook_prices
        ):
            complete_sportsbook_runners += 1

        codes = [
            clean(price.get("bookmaker_code")).upper()
            for price in sportsbook_prices
            if clean(price.get("bookmaker_code"))
        ]
        if len(codes) != len(set(codes)):
            duplicate_code_runners.append(horse)

        if not sportsbook_prices:
            invalid_price_runners.append(horse)
            continue

        if len(sportsbook_prices) == 1:
            sparse_price_runners.append(horse)

        decimal_prices = sorted(
            price["decimal"] for price in sportsbook_prices
        )
        if len(decimal_prices) >= 3:
            middle = len(decimal_prices) // 2
            median_price = (
                decimal_prices[middle]
                if len(decimal_prices) % 2
                else (
                    decimal_prices[middle - 1]
                    + decimal_prices[middle]
                ) / 2
            )
            best_price = max(decimal_prices)
            ratio = best_price / median_price if median_price > 0 else 999.0
            if ratio > maximum_best_to_median_ratio:
                price_outlier_runners.append(
                    {
                        "horse": horse,
                        "best_decimal": round(best_price, 4),
                        "median_decimal": round(median_price, 4),
                        "ratio": round(ratio, 4),
                    }
                )

    add_check(
        "all_dom_rows_confirmed",
        runner_count > 0 and complete_dom_runners == runner_count,
        f"Confirmed DOM runners: {complete_dom_runners}/{runner_count}",
    )
    add_check(
        "complete_sportsbook_market",
        runner_count > 0 and complete_sportsbook_runners == runner_count,
        f"Confirmed sportsbook runners: {complete_sportsbook_runners}/{runner_count}",
    )
    add_check(
        "valid_sportsbook_prices",
        not invalid_price_runners,
        (
            "Every runner has at least one valid sportsbook price."
            if not invalid_price_runners
            else "Missing or invalid sportsbook prices for: "
            + ", ".join(invalid_price_runners)
        ),
    )
    add_check(
        "duplicate_bookmaker_codes",
        not duplicate_code_runners,
        (
            "No duplicate bookmaker cells within runner rows."
            if not duplicate_code_runners
            else "Duplicate bookmaker codes detected for: "
            + ", ".join(duplicate_code_runners)
        ),
    )
    add_check(
        "price_outlier_check",
        not price_outlier_runners,
        (
            "No best-price outliers against runner median."
            if not price_outlier_runners
            else "Suspicious best-price outliers: "
            + ", ".join(
                f"{item['horse']} {item['best_decimal']:.2f} vs median "
                f"{item['median_decimal']:.2f} ({item['ratio']:.2f}x)"
                for item in price_outlier_runners
            )
        ),
    )

    complete_market = canonical.get("complete_market") is True
    add_check(
        "complete_canonical_market",
        complete_market,
        (
            "Canonical sportsbook market is complete: "
            f"{canonical.get('confirmed_runner_count', 0)}/{runner_count}"
        ),
    )

    market_percentage = canonical.get("market_percentage")
    arb_margin_percent = canonical.get("arb_margin_percent")

    if complete_market and market_percentage is not None:
        market_is_sane = 70 <= float(market_percentage) <= 160
        add_check(
            "market_percentage_sanity",
            market_is_sane,
            f"Sportsbook market percentage: {float(market_percentage):.2f}%",
        )

        if canonical.get("is_arbitrage"):
            margin_is_verified = (
                float(arb_margin_percent) <= maximum_verified_margin
            )
            add_check(
                "verified_margin_limit",
                margin_is_verified,
                (
                    f"Arbitrage margin: {float(arb_margin_percent):.2f}% | "
                    f"Automatic verification limit: {maximum_verified_margin:.2f}%"
                ),
                severity="warning",
            )

    passed_count = sum(1 for check in checks if check["passed"])
    total_checks = len(checks)
    score = round(
        passed_count / total_checks * 100 if total_checks else 0,
        1,
    )

    if failures:
        status = "INVALID_ALIGNMENT"
        eligible = False
    elif warnings:
        status = "REVIEW_REQUIRED"
        eligible = False
    else:
        status = "VERIFIED_ALIGNMENT"
        eligible = True

    validation = {
        "status": status,
        "eligible_for_verified_arb": eligible,
        "score": score,
        "runner_count": runner_count,
        "dom_row_count": dom_row_count,
        "bookmaker_count": bookmaker_count,
        "sportsbook_count": sportsbook_count,
        "exchange_count": exchange_count,
        "unknown_source_count": unknown_count,
        "confirmed_dom_runners": complete_dom_runners,
        "confirmed_sportsbook_runners": complete_sportsbook_runners,
        "market_percentage": market_percentage,
        "arb_margin_percent": arb_margin_percent,
        "maximum_verified_margin": maximum_verified_margin,
        "maximum_best_to_median_ratio": maximum_best_to_median_ratio,
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "price_outlier_runners": price_outlier_runners,
        "sparse_price_runners": sparse_price_runners,
    }

    snapshot["arb_validation"] = validation
    return validation

def print_arb_validation(
    validation,
):
    print(
        "Arb Validation | "
        f"Status: "
        f"{validation.get('status')} | "
        f"Score: "
        f"{validation.get('score', 0):.1f}% | "
        f"Eligible: "
        f"{validation.get('eligible_for_verified_arb')}"
    )

    for reason in validation.get(
        "failures",
        [],
    ):
        print(
            "VALIDATION FAILURE | "
            f"{reason}"
        )

    for reason in validation.get(
        "warnings",
        [],
    ):
        print(
            "VALIDATION REVIEW | "
            f"{reason}"
        )



def print_verified_arbitrage(
    snapshot,
    result=None,
    total_stake=100.0,
):
    """Print and store the already-calculated canonical arb result."""

    canonical = snapshot.get("canonical_arb")
    if not isinstance(canonical, dict):
        canonical = calculate_canonical_sportsbook_arb(
            snapshot,
            total_stake=total_stake,
        )

    validation = snapshot.get("arb_validation")
    if not validation:
        validation = validate_snapshot_for_arbitrage(snapshot)

    if not validation.get("eligible_for_verified_arb"):
        status = validation.get("status", "REVIEW_REQUIRED")
        print(f"Arbitrage withheld by validation engine: {status}")
        snapshot["verified_arb"] = {
            "verification_status": "WITHHELD_BY_VALIDATION",
            "validation_status": status,
            "validation_score": validation.get("score", 0),
            "failures": validation.get("failures", []),
            "warnings": validation.get("warnings", []),
            "canonical_arb": canonical,
        }
        return None

    if not canonical.get("complete_market"):
        print("Arbitrage rejected: sportsbook market is incomplete.")
        snapshot["verified_arb"] = {
            "verification_status": "REJECTED_INCOMPLETE_SPORTSBOOK_MARKET",
            **canonical,
        }
        return None

    if not canonical.get("is_arbitrage"):
        print("Arbitrage rejected: canonical market is not below 100%.")
        snapshot["verified_arb"] = {
            "verification_status": "REJECTED_NOT_SPORTSBOOK_ARBITRAGE",
            **canonical,
        }
        return None

    url = clean(snapshot.get("url"))
    race_name = "Unknown race"
    race_match = re.search(
        r"/horse-racing/([^/]+)/(\d{1,2}:\d{2})/winner",
        url,
        flags=re.IGNORECASE,
    )
    if race_match:
        course = race_match.group(1).replace("-", " ").title()
        race_name = f"{course} {race_match.group(2)}"

    arb_record = {
        **canonical,
        "verification_status": "VERIFIED_SPORTSBOOK_BACK_BACK",
        "validation_status": validation.get("status"),
        "validation_score": validation.get("score"),
        "race": race_name,
        "url": url,
    }
    snapshot["verified_arb"] = arb_record

    print()
    print("=" * 70)
    print("PULSE VERIFIED SPORTSBOOK ARBITRAGE")
    print("=" * 70)
    print(f"Race: {race_name}")
    print("Status: VERIFIED_SPORTSBOOK_BACK_BACK")
    print(
        "Validation: "
        f"{validation.get('status')} | "
        f"{validation.get('score', 0):.1f}%"
    )
    print(
        "Confirmed sportsbook market: "
        f"{canonical.get('confirmed_runner_count', 0)}/"
        f"{canonical.get('runner_count', 0)} runners"
    )
    print(
        "Market percentage: "
        f"{canonical.get('market_percentage', 0):.2f}%"
    )
    print(
        "Arbitrage margin: "
        f"{canonical.get('arb_margin_percent', 0):.2f}%"
    )
    print(
        "Target total stake: "
        f"£{canonical.get('requested_total_stake', 0):.2f}"
    )
    print("-" * 70)

    for leg in canonical.get("legs", []):
        print(clean(leg.get("horse")))
        print(
            "  Sportsbook: "
            f"{clean(leg.get('bookmaker'))} "
            f"[{clean(leg.get('bookmaker_code'))}]"
        )
        print(
            "  Odds: "
            f"{clean(leg.get('fractional_odds'))} "
            f"({leg.get('decimal_odds', 0):.2f})"
        )
        print(f"  Stake: £{leg.get('stake', 0):.2f}")
        print(f"  Return: £{leg.get('return', 0):.2f}")

    print("-" * 70)
    print(
        "Rounded total stake: "
        f"£{canonical.get('rounded_total_stake', 0):.2f}"
    )
    print(
        "Guaranteed return: "
        f"£{canonical.get('rounded_guaranteed_return', 0):.2f}"
    )
    print(
        "Guaranteed profit: "
        f"£{canonical.get('rounded_profit', 0):.2f}"
    )
    print(
        "Rounded ROI: "
        f"{canonical.get('rounded_roi_percent', 0):.2f}%"
    )
    print(
        "Exact theoretical ROI: "
        f"{canonical.get('exact_roi_percent', 0):.2f}%"
    )
    print("=" * 70)
    print()

    return arb_record

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
                const body =
                    document.body.innerText;

                const hasQuickBet =
                    body.includes("QuickBet");

                const hasFractionalOdds =
                    /\\b\\d+\\/\\d+\\b/.test(
                        body
                    );

                const hasBookmakerHeaders =
                    document.querySelectorAll(
                        'a.bk-logo-main-90[data-bk], ' +
                        'a.bk-logo-click[data-bk]'
                    ).length >= 2;

                return (
                    hasQuickBet &&
                    hasFractionalOdds &&
                    hasBookmakerHeaders
                );
            }
            """,
            timeout=10000,
        )

    except Exception:
        print(
            "Oddschecker DOM readiness timeout; "
            "attempting parser anyway."
        )

    page.wait_for_timeout(
        500
    )

    text = extract_race_text(
        page
    )

    snapshot = parse_visible_market_text(
        text,
        url,
    )

    expected_runner_count = len(
        snapshot.get(
            "runners",
            [],
        )
    )

    dom_market = extract_dom_market_prices(
        page,
        expected_runner_count=(
            expected_runner_count
        ),
    )

    report_bookmaker_codes(
        dom_market.get(
            "headers",
            [],
        ),
        race_url=url,
    )

    snapshot["bookmaker_code_map"] = [
        {
            "code": header.get("code"),
            "raw_name": header.get(
                "raw_name"
            ),
            "bookmaker": header.get(
                "bookmaker"
            ),
            "source_type": header.get(
                "source_type"
            ),
        }
        for header in dom_market.get(
            "headers",
            [],
        )
    ]

    snapshot = apply_dom_prices_to_snapshot(
        snapshot,
        dom_market,
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

    confirmed_dom_runners = sum(
        1
        for runner in snapshot.get(
            "runners",
            [],
        )
        if (
            runner.get(
                "confirmed_dom_prices"
            )
            is True
        )
    )

    if confirmed_dom_runners == 0:
        raise RuntimeError(
            "No confirmed DOM bookmaker prices parsed."
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

    # ----------------------------------
    # Pulse Canonical Arb Analysis
    # ----------------------------------

    try:
        canonical_result = calculate_canonical_sportsbook_arb(
            snapshot,
            total_stake=100.0,
        )

        validation = validate_snapshot_for_arbitrage(
            snapshot
        )

        print_arb_validation(validation)

        market_percentage = canonical_result.get(
            "market_percentage"
        )
        arb_margin = canonical_result.get(
            "arb_margin_percent"
        )

        if market_percentage is None:
            print(
                "Arb Analysis | Incomplete sportsbook market | "
                f"Confirmed: {canonical_result.get('confirmed_runner_count', 0)}/"
                f"{canonical_result.get('runner_count', 0)}"
            )
        else:
            print(
                "Arb Analysis | "
                f"Market %: {market_percentage:.2f}% | "
                f"Arb Margin: {arb_margin:.2f}% | "
                f"Arbitrage: {canonical_result.get('is_arbitrage')}"
            )

        if canonical_result.get("is_arbitrage"):
            print_verified_arbitrage(
                snapshot=snapshot,
                result=canonical_result,
                total_stake=100.0,
            )

    except Exception as exc:
        snapshot["arb_analysis_error"] = str(exc)
        print(f"Arbitrage analysis failed: {exc}")

    # Feed the canonical calculation and validation result into the
    # Arbitrage Opportunity Store before saving the raw market snapshot.
    try:
        stored_opportunity = record_snapshot(
            snapshot
        )

        print(
            "Arbitrage Store | "
            f"{stored_opportunity.get('status')} | "
            f"{stored_opportunity.get('race')} | "
            f"Seen: {stored_opportunity.get('seen_count')}"
        )

    except Exception as exc:
        snapshot["arb_store_error"] = str(exc)

        print(
            "Arbitrage store failed: "
            f"{exc}"
        )

    # Save the snapshot after verification so the complete arb breakdown
    # is included in the stored JSONL record.
    append_jsonl(
        sport="horses",
        data_type="live_market",
        record=snapshot,
    )

    market_events_saved = (
        save_market_events(
            snapshot
        )
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
        "DOM bookmaker headers: "
        f"{snapshot.get('dom_bookmaker_count', 0)}"
    )

    print(
        "DOM price rows: "
        f"{snapshot.get('dom_price_row_count', 0)}"
    )

    print(
        "DOM sportsbooks: "
        f"{snapshot.get('dom_sportsbook_count', 0)}"
    )

    print(
        "DOM exchanges: "
        f"{snapshot.get('dom_exchange_count', 0)}"
    )

    print(
        "DOM unknown sources: "
        f"{snapshot.get('dom_unknown_source_count', 0)}"
    )

    print(
        "Runners with confirmed DOM prices: "
        f"{confirmed_dom_runners}"
    )

    confirmed_sportsbook_runners = sum(
        1
        for runner in snapshot.get(
            "runners",
            [],
        )
        if runner.get(
            "confirmed_sportsbook_prices"
        )
    )

    print(
        "Runners with confirmed sportsbook prices: "
        f"{confirmed_sportsbook_runners}"
    )

    print(
        "Market events saved: "
        f"{market_events_saved}"
    )

    return snapshot

def meeting_from_race_url(url):
    """
    Extract the meeting slug from an Oddschecker race URL.

    Example:
    /horse-racing/vichy/15:03/winner -> vichy
    """

    match = re.search(
        r"/horse-racing/([^/]+)/",
        clean(url),
        flags=re.IGNORECASE,
    )

    if not match:
        return "unknown"

    return match.group(1).lower()


def collect_all_discovered_races(
    headless: Optional[bool] = None,
    limit=50,
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
    skipped = 0

    meeting_failure_counts = {}
    blocked_meetings = set()

    try:
        for index, url in enumerate(
            urls,
            start=1,
        ):
            meeting = meeting_from_race_url(
                url
            )

            if meeting in blocked_meetings:
                skipped += 1

                print(
                    "SKIPPED FAILED MEETING | "
                    f"{meeting} | "
                    f"{url}"
                )

                continue

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

                meeting_failure_counts[
                    meeting
                ] = 0

            else:
                failed += 1

                meeting_failure_counts[
                    meeting
                ] = (
                    meeting_failure_counts.get(
                        meeting,
                        0,
                    )
                    + 1
                )

                print(
                    "FAILED AFTER 3 ATTEMPTS | "
                    f"{url} | "
                    f"{last_error}"
                )

                if (
                    meeting != "unknown"
                    and meeting_failure_counts[
                        meeting
                    ] >= 2
                ):
                    blocked_meetings.add(
                        meeting
                    )

                    print(
                        "MEETING CIRCUIT BREAKER | "
                        f"{meeting} has failed "
                        "twice consecutively. "
                        "Remaining races from this "
                        "meeting will be skipped "
                        "for this scan."
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

    if skipped:
        print(
            "Skipped after meeting failures: "
            f"{skipped}"
        )

    if blocked_meetings:
        print(
            "Blocked meetings this scan: "
            + ", ".join(
                sorted(blocked_meetings)
            )
        )

    return {
        "discovered": len(urls),
        "saved": saved,
        "failed": failed,
        "skipped": skipped,
        "blocked_meetings": sorted(
            blocked_meetings
        ),
    }

def monitor_all_discovered_races(
    interval_seconds=DEFAULT_INTERVAL_SECONDS,
    headless: Optional[bool] = None,
    limit=50,
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
        limit=50,
    )
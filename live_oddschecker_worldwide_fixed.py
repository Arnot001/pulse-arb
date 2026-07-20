import json
import re
import time
from app.modules.arbitrage.engine import engine
from app.modules.arbitrage.scanner import scan_market
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

def extract_dom_market_prices(
    page: Page,
):
    """
    Extract bookmaker names and runner prices directly from the
    Oddschecker DOM.

    Bookmaker headers contain attributes such as:

        title="William Hill"
        data-bk="WH"

    Price cells are then matched to those bookmaker codes and grouped
    into runner rows using their vertical screen position.
    """

    dom_result = page.evaluate(
        """
        () => {
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
                    style.visibility !== "hidden"
                );
            };

            const headerElements = Array.from(
                document.querySelectorAll(
                    'a.bk-logo-main-90[data-bk], ' +
                    'a.bk-logo-click[data-bk]'
                )
            );

            const headersByCode = new Map();

            for (const element of headerElements) {
                if (!visible(element)) {
                    continue;
                }

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

                if (!headersByCode.has(code)) {
                    headersByCode.set(
                        code,
                        {
                            code,
                            name,
                            x:
                                rect.x +
                                (rect.width / 2),
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        }
                    );
                }
            }

            const headers = Array.from(
                headersByCode.values()
            ).sort(
                (left, right) =>
                    left.x - right.x
            );

            if (headers.length === 0) {
                return {
                    headers: [],
                    rows: []
                };
            }

            const headerCodes = new Set(
                headers.map(
                    header => header.code
                )
            );

            const headerBottom = Math.max(
                ...headers.map(
                    header =>
                        header.y +
                        header.height
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

                if (rect.y <= headerBottom) {
                    continue;
                }

                rawPrices.push(
                    {
                        code,
                        odds: text,
                        x:
                            rect.x +
                            (rect.width / 2),
                        y:
                            rect.y +
                            (rect.height / 2),
                        width: rect.width,
                        height: rect.height,
                        area:
                            rect.width *
                            rect.height
                    }
                );
            }

            /*
             * Oddschecker sometimes gives data-bk to both a parent and
             * child element. Keep the smallest element for each visible
             * bookmaker/odds position.
             */
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

            /*
             * Group cells using adaptive vertical spacing instead of
             * a fixed pixel tolerance. This is more robust when some
             * Oddschecker rows render slightly taller than others.
             */
            const groupedRows = [];

            for (const price of dedupedPrices) {
                let nearest = null;
                let nearestDistance = Number.MAX_VALUE;

                for (const candidate of groupedRows) {
                    const distance = Math.abs(
                        candidate.y - price.y
                    );

                    const tolerance = Math.max(
                        6,
                        Math.min(
                            14,
                            Math.max(
                                candidate.maxHeight,
                                price.height
                            ) * 0.75
                        )
                    );

                    if (
                        distance < nearestDistance &&
                        distance <= tolerance
                    ) {
                        nearest = candidate;
                        nearestDistance = distance;
                    }
                }

                if (!nearest) {
                    nearest = {
                        y: price.y,
                        maxHeight: price.height,
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
                    const previousCount =
                        nearest.prices.length;

                    nearest.prices.push(price);

                    nearest.y =
                        (
                            nearest.y * previousCount +
                            price.y
                        ) /
                        (previousCount + 1);

                    nearest.maxHeight = Math.max(
                        nearest.maxHeight,
                        price.height
                    );
                }
            }

            const minimumPricesPerRow = Math.max(
                2,
                Math.floor(headers.length * 0.15)
            );

            const rows = groupedRows
                .filter(
                    row =>
                        row.prices.length >=
                        minimumPricesPerRow
                )
                .sort(
                    (left, right) =>
                        left.y - right.y
                )
                .map(
                    row => ({
                        y: row.y,
                        prices:
                            row.prices.sort(
                                (
                                    left,
                                    right
                                ) =>
                                    left.x -
                                    right.x
                            )
                    })
                );

            return {
                headers,
                rows
            };
        }
        """
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

        headers.append(
            {
                "code": code,
                "bookmaker": bookmaker,
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

            prices.append(
                {
                    "bookmaker": bookmaker,
                    "bookmaker_code": code,
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
                    "prices": prices,
                }
            )

    return {
        "headers": headers,
        "rows": rows,
    }


def apply_dom_prices_to_snapshot(
    snapshot,
    dom_market,
):
    """
    Replace guessed Bookmaker 1, Bookmaker 2, etc. with real bookmaker
    prices extracted from the DOM.

    Runner order in the visible text table and DOM table is top-to-bottom,
    so rows are aligned using their market order.
    """

    runners = snapshot.get(
        "runners",
        [],
    )

    dom_rows = dom_market.get(
        "rows",
        [],
    )

    bookmaker_headers = [
        header.get("bookmaker")
        for header in dom_market.get(
            "headers",
            [],
        )
        if header.get("bookmaker")
    ]

    snapshot[
        "bookmaker_headers"
    ] = bookmaker_headers

    snapshot[
        "dom_price_row_count"
    ] = len(dom_rows)

    snapshot[
        "dom_bookmaker_count"
    ] = len(bookmaker_headers)

    if not runners:
        return snapshot

    if not dom_rows:
        print(
            "DOM parser found no bookmaker price rows."
        )

        return snapshot

    if len(dom_rows) != len(runners):
        print(
            "DOM row warning | "
            f"Text runners: {len(runners)} | "
            f"DOM price rows: {len(dom_rows)}"
        )

    # Keep DOM rows in their actual top-to-bottom market order.
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

        prices = dom_rows[index].get(
            "prices",
            [],
        )

        if not prices:
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

        runner["prices"] = prices

        runner[
            "bookmaker_count"
        ] = price_summary.get(
            "bookmaker_count",
            0,
        )

        runner["odds_list"] = [
            price.get("odds")
            for price in prices
            if price.get("odds")
        ]

        runner["best_bookmaker"] = (
            best_price.get("bookmaker")
            if best_price
            else None
        )

        runner["best_odds"] = (
            best_price.get("odds")
            if best_price
            else None
        )

        runner[
            "best_odds_decimal"
        ] = (
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

        runner[
            "worst_odds_decimal"
        ] = (
            worst_price.get("decimal")
            if worst_price
            else None
        )

        runner[
            "average_odds_decimal"
        ] = price_summary.get(
            "average_decimal"
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
    Discover every currently available Oddschecker horse-racing winner
    market, regardless of country or section.

    The collector no longer depends on the UK & Ireland section heading.
    It scans the complete page for genuine race winner URLs, removes
    duplicates, skips countdown cards, and filters completed UK/Irish
    races while allowing international markets through.
    """

    urls = []
    skipped_past = 0
    skipped_countdown = 0

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
                ).length > 25
                """,
                timeout=30000,
            )
        except Exception:
            print(
                "Timed out waiting for Oddschecker "
                "race links to populate."
            )

        # Trigger lazy-loaded sections by scrolling through the page.
        try:
            page.evaluate(
                """
                async () => {
                    const delay = milliseconds =>
                        new Promise(resolve =>
                            setTimeout(resolve, milliseconds)
                        );

                    const step = Math.max(
                        500,
                        Math.floor(window.innerHeight * 0.8)
                    );

                    for (
                        let y = 0;
                        y < document.body.scrollHeight;
                        y += step
                    ) {
                        window.scrollTo(0, y);
                        await delay(120);
                    }

                    window.scrollTo(0, 0);
                }
                """
            )
        except Exception:
            pass

        page.wait_for_timeout(1000)

        body_text = page.locator(
            "body"
        ).inner_text(timeout=20000)

        if "you have been blocked" in body_text.lower():
            print(
                "Oddschecker blocked the discovery browser."
            )
            return []

        section_links = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();

                document.querySelectorAll(
                    'a[href*="/horse-racing/"]'
                ).forEach(link => {
                    const rawHref = link.href || "";

                    if (
                        !/\\/\\d{1,2}:\\d{2}\\/winner(?:$|[?#])/i
                            .test(rawHref)
                    ) {
                        return;
                    }

                    const cleanHref = rawHref
                        .split("?")[0]
                        .split("#")[0]
                        .replace(/\\/$/, "");

                    if (seen.has(cleanHref)) {
                        return;
                    }

                    seen.add(cleanHref);

                    results.push({
                        href: cleanHref,
                        text: (
                            link.innerText ||
                            link.textContent ||
                            ""
                        ).trim(),
                    });
                });

                return results;
            }
            """
        )

        print(
            "All horse-racing winner links found: "
            f"{len(section_links)}"
        )

        for item in section_links:
            link = clean(
                item.get("href", "")
            )

            text = clean(
                item.get("text", "")
            )

            if not link:
                continue

            if text.lower().startswith("in "):
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
            f"Past race links skipped: {skipped_past}"
        )

        print(
            f"Countdown race links skipped: "
            f"{skipped_countdown}"
        )

        print(
            f"Usable worldwide race links: {len(urls)}"
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

    dom_market = extract_dom_market_prices(
        page
    )

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

    runners_with_prices = sum(
        1
        for runner in snapshot.get(
            "runners",
            [],
        )
        if runner.get("prices")
    )

    if runners_with_prices == 0:
        raise RuntimeError(
            "No genuine bookmaker prices parsed."
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
    # Pulse Arb Analysis
    # ----------------------------------

    try:
        race_market = engine.load_snapshot(
            snapshot
        )

        arb_analysis = scan_market(
            race_market
        )

        snapshot[
            "arb_analysis"
        ] = arb_analysis

        print(
            "Arb Analysis | "
            f"Overround: "
            f"{arb_analysis['overround']:.4f} | "
            "Back/Back: "
            f"{arb_analysis['back_back_possible']}"
        )

    except Exception as exc:
        snapshot[
            "arb_analysis_error"
        ] = str(exc)

        print(
            f"Arbitrage analysis failed: {exc}"
        )

    # This must run whether arb analysis succeeds or fails.
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
        "Runners with genuine prices: "
        f"{runners_with_prices}"
    )

    print(
        "Market events saved: "
        f"{market_events_saved}"
    )

    return snapshot

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
import requests
import logging
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.core.bookmakers import (
    UK_ALLOWED_BOOKS,
    EXCHANGE_BOOKS,
)
from app.core.pricing import (
    calculate_arb_percentage_from_inverse,
    calculate_price_gaps,
    build_arb_legs,
)

from app.core.stability import (
    build_execution_status,
    update_stability_tracking,
)

def calculate_market(bookmakers, bankroll=100.0):
    if not bookmakers:
        return None

    outcomes = {}
    all_prices = {}

    for bm in bookmakers:
        bookmaker_key = bm.get("key", "unknown")

        if bookmaker_key not in UK_ALLOWED_BOOKS:
            continue

        for market in bm.get("markets", []):
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                odds = outcome.get("price")

                if not name or not odds:
                    continue

                if odds < 1.01 or odds > 50:
                    logging.info(
                        f"SKIP | Suspicious odds ignored | "
                        f"bookmaker={bookmaker_key} | selection={name} | odds={odds}"
                    )
                    continue

                if name not in all_prices:
                    all_prices[name] = []

                all_prices[name].append({
                    "bookmaker": bookmaker_key,
                    "odds": odds,
                })

                if name not in outcomes or odds > outcomes[name]["odds"]:
                    outcomes[name] = {
                        "odds": odds,
                        "bookmaker": bookmaker_key,
                    }

    logging.info(
        f"MARKET CHECK | outcomes={len(outcomes)} "
        f"| outcome_names={list(outcomes.keys())}"
    )

    if len(outcomes) < 2:
        return None

    inv_sum = sum(1 / item["odds"] for item in outcomes.values())

    profit_percent = round(
        calculate_arb_percentage_from_inverse(inv_sum),
        2,
    )

    legs = build_arb_legs(
        outcomes=outcomes,
        bankroll=bankroll,
        inv_sum=inv_sum,
    )

    for leg in legs:
        stake = leg.get("stake")

        if stake is not None:
            leg["exact_stake"] = round(stake, 2)
            leg["natural_stake"] = round(stake)
            leg["stake_mode"] = "Natural"

    unique_books = set(leg["bookmaker"] for leg in legs)

    same_book_market = len(unique_books) == 1
    
    if same_book_market:
        logging.info(
            f"SKIP | Same bookmaker market | books={list(unique_books)}"
        )
        return None
    
    contains_exchange = any(
        leg["bookmaker"] in EXCHANGE_BOOKS
        for leg in legs
    )
    
    exchange_leg_count = sum(
        1
        for leg in legs
        if leg["bookmaker"] in EXCHANGE_BOOKS
    )

    if contains_exchange and exchange_leg_count == len(legs):
        logging.info(
            f"SKIP | Exchange-only market | books={list(unique_books)}"
        )
        return None

    price_gaps = calculate_price_gaps(all_prices)
    
    max_gap = 0

    for gap in price_gaps:
        max_gap = max(
            max_gap,
            gap.get("gap_percent", 0),
        )

    if max_gap > 500:
        logging.info(
            f"SKIP | Extreme price gap detected | "
            f"gap={max_gap}%"
        )
        return None
    
    logging.info(
        f"RESULT | profit={profit_percent} "
        f"| exchange={contains_exchange} "
        f"| exchange_legs={exchange_leg_count}/{len(legs)} "
        f"| books={list(unique_books)}"
    )

    return {
        "profit_percent": profit_percent,
        "legs": legs,
        "books": list(unique_books),
        "contains_exchange": contains_exchange,
        "same_book_market": same_book_market,
        "price_gaps": price_gaps,
    }

def fetch_sport_results(
    sport,
    api_key,
    bankroll=100.0,
    min_profit=1.0,
    near_threshold=-3.0,
):
    if not api_key:
        raise HTTPException(
            400,
            "Missing The Odds API key. Add it in Pulse Settings.",
        )

    now = datetime.now(timezone.utc)

    from_time = (now - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_time = (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport}/odds",
        params={
            "apiKey": api_key,
            "regions": "uk,eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "commenceTimeFrom": from_time,
            "commenceTimeTo": to_time,
        },
        timeout=20,
    )

    if resp.status_code != 200:
        raise HTTPException(
            500,
            f"Odds API error for {sport}: {resp.text}",
        )

    api_remaining = resp.headers.get("x-requests-remaining")
    api_used = resp.headers.get("x-requests-used")

    events = resp.json()

    logging.info(f"{sport} EVENTS RETURNED: {len(events)}")

    arbs = []
    near_arbs = []

    for event in events:

        commence_time = event.get("commence_time")

        is_live = False

        if commence_time:
            event_time = datetime.fromisoformat(
                commence_time.replace("Z", "+00:00")
            )

            now_utc = datetime.now(timezone.utc)

            time_diff = now_utc - event_time

            live_window_seconds = 10800  # 3 hours

            is_live = (
                time_diff.total_seconds() >= 0
                and time_diff.total_seconds() <= live_window_seconds
            )

        calc = calculate_market(
            event.get("bookmakers", []),
            bankroll=bankroll,
        )

        if not calc:
            continue

        item = {
            "sport": sport,
            "event": f"{event.get('home_team', 'Home')} vs {event.get('away_team', 'Away')}",
            "commence_time": event.get("commence_time"),
            
            "event_age_seconds": int(
                time_diff.total_seconds()
            ) if commence_time else 0,

            "is_live": is_live,
            "market_type": "LIVE" if is_live else "PREMATCH",

            "profit_percent": calc["profit_percent"],
            "legs": calc["legs"],
            "books": calc["books"],

            "exchange_arb": calc["contains_exchange"],
            "same_book_market": calc["same_book_market"],

            "price_gaps": calc.get("price_gaps", []),

            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

        item = update_stability_tracking(item)

        stable_seconds = item.get("stability_tracking", {}).get("stable_seconds", 0)

        item["execution"] = build_execution_status(
            profit_percent=calc["profit_percent"],
            contains_exchange=calc["contains_exchange"],
            stable_seconds=stable_seconds,
        )

        if calc["same_book_market"]:
            continue

        if calc["contains_exchange"]:
            near_arbs.append(item)

        elif calc["profit_percent"] >= min_profit:
            arbs.append(item)

        elif calc["profit_percent"] >= near_threshold:
            near_arbs.append(item)

    return arbs, near_arbs, api_remaining, api_used

def run_full_scan(
    sports_to_scan,
    api_key,
    should_pause_callback,
    save_results_callback,
    bankroll=100.0,
    min_profit=1.0,
    near_threshold=-3.0,
):
    all_arbs = []
    all_near_arbs = []
    api_remaining = None
    api_used = None
    

    for sport in sports_to_scan:
        if should_pause_callback():
            logging.warning(
                "⛔ Credit safety stop triggered. "
                "Please wait before running another scan."
            )
            break

        try:
            arbs, near_arbs, api_remaining, api_used = fetch_sport_results(
                sport=sport,
                api_key=api_key,
                bankroll=bankroll,
                min_profit=min_profit,
                near_threshold=near_threshold,
            )

            all_arbs.extend(arbs)
            all_near_arbs.extend(near_arbs)

        except Exception as e:
            logging.error(f"Sport scan error for {sport}: {e}")

    all_arbs.sort(
        key=lambda x: x["profit_percent"],
        reverse=True,
    )

    all_near_arbs.sort(
        key=lambda x: x["profit_percent"],
        reverse=True,
    )

    last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if all_arbs or all_near_arbs:
        save_results_callback(all_arbs + all_near_arbs)

    return {
        "arbs": all_arbs,
        "near_arbs": all_near_arbs,
        "last_scan": last_scan,
        "api_remaining": api_remaining,
        "api_used": api_used,
        
    }
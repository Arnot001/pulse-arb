from odds_history import save_odds_snapshot, detect_line_movement
from opportunity import classify_opportunity
import json
from datetime import datetime, timezone
from pathlib import Path

from app.api_clients.the_odds_api import TheOddsApiClient


UK_BOOKMAKERS = {
    "bet365",
    "betfair",
    "skybet",
    "williamhill",
    "ladbrokes",
    "coral",
    "paddypower",
    "unibet",
    "betvictor",
    "boylesports",
    "888sport",
    "betway",
}


BOOKMAKER_LINKS = {
    "bet365": "https://www.bet365.com/",
    "betfair": "https://www.betfair.com/exchange/plus/",
    "skybet": "https://m.skybet.com/",
    "williamhill": "https://sports.williamhill.com/betting/en-gb",
    "ladbrokes": "https://sports.ladbrokes.com/",
    "coral": "https://sports.coral.co.uk/",
    "paddypower": "https://www.paddypower.com/",
    "unibet": "https://www.unibet.co.uk/betting",
    "betvictor": "https://www.betvictor.com/en-gb/sports",
    "boylesports": "https://www.boylesports.com/",
    "888sport": "https://www.888sport.com/",
    "betway": "https://sports.betway.com/",
}


def calculate_arb(best_prices, bankroll):
    total = sum(1 / price for price in best_prices)

    arb_percent = (1 - total) * 100

    stakes = [
        round(bankroll * ((1 / price) / total), 2)
        for price in best_prices
    ]

    return arb_percent, stakes


def save_scan_history(results):
    Path("app/output").mkdir(parents=True, exist_ok=True)

    history_file = Path("app/output/scan_history.jsonl")
    scanned_at = datetime.now(timezone.utc).isoformat()

    rows = []

    for item in results["arbs"]:
        rows.append({
            "scanned_at": scanned_at,
            "type": "ARB",
            **item,
        })

    for item in results["near_arbs"]:
        rows.append({
            "scanned_at": scanned_at,
            "type": "NEAR_ARB",
            **item,
        })

    with history_file.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")


async def run_scan(
    send_alerts=False,
    bankroll=100,
    near_threshold=-3,
):
    client = TheOddsApiClient()

    fetch_data = await client.fetch_all(search_days=5)

    events = fetch_data["events"]
    remaining_credits = fetch_data.get("remaining_credits")
    used_credits = fetch_data.get("used_credits")

    arbs = []
    near_arbs = []

    for event in events:
        commence_time = event.get("commence_time")

        if commence_time:
            event_time = datetime.fromisoformat(
                commence_time.replace("Z", "+00:00")
            )

            if event_time <= datetime.now(timezone.utc):
                continue

        outcomes_map = {}

        for bookmaker in event.get("bookmakers", []):
            key = bookmaker.get("key")

            if key not in UK_BOOKMAKERS:
                continue

            for market in bookmaker.get("markets", []):
                market_key = market.get("key")

                if market_key != "h2h":
                    continue

                for outcome in market.get("outcomes", []):
                    name = outcome["name"]
                    price = outcome["price"]

                    if name not in outcomes_map:
                        outcomes_map[name] = []

                    outcomes_map[name].append({
                        "bookmaker": bookmaker["title"],
                        "bookmaker_key": key,
                        "price": price,
                        "url": BOOKMAKER_LINKS.get(key, ""),
                        "market": market_key,
                    })

        if len(outcomes_map) < 2:
            continue

        best_legs = []

        for outcome_name, prices in outcomes_map.items():
            best = max(
                prices,
                key=lambda x: x["price"],
            )

            best_legs.append({
                "outcome": outcome_name,
                **best,
            })

        bookmaker_keys_used = [
            x["bookmaker_key"]
            for x in best_legs
        ]

        if len(bookmaker_keys_used) != len(set(bookmaker_keys_used)):
            print("SKIP | Duplicate bookmaker inside arb:", bookmaker_keys_used)
            continue
        
        
        best_prices = [
            x["price"]
            for x in best_legs
        ]

        line_movements = detect_line_movement(event, best_legs)
        save_odds_snapshot(event, best_legs)

        arb_percent, stakes = calculate_arb(
            best_prices,
            bankroll,
        )

        book_percentage = round(
            sum(1 / price for price in best_prices) * 100,
            2,
        )

        price_gap_percentage = 0

        opportunity_type, opportunity_score = classify_opportunity(
            book_percentage,
            price_gap_percentage,
        )

        result = {
            "event": (
                f"{event['home_team']} "
                f"vs "
                f"{event['away_team']}"
            ),
            "line_movements": line_movements,
            "commence_time": event.get("commence_time"),
            "sport": event["sport_key"],
            "profit_percent": round(arb_percent, 2),
            "book_percentage": book_percentage,
            "opportunity_type": opportunity_type,
            "opportunity_score": opportunity_score,
            "legs": best_legs,
            "stakes": stakes,
            "bankroll": bankroll,
        }

        if arb_percent > 0:
            arbs.append(result)

        elif arb_percent > near_threshold:
            near_arbs.append(result)

    arbs = sorted(
        arbs,
        key=lambda x: x["profit_percent"],
        reverse=True,
    )

    near_arbs = sorted(
        near_arbs,
        key=lambda x: x["profit_percent"],
        reverse=True,
    )

    results = {
        "events": events,
        "arbs": arbs,
        "near_arbs": near_arbs,
        "remaining_credits": remaining_credits,
        "used_credits": used_credits,
    }

    save_scan_history(results)

    return results
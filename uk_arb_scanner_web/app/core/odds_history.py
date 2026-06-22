import json
from datetime import datetime, timezone
from pathlib import Path


HISTORY_PATH = Path("app/output/odds_snapshots.jsonl")


def save_odds_snapshot(event, best_legs):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "event": f"{event['home_team']} vs {event['away_team']}",
        "commence_time": event.get("commence_time"),
        "sport": event.get("sport_key"),
        "legs": best_legs,
    }

    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")


def load_recent_snapshots(limit=500):
    if not HISTORY_PATH.exists():
        return []

    with HISTORY_PATH.open("r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]

    return [json.loads(line) for line in lines]


def detect_line_movement(event, best_legs):
    snapshots = load_recent_snapshots()

    event_name = f"{event['home_team']} vs {event['away_team']}"

    previous = None

    for snapshot in reversed(snapshots):
        if snapshot.get("event") == event_name:
            previous = snapshot
            break

    if not previous:
        return []

    movements = []

    old_prices = {
        leg["outcome"]: leg["price"]
        for leg in previous.get("legs", [])
    }

    for leg in best_legs:
        outcome = leg["outcome"]
        new_price = leg["price"]
        old_price = old_prices.get(outcome)

        if not old_price:
            continue

        change = round(new_price - old_price, 2)

        if abs(change) >= 0.05:
            movements.append({
                "outcome": outcome,
                "bookmaker": leg["bookmaker"],
                "old_price": old_price,
                "new_price": new_price,
                "change": change,
                "direction": "UP" if change > 0 else "DOWN",
            })

    return movements
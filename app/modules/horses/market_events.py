from pathlib import Path
import json


def implied_probability(decimal_odds):
    try:
        if decimal_odds:
            return round((1 / float(decimal_odds)) * 100, 2)
    except Exception:
        pass
    return None


def get_market_events(limit=100):
    path = Path("data/horses/market_events")

    if not path.exists():
        return []

    events = []

    for file in sorted(path.glob("*.jsonl"), reverse=True):
        with file.open(encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)

                    previous_decimal = event.get("previous_best_odds_decimal")
                    current_decimal = event.get("best_odds_decimal")

                    event["previous_decimal"] = previous_decimal
                    event["current_decimal"] = current_decimal

                    event["previous_probability"] = implied_probability(previous_decimal)
                    event["current_probability"] = implied_probability(current_decimal)

                    events.append(event)

                except Exception:
                    pass

    events.sort(
        key=lambda x: x.get("detected_at", ""),
        reverse=True,
    )

    return events[:limit]
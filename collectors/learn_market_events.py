import json
from collections import defaultdict
from pathlib import Path

from app.data_store import append_jsonl


def load_enriched_market_events():
    path = Path("data/horses/enriched_market_events")
    events = []

    if not path.exists():
        return events

    for file in sorted(path.glob("*.jsonl")):
        with file.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass

    return events


def avg(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else 0


def learn_market_events():
    events = load_enriched_market_events()

    steamers = [e for e in events if e.get("event_type") == "market_shortening"]
    drifters = [e for e in events if e.get("event_type") == "market_drifting"]

    high_pulse_drifters = [
        e for e in drifters
        if (e.get("pulse_score") or 0) >= 75
    ]

    low_pulse_steamers = [
        e for e in steamers
        if (e.get("pulse_score") or 0) <= 55
    ]

    trainer_moves = defaultdict(int)
    jockey_moves = defaultdict(int)

    for event in events:
        if event.get("trainer"):
            trainer_moves[event["trainer"]] += 1
        if event.get("jockey"):
            jockey_moves[event["jockey"]] += 1

    report = {
        "source": "pulse_market_learning",
        "total_events": len(events),
        "steamers": len(steamers),
        "drifters": len(drifters),
        "avg_steamer_pulse_score": avg([e.get("pulse_score") for e in steamers]),
        "avg_drifter_pulse_score": avg([e.get("pulse_score") for e in drifters]),
        "high_pulse_drifters": high_pulse_drifters[:20],
        "low_pulse_steamers": low_pulse_steamers[:20],
        "top_trainer_market_moves": sorted(
            trainer_moves.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:20],
        "top_jockey_market_moves": sorted(
            jockey_moves.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:20],
    }

    append_jsonl(
        sport="horses",
        data_type="market_learning_reports",
        record=report,
    )

    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    learn_market_events()
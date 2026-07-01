import json
from pathlib import Path


STRATEGY_HISTORY_DIR = Path("data/strategy/history")


def load_strategy_snapshots():
    if not STRATEGY_HISTORY_DIR.exists():
        return []

    snapshots = []

    for file in sorted(STRATEGY_HISTORY_DIR.glob("*.json")):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                data["_file"] = str(file)
                snapshots.append(data)
        except Exception:
            continue

    return snapshots


def get_strategy_map(snapshot):
    strategies = snapshot.get("verified_strategies", [])

    return {
        item.get("strategy_id"): item
        for item in strategies
        if item.get("strategy_id")
    }


def calculate_change(current, previous, field):
    current_value = current.get(field, 0)
    previous_value = previous.get(field, 0)

    return round(current_value - previous_value, 1)


def get_trend_label(value):
    if value >= 5:
        return "IMPROVING_FAST"

    if value >= 1:
        return "IMPROVING"

    if value <= -5:
        return "DECLINING_FAST"

    if value <= -1:
        return "DECLINING"

    return "STABLE"


def analyse_strategy_trends():
    snapshots = load_strategy_snapshots()

    if len(snapshots) < 2:
        return []

    previous_snapshot = snapshots[-2]
    current_snapshot = snapshots[-1]

    previous_map = get_strategy_map(previous_snapshot)
    current_map = get_strategy_map(current_snapshot)

    trends = []

    for strategy_id, current in current_map.items():
        previous = previous_map.get(strategy_id)

        if not previous:
            trends.append({
                "strategy_id": strategy_id,
                "name": current.get("name"),
                "trend": "NEW",
                "trust_change": 0,
                "sample_change": current.get("sample", 0),
                "top_pick_change": 0,
                "top_3_change": 0,
                "current_trust": current.get("trust_score", 0),
                "current_status": current.get("lifecycle_status"),
            })
            continue

        trust_change = calculate_change(current, previous, "trust_score")
        sample_change = current.get("sample", 0) - previous.get("sample", 0)
        top_pick_change = calculate_change(current, previous, "top_pick_rate")
        top_3_change = calculate_change(current, previous, "top_3_rate")

        trends.append({
            "strategy_id": strategy_id,
            "name": current.get("name"),
            "trend": get_trend_label(trust_change),
            "trust_change": trust_change,
            "sample_change": sample_change,
            "top_pick_change": top_pick_change,
            "top_3_change": top_3_change,
            "current_trust": current.get("trust_score", 0),
            "current_status": current.get("lifecycle_status"),
        })

    trends.sort(
        key=lambda item: (
            item.get("current_status") != "RETIRED",
            item.get("current_trust", 0),
            item.get("trust_change", 0),
        ),
        reverse=True,
    )

    return trends


if __name__ == "__main__":
    trends = analyse_strategy_trends()

    print(f"Strategy trends found: {len(trends)}")

    for trend in trends:
        print(
            f"{trend['name']} | "
            f"{trend['trend']} | "
            f"Trust {trend['current_trust']} "
            f"({trend['trust_change']:+}) | "
            f"Sample {trend['sample_change']:+}"
        )
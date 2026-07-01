import json
from pathlib import Path

from app.modules.strategy.engine import load_race_reviews
from app.modules.strategy.discoveries.score import score_discoveries
from app.modules.strategy.discoveries.field_size import field_size_discoveries
from app.modules.strategy.discoveries.course import course_discoveries
from app.modules.strategy.discoveries.going import going_discoveries
from app.modules.strategy.discoveries.market import market_discoveries


DISCOVERY_OUTPUT = Path("data/strategy/discoveries.json")


def discover_strategies():
    reviews = load_race_reviews()

    discoveries = []

    discoveries.extend(score_discoveries(reviews))
    discoveries.extend(field_size_discoveries(reviews))
    discoveries.extend(course_discoveries(reviews))
    discoveries.extend(going_discoveries(reviews))
    discoveries.extend(market_discoveries(reviews))

    discoveries = [
        item for item in discoveries
        if item.get("sample", 0) > 0
    ]

    discoveries.sort(
        key=lambda d: (
            d.get("confidence_score", 0),
            d.get("top_3_rate", 0),
            d.get("top_pick_rate", 0),
            d.get("sample", 0),
        ),
        reverse=True,
    )

    return discoveries


def save_discoveries(discoveries):
    DISCOVERY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with DISCOVERY_OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(discoveries, f, indent=2, ensure_ascii=False)

    return DISCOVERY_OUTPUT


def run_discovery():
    discoveries = discover_strategies()
    path = save_discoveries(discoveries)

    print(f"Strategy discoveries saved: {path}")
    print(f"Discoveries found: {len(discoveries)}")

    for item in discoveries:
        print(
            f"{item['name']} | "
            f"Sample {item['sample']} | "
            f"Top Pick {item['top_pick_rate']}% | "
            f"Top 3 {item['top_3_rate']}% | "
            f"Confidence {item['confidence']}"
        )

    return discoveries


if __name__ == "__main__":
    run_discovery()
import json
from collections import Counter, defaultdict
from pathlib import Path


LEARNING_DIR = Path("data/horses/learning")
OUTPUT_DIR = Path("data/horses/learning_reports")


def load_learning_events():
    events = []

    if not LEARNING_DIR.exists():
        return events

    for file_path in LEARNING_DIR.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                events.append(json.load(f))
        except Exception:
            continue

    return events


def analyse_learning_factors():
    events = load_learning_events()

    factor_counts = Counter()
    factor_horses = defaultdict(list)

    for event in events:
        horse = event.get("horse")
        pulse_rank = event.get("pulse_rank")
        sp = event.get("sp")

        for signal in event.get("signals", []):
            factor = signal.get("signal")

            if not factor:
                continue

            factor_counts[factor] += 1

            factor_horses[factor].append(
                {
                    "horse": horse,
                    "pulse_rank": pulse_rank,
                    "sp": sp,
                    "reason": signal.get("reason"),
                }
            )

    report = {
        "learning_events": len(events),
        "factors": [],
    }

    for factor, count in factor_counts.most_common():
        report["factors"].append(
            {
                "factor": factor,
                "missed_winner_count": count,
                "examples": factor_horses[factor][:10],
            }
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / "factor_summary.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print("PULSE IQ LEARNING FACTOR REPORT")
    print("=" * 70)
    print(f"Learning events analysed: {len(events)}")
    print()

    for item in report["factors"]:
        print(f"{item['factor']}: {item['missed_winner_count']} missed winners")

    print("=" * 70)


if __name__ == "__main__":
    analyse_learning_factors()
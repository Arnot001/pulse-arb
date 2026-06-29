import json
from collections import Counter, defaultdict
from pathlib import Path


LEARNING_DIR = Path("data/horses/learning")
PERFORMANCE_DIR = Path("data/horses/performance_reports")
PULSE_SCORE_DIR = Path("data/horses/pulse_scores")
OUTPUT_DIR = Path("data/horses/learning_reports")


def normalise(value):
    return (
        str(value or "")
        .lower()
        .replace("'", "")
        .replace(".", "")
        .replace(",", "")
        .replace("&", "and")
        .strip()
    )


def load_jsonl(folder):
    records = []

    if not folder.exists():
        return records

    for file_path in folder.glob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    records.append(json.loads(line))
                except Exception:
                    continue

    return records


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


def load_latest_performance_report():
    reports = sorted(PERFORMANCE_DIR.glob("*.json"))

    if not reports:
        return None

    with reports[-1].open("r", encoding="utf-8") as f:
        return json.load(f)


def race_runner_key(course, time, horse):
    return "|".join(
        [
            normalise(course),
            normalise(time),
            normalise(horse),
        ]
    )


def build_score_lookup(target_date):
    lookup = {}

    for item in load_jsonl(PULSE_SCORE_DIR):
        if item.get("date") != target_date:
            continue

        key = race_runner_key(
            item.get("course"),
            item.get("off_time"),
            item.get("horse"),
        )

        lookup[key] = item

    return lookup


def analyse_learning_factors():
    events = load_learning_events()
    performance = load_latest_performance_report()

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

    factor_score_totals = defaultdict(float)
    factor_score_counts = Counter()
    winner_factor_totals = defaultdict(float)
    winner_factor_counts = Counter()

    if performance:
        score_lookup = build_score_lookup(performance.get("date"))

        for race in performance.get("races", []):
            top_3_names = {
                normalise(item.get("horse"))
                for item in race.get("top_3", [])
            }

            winner_key = race_runner_key(
                race.get("course"),
                race.get("time"),
                race.get("winner"),
            )

            winner_score_record = score_lookup.get(winner_key)

            if winner_score_record:
                for factor, value in winner_score_record.get("factors", {}).items():
                    winner_factor_totals[factor] += value or 0
                    winner_factor_counts[factor] += 1

            for top_runner in race.get("top_3", []):
                top_key = race_runner_key(
                    race.get("course"),
                    race.get("time"),
                    top_runner.get("horse"),
                )

                score_record = score_lookup.get(top_key)

                if not score_record:
                    continue

                for factor, value in score_record.get("factors", {}).items():
                    factor_score_totals[factor] += value or 0
                    factor_score_counts[factor] += 1

    report = {
        "learning_events": len(events),
        "performance_date": performance.get("date") if performance else None,
        "learning_signal_summary": [],
        "winner_factor_summary": [],
        "top_3_factor_summary": [],
    }

    for factor, count in factor_counts.most_common():
        report["learning_signal_summary"].append(
            {
                "factor": factor,
                "missed_winner_count": count,
                "examples": factor_horses[factor][:10],
            }
        )

    for factor, count in winner_factor_counts.most_common():
        avg_value = round(winner_factor_totals[factor] / count, 2) if count else 0

        report["winner_factor_summary"].append(
            {
                "factor": factor,
                "runner_count": count,
                "average_value": avg_value,
            }
        )

    for factor, count in factor_score_counts.most_common():
        avg_value = round(factor_score_totals[factor] / count, 2) if count else 0

        report["top_3_factor_summary"].append(
            {
                "factor": factor,
                "runner_count": count,
                "average_value": avg_value,
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

    if performance:
        print(f"Performance date: {performance.get('date')}")
        print(f"Races analysed: {performance.get('races_checked')}")
        print()

    print("Missed winner learning signals")
    print("-" * 70)

    for item in report["learning_signal_summary"][:10]:
        print(f"{item['factor']}: {item['missed_winner_count']} missed winners")

    print()
    print("Winner factor averages")
    print("-" * 70)

    for item in report["winner_factor_summary"]:
        print(
            f"{item['factor']}: "
            f"avg {item['average_value']} "
            f"over {item['runner_count']} winners"
        )

    print()
    print("Top 3 Pulse factor averages")
    print("-" * 70)

    for item in report["top_3_factor_summary"]:
        print(
            f"{item['factor']}: "
            f"avg {item['average_value']} "
            f"over {item['runner_count']} top-3 runners"
        )

    print("=" * 70)


if __name__ == "__main__":
    analyse_learning_factors()
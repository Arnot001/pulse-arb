import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


PULSE_SCORE_DIR = Path("data/horses/pulse_scores")
PUBLIC_RESULTS_DIR = Path("data/horses/sporting_life_results")
OUTPUT_DIR = Path("data/horses/performance_reports")


def normalise(value):
    text = (
        str(value or "")
        .lower()
        .replace("'", "")
        .replace(".", "")
        .replace(",", "")
        .replace("&", "and")
        .replace("(gb)", "")
        .replace("(ire)", "")
        .replace("(fr)", "")
    )

    return " ".join(text.split()).strip()


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


def race_key(course, time):
    return f"{normalise(course)}|{normalise(time)}"

def score_time(item):
    off_dt = item.get("off_dt", "")

    if "T" in str(off_dt):
        return str(off_dt).split("T")[1][:5]

    return item.get("off_time")


def shift_time(value, hours):
    try:
        parsed = datetime.strptime(str(value), "%H:%M")
        shifted = parsed + timedelta(hours=hours)
        return shifted.strftime("%H:%M").lstrip("0")
    except Exception:
        return value


def get_runner_match(
    grouped_scores,
    grouped_names,
    course,
    race_name,
    result_time,
):
    # First try exact race name
    name_key = (
        normalise(course),
        normalise(race_name),
    )

    runners = grouped_names.get(name_key)

    if runners:
        return runners

    # Then exact time
    key = race_key(course, result_time)

    if grouped_scores.get(key):
        return grouped_scores[key]

    # Finally allow ±1 hour (BST/UTC)
    for offset in (1, -1):
        key = race_key(course, shift_time(result_time, offset))

        if grouped_scores.get(key):
            return grouped_scores[key]

    return []

def dedupe_runners(runners):
    deduped = {}
    
    for runner in runners:
        key = normalise(runner.get("horse"))

        if not key:
            continue

        existing = deduped.get(key)

        if (
            existing is None
            or runner.get("pulse_score", 0) > existing.get("pulse_score", 0)
        ):
            deduped[key] = runner

    return list(deduped.values())


def dedupe_results(results):
    deduped = []
    seen = set()

    for result in results:
        raw = result.get("raw", {})
        winner = raw.get("winner", {})

        key = "|".join(
            [
                normalise(raw.get("course")),
                normalise(raw.get("race_time")),
                normalise(raw.get("race_name")),
                normalise(winner.get("horse")),
            ]
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append(result)

    return deduped


def analyse_date(target_date):
    scores = [
        item for item in load_jsonl(PULSE_SCORE_DIR)
        if item.get("date") == target_date
    ]

    results_raw = [
        item for item in load_jsonl(PUBLIC_RESULTS_DIR)
        if item.get("result_date") == target_date
    ]

    results = dedupe_results(results_raw)

    grouped_scores = defaultdict(list)
    grouped_names = defaultdict(list)

    for item in scores:
        grouped_scores[
            race_key(
                item.get("course"),
                score_time(item),
            )
        ].append(item)

        grouped_names[
            (
                normalise(item.get("course")),
                normalise(item.get("race_name")),
            )
        ].append(item)

    known_courses = {
        normalise(item.get("course"))
        for item in scores
        if item.get("course")
    }

    races_checked = 0
    top_1_wins = 0
    top_2_wins = 0
    top_3_wins = 0
    misses = []
    unmatched_results = []
    race_reports = []

    for result in results:
        raw = result.get("raw", {})

        if normalise(raw.get("course")) not in known_courses:
            continue

        winner = raw.get("winner", {})
        winner_name = winner.get("horse")

        runners = dedupe_runners(
            get_runner_match(
                grouped_scores,
                grouped_names,
                raw.get("course"),
                raw.get("race_name"),
                raw.get("race_time"),
            )
        )

        if not runners or not winner_name:
            unmatched_results.append(
                {
                    "course": raw.get("course"),
                    "time": raw.get("race_time"),
                    "race_name": raw.get("race_name"),
                    "winner": winner_name,
                }
            )
            continue

        runners.sort(
            key=lambda item: item.get("pulse_score", 0),
            reverse=True,
        )

        races_checked += 1

        winner_rank = None
        winner_score = None

        for index, runner in enumerate(runners, start=1):
            if normalise(runner.get("horse")) == normalise(winner_name):
                winner_rank = index
                winner_score = runner.get("pulse_score")
                break

        top_pick = runners[0] if runners else None

        if winner_rank == 1:
            top_1_wins += 1

        if winner_rank and winner_rank <= 2:
            top_2_wins += 1

        if winner_rank and winner_rank <= 3:
            top_3_wins += 1

        if not winner_rank or winner_rank > 3:
            misses.append(
                {
                    "course": raw.get("course"),
                    "time": raw.get("race_time"),
                    "race_name": raw.get("race_name"),
                    "winner": winner_name,
                    "sp": winner.get("sp"),
                    "winner_rank": winner_rank,
                    "winner_score": winner_score,
                    "top_pick": top_pick.get("horse") if top_pick else None,
                    "top_pick_score": top_pick.get("pulse_score") if top_pick else None,
                }
            )

        race_reports.append(
            {
                "course": raw.get("course"),
                "time": raw.get("race_time"),
                "race_name": raw.get("race_name"),
                "winner": winner_name,
                "winner_sp": winner.get("sp"),
                "winner_rank": winner_rank,
                "winner_score": winner_score,
                "top_pick": top_pick.get("horse") if top_pick else None,
                "top_pick_score": top_pick.get("pulse_score") if top_pick else None,
                "top_3": [
                    {
                        "rank": index,
                        "horse": runner.get("horse"),
                        "pulse_score": runner.get("pulse_score"),
                    }
                    for index, runner in enumerate(runners[:3], start=1)
                ],
            }
        )

    report = {
        "date": target_date,
        "pulse_score_records": len(scores),
        "public_result_records_raw": len(results_raw),
        "public_result_records_unique": len(results),
        "races_checked": races_checked,
        "unmatched_results": unmatched_results,
        "unmatched_count": len(unmatched_results),
        "top_1_wins": top_1_wins,
        "top_2_wins": top_2_wins,
        "top_3_wins": top_3_wins,
        "top_1_rate": round((top_1_wins / races_checked) * 100, 1) if races_checked else 0,
        "top_2_rate": round((top_2_wins / races_checked) * 100, 1) if races_checked else 0,
        "top_3_rate": round((top_3_wins / races_checked) * 100, 1) if races_checked else 0,
        "misses": misses,
        "races": race_reports,
    }

    return report


def save_report(report):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_path = OUTPUT_DIR / f"{report['date']}.json"

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return file_path


def print_report(report):
    print("=" * 70)
    print("PULSE IQ HORSE PERFORMANCE REPORT")
    print("=" * 70)
    print(f"Date: {report['date']}")
    print(f"Pulse score records: {report['pulse_score_records']}")
    print(f"Public result records raw: {report['public_result_records_raw']}")
    print(f"Public result records unique: {report['public_result_records_unique']}")
    print(f"Races checked: {report['races_checked']}")
    print(f"Unmatched results: {report['unmatched_count']}")
    print()
    print(f"Top Pulse Pick wins: {report['top_1_wins']} ({report['top_1_rate']}%)")
    print(f"Top 2 Pulse wins: {report['top_2_wins']} ({report['top_2_rate']}%)")
    print(f"Top 3 Pulse wins: {report['top_3_wins']} ({report['top_3_rate']}%)")
    print()

    if report["misses"]:
        print("Biggest misses / winners outside Top 3")
        print("-" * 70)

        for miss in report["misses"][:10]:
            rank = miss["winner_rank"] if miss["winner_rank"] else "not ranked"

            print(
                f"{miss['time']} {miss['course']} | "
                f"Winner: {miss['winner']} ({miss['sp']}) | "
                f"Pulse rank: {rank} | "
                f"Top pick: {miss['top_pick']} ({miss['top_pick_score']})"
            )

    print("=" * 70)


def analyse_pulse_performance():
    target_date = (
        datetime.now(timezone.utc).date()
        - timedelta(days=1)
    ).isoformat()

    report = analyse_date(target_date)
    save_report(report)
    print_report(report)

    if report["unmatched_results"]:
        print()
        print("Unmatched result examples")
        print("-" * 70)

        for item in report["unmatched_results"][:10]:
            print(
                f"{item['time']} {item['course']} | "
                f"{item['winner']} | "
                f"{item['race_name']}"
            )


if __name__ == "__main__":
    analyse_pulse_performance()
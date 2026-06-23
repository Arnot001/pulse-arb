import json
from pathlib import Path
from collections import defaultdict

from app.data_store import get_week_key


def load_horse_scores():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "pulse_scores" / f"{week_key}.jsonl"

    if not file_path.exists():
        return []

    horses = []
    seen = set()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            horse = json.loads(line)
            key = f'{horse.get("race_id")}:{horse.get("horse_id")}'

            if key in seen:
                continue

            seen.add(key)
            horses.append(horse)

    return horses


def get_top_horses(limit=20):
    horses = load_horse_scores()
    horses.sort(key=lambda x: x.get("pulse_score", 0), reverse=True)
    return horses[:limit]


def get_confidence_label(gap):
    if gap >= 15:
        return "ELITE"
    if gap >= 10:
        return "HIGH"
    if gap >= 5:
        return "MEDIUM"
    return "LOW"


def get_race_groups():
    horses = load_horse_scores()
    grouped = defaultdict(list)

    for horse in horses:
        race_key = f'{horse.get("course")}|{horse.get("off_time")}|{horse.get("race_name")}'
        grouped[race_key].append(horse)

    races = []

    for race_key, runners in grouped.items():
        course, off_time, race_name = race_key.split("|")

        runners.sort(key=lambda x: x.get("pulse_score", 0), reverse=True)

        top_runner = runners[0] if runners else None
        second_runner = runners[1] if len(runners) > 1 else None

        top_score = top_runner.get("pulse_score", 0) if top_runner else 0
        second_score = second_runner.get("pulse_score", 0) if second_runner else 0
        gap = top_score - second_score

        races.append({
            "course": course,
            "time": off_time,
            "race_name": race_name,
            "runners": runners,
            "pulse_pick": top_runner,
            "top_score": top_score,
            "second_score": second_score,
            "gap": gap,
            "confidence": get_confidence_label(gap),
        })

    races.sort(key=lambda x: (x["course"], x["time"]))
    return races
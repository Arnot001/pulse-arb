import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from app.data_store import get_week_key


def today_key():
    return datetime.now().date().isoformat()


def load_horse_scores():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "pulse_scores" / f"{week_key}.jsonl"

    if not file_path.exists():
        return []

    today = today_key()
    horses = []
    seen = set()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            horse = json.loads(line)

            if horse.get("date") != today:
                continue

            key = f'{horse.get("race_id")}:{horse.get("horse_id")}'

            if key in seen:
                continue

            seen.add(key)
            horses.append(enrich_horse_notes(horse))

    return horses


def enrich_horse_notes(horse):
    notes = horse.get("notes", [])

    normal_notes = []
    tipster_notes = []
    history_notes = []

    for note in notes:
        text = str(note)

        if text.startswith("Tipster:") or text.startswith("Tipster support"):
            tipster_notes.append(text)

        elif text.startswith("Historical") or "course winner" in text.lower():
            history_notes.append(text)

        else:
            normal_notes.append(text)

    horse["normal_notes"] = normal_notes
    horse["tipster_notes"] = tipster_notes
    horse["history_notes"] = history_notes

    return horse


def get_top_horses(limit=20):
    horses = load_horse_scores()
    horses.sort(key=lambda x: x.get("pulse_score", 0), reverse=True)
    return horses[:limit]


def get_confidence_label(gap):
    if gap >= 15:
        return "DOMINANT"
    if gap >= 10:
        return "STRONG EDGE"
    if gap >= 5:
        return "COMPETITIVE"
    return "TIGHT RACE"


def get_opportunity_note(gap, field_size):
    if gap >= 10 and field_size >= 10:
        return "Large-field standout"
    if gap >= 10:
        return "Clear Pulse edge"
    if gap <= 3:
        return "Very tight race"
    return ""


def get_race_groups():
    horses = load_horse_scores()
    grouped = defaultdict(list)

    for horse in horses:
        race_key = (
            f'{horse.get("course")}|'
            f'{horse.get("off_time")}|'
            f'{horse.get("race_name")}'
        )
        grouped[race_key].append(horse)

    races = []

    for race_key, runners in grouped.items():
        course, off_time, race_name = race_key.split("|")

        runners.sort(
            key=lambda x: x.get("pulse_score", 0),
            reverse=True,
        )

        top_runner = runners[0] if runners else None
        second_runner = runners[1] if len(runners) > 1 else None

        top_score = top_runner.get("pulse_score", 0) if top_runner else 0
        second_score = second_runner.get("pulse_score", 0) if second_runner else 0
        gap = top_score - second_score
        field_size = len(runners)

        races.append({
            "course": course,
            "time": off_time,
            "race_name": race_name,
            "runners": runners,
            "pulse_pick": top_runner,
            "top_score": top_score,
            "second_score": second_score,
            "gap": gap,
            "field_size": field_size,
            "confidence": get_confidence_label(gap),
            "opportunity_note": get_opportunity_note(gap, field_size),
        })

    races.sort(key=lambda x: (x["course"], x["time"]))
    return races


def get_race_by_key(race_key):
    races = get_race_groups()

    for race in races:
        current_key = (
            f'{race["course"]}|'
            f'{race["time"]}|'
            f'{race["race_name"]}'
        )

        if current_key == race_key:
            return race

    return None
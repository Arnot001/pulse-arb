import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict


RESULTS_DIRS = [
    Path("data/horses/sporting_life_results"),
    Path("data/horses/public_results"),
]

def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def normalise(value):
    return str(value or "").strip().lower()


def normalise_distance(value):
    return str(value or "").strip()


def normalise_going(value):
    return str(value or "").strip()


def build_horse_history():
    history = defaultdict(
        lambda: {
            "runs": 0,
            "wins": 0,
            "courses": defaultdict(
                lambda: {
                    "runs": 0,
                    "wins": 0,
                }
            ),
            "distances": defaultdict(
                lambda: {
                    "runs": 0,
                    "wins": 0,
                }
            ),
            "goings": defaultdict(
                lambda: {
                    "runs": 0,
                    "wins": 0,
                }
            ),
        }
    )

    for results_dir in RESULTS_DIRS:
        if not results_dir.exists():
            continue

        for file in results_dir.glob("*.jsonl"):
            with file.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        record = json.loads(line)
                    except Exception:
                        continue

                    race = record.get("raw", {})
                    winner = race.get("winner", {})

                    horse = winner.get("horse")
                    course = race.get("course")
                    distance = normalise_distance(
                        race.get("distance") or race.get("distance_f")
                    )
                    going = normalise_going(race.get("going"))

                    if not horse:
                        continue

                    key = normalise(horse)

                    history[key]["runs"] += 1
                    history[key]["wins"] += 1

                    if course:
                        history[key]["courses"][course]["runs"] += 1
                        history[key]["courses"][course]["wins"] += 1

                    if distance:
                        history[key]["distances"][distance]["runs"] += 1
                        history[key]["distances"][distance]["wins"] += 1

                    if going:
                        history[key]["goings"][going]["runs"] += 1
                        history[key]["goings"][going]["wins"] += 1

    return history


HORSE_HISTORY = build_horse_history()


def get_horse_history(horse_name):
    return HORSE_HISTORY.get(normalise(horse_name))


def get_distance_profile(horse_name, distance):
    history = get_horse_history(horse_name)

    if not history:
        return None

    distance = normalise_distance(distance)

    if not distance:
        return None

    stats = history.get("distances", {}).get(distance)

    if not stats:
        return None

    runs = stats.get("runs", 0)
    wins = stats.get("wins", 0)

    return {
        "distance": distance,
        "runs": runs,
        "wins": wins,
        "win_rate": round((wins / runs) * 100, 1) if runs else 0,
    }


def get_going_profile(horse_name, going):
    history = get_horse_history(horse_name)

    if not history:
        return None

    going = normalise_going(going)

    if not going:
        return None

    stats = history.get("goings", {}).get(going)

    if not stats:
        return None

    runs = stats.get("runs", 0)
    wins = stats.get("wins", 0)

    return {
        "going": going,
        "runs": runs,
        "wins": wins,
        "win_rate": round((wins / runs) * 100, 1) if runs else 0,
    }
    
def get_trainer_recent_form(trainer_name=None, trainer_id=None, days=14):
    runner_results_dir = Path("data/horses/runner_results")
    trainer_key = normalise(trainer_id or trainer_name)

    if not trainer_key:
        return None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    runs = 0
    wins = 0
    placed = 0

    if not runner_results_dir.exists():
        return None

    for file in runner_results_dir.glob("*.jsonl"):
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if not record.get("matched_racecard"):
                    continue

                race_date = record.get("result_date") or record.get("date")
                parsed_date = parse_date(race_date)

                if parsed_date and parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)

                if parsed_date and parsed_date < cutoff:
                    continue

                result_key = normalise(
                    record.get("trainer_id") or record.get("trainer")
                )

                if result_key != trainer_key:
                    continue

                runs += 1

                position = record.get("finish_position")

                try:
                    position = int(position)
                except Exception:
                    position = None

                if position == 1:
                    wins += 1

                if position is not None and position <= 3:
                    placed += 1

    if runs == 0:
        return None

    return {
        "trainer": trainer_name,
        "trainer_id": trainer_id,
        "days": days,
        "runs": runs,
        "wins": wins,
        "placed": placed,
        "win_rate": round((wins / runs) * 100, 1) if runs else 0,
        "place_rate": round((placed / runs) * 100, 1) if runs else 0,
    }
    
def get_jockey_recent_form(jockey_name=None, jockey_id=None, days=14):
    runner_results_dir = Path("data/horses/runner_results")
    jockey_key = normalise(jockey_id or jockey_name)

    if not jockey_key:
        return None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    runs = 0
    wins = 0
    placed = 0

    if not runner_results_dir.exists():
        return None

    for file in runner_results_dir.glob("*.jsonl"):
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if not record.get("matched_racecard"):
                    continue

                race_date = record.get("result_date") or record.get("date")
                parsed_date = parse_date(race_date)

                if parsed_date and parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)

                if parsed_date and parsed_date < cutoff:
                    continue

                result_key = normalise(
                    record.get("jockey_id") or record.get("jockey")
                )

                if result_key != jockey_key:
                    continue

                runs += 1

                position = record.get("finish_position")

                try:
                    position = int(position)
                except Exception:
                    position = None

                if position == 1:
                    wins += 1

                if position is not None and position <= 3:
                    placed += 1

    if runs == 0:
        return None

    return {
        "jockey": jockey_name,
        "jockey_id": jockey_id,
        "days": days,
        "runs": runs,
        "wins": wins,
        "placed": placed,
        "win_rate": round((wins / runs) * 100, 1) if runs else 0,
        "place_rate": round((placed / runs) * 100, 1) if runs else 0,
    }
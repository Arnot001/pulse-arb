import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


RESULTS_DIRS = [
    Path("data/horses/sporting_life_results"),
    Path("data/horses/public_results"),
]

RUNNER_RESULTS_DIR = Path("data/horses/runner_results")


def parse_date(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed

    except Exception:
        return None


def normalise(value):
    return str(value or "").strip().lower()


def normalise_distance(value):
    return str(value or "").strip()


def normalise_going(value):
    return str(value or "").strip()


def parse_finish_position(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
                    except json.JSONDecodeError:
                        continue

                    race = record.get("raw", {})
                    winner = race.get("winner", {})

                    horse = winner.get("horse")
                    course = race.get("course")

                    distance = normalise_distance(
                        race.get("distance")
                        or race.get("distance_f")
                    )

                    going = normalise_going(
                        race.get("going")
                    )

                    if not horse:
                        continue

                    horse_key = normalise(horse)

                    history[horse_key]["runs"] += 1
                    history[horse_key]["wins"] += 1

                    if course:
                        history[horse_key]["courses"][course]["runs"] += 1
                        history[horse_key]["courses"][course]["wins"] += 1

                    if distance:
                        history[horse_key]["distances"][distance]["runs"] += 1
                        history[horse_key]["distances"][distance]["wins"] += 1

                    if going:
                        history[horse_key]["goings"][going]["runs"] += 1
                        history[horse_key]["goings"][going]["wins"] += 1

    return history


def build_recent_form_indexes():
    trainer_results = defaultdict(list)
    jockey_results = defaultdict(list)

    records_loaded = 0

    if not RUNNER_RESULTS_DIR.exists():
        return trainer_results, jockey_results

    for file in RUNNER_RESULTS_DIR.glob("*.jsonl"):
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not record.get("matched_racecard"):
                    continue

                race_date = parse_date(
                    record.get("result_date")
                    or record.get("date")
                )

                if race_date is None:
                    continue

                finish_position = parse_finish_position(
                    record.get("finish_position")
                )

                trainer_key = normalise(
                    record.get("trainer_id")
                    or record.get("trainer")
                )

                jockey_key = normalise(
                    record.get("jockey_id")
                    or record.get("jockey")
                )

                indexed_result = {
                    "date": race_date,
                    "position": finish_position,
                }

                if trainer_key:
                    trainer_results[trainer_key].append(
                        indexed_result
                    )

                if jockey_key:
                    jockey_results[jockey_key].append(
                        indexed_result
                    )

                records_loaded += 1

    print(
        "Horse recent-form indexes built | "
        f"Records: {records_loaded} | "
        f"Trainers: {len(trainer_results)} | "
        f"Jockeys: {len(jockey_results)}"
    )

    return trainer_results, jockey_results


def calculate_recent_form(records, days):
    if not records:
        return None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    runs = 0
    wins = 0
    placed = 0

    for result in records:
        race_date = result["date"]

        if race_date < cutoff:
            continue

        runs += 1

        position = result["position"]

        if position == 1:
            wins += 1

        if position is not None and position <= 3:
            placed += 1

    if runs == 0:
        return None

    return {
        "days": days,
        "runs": runs,
        "wins": wins,
        "placed": placed,
        "win_rate": round(
            (wins / runs) * 100,
            1,
        ),
        "place_rate": round(
            (placed / runs) * 100,
            1,
        ),
    }


HORSE_HISTORY = build_horse_history()

(
    TRAINER_RECENT_FORM_INDEX,
    JOCKEY_RECENT_FORM_INDEX,
) = build_recent_form_indexes()


def get_horse_history(horse_name):
    return HORSE_HISTORY.get(
        normalise(horse_name)
    )


def get_distance_profile(horse_name, distance):
    history = get_horse_history(horse_name)

    if not history:
        return None

    distance = normalise_distance(distance)

    if not distance:
        return None

    stats = history.get(
        "distances",
        {},
    ).get(distance)

    if not stats:
        return None

    runs = stats.get("runs", 0)
    wins = stats.get("wins", 0)

    return {
        "distance": distance,
        "runs": runs,
        "wins": wins,
        "win_rate": round(
            (wins / runs) * 100,
            1,
        ) if runs else 0,
    }


def get_going_profile(horse_name, going):
    history = get_horse_history(horse_name)

    if not history:
        return None

    going = normalise_going(going)

    if not going:
        return None

    stats = history.get(
        "goings",
        {},
    ).get(going)

    if not stats:
        return None

    runs = stats.get("runs", 0)
    wins = stats.get("wins", 0)

    return {
        "going": going,
        "runs": runs,
        "wins": wins,
        "win_rate": round(
            (wins / runs) * 100,
            1,
        ) if runs else 0,
    }


def get_trainer_recent_form(
    trainer_name=None,
    trainer_id=None,
    days=14,
):
    trainer_key = normalise(
        trainer_id or trainer_name
    )

    if not trainer_key:
        return None

    form = calculate_recent_form(
        TRAINER_RECENT_FORM_INDEX.get(
            trainer_key,
            [],
        ),
        days,
    )

    if not form:
        return None

    return {
        "trainer": trainer_name,
        "trainer_id": trainer_id,
        **form,
    }


def get_jockey_recent_form(
    jockey_name=None,
    jockey_id=None,
    days=14,
):
    jockey_key = normalise(
        jockey_id or jockey_name
    )

    if not jockey_key:
        return None

    form = calculate_recent_form(
        JOCKEY_RECENT_FORM_INDEX.get(
            jockey_key,
            [],
        ),
        days,
    )

    if not form:
        return None

    return {
        "jockey": jockey_name,
        "jockey_id": jockey_id,
        **form,
    }
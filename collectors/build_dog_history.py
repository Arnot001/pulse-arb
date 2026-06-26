import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


RUNNER_RECORDS_DIR = Path("data/dogs/runner_records")
OUTPUT_DIR = Path("intelligence/dogs/history")


def parse_time(value):
    if not value:
        return None

    text = str(value).replace("s", "").strip()

    try:
        return float(text)
    except ValueError:
        return None


def empty_bucket():
    return {
        "runs": 0,
        "wins": 0,
        "seconds": 0,
        "thirds": 0,
        "places": 0,
    }


def update_bucket(bucket, position):
    bucket["runs"] += 1

    if position == 1:
        bucket["wins"] += 1

    if position == 2:
        bucket["seconds"] += 1

    if position == 3:
        bucket["thirds"] += 1

    if position in [1, 2, 3]:
        bucket["places"] += 1


def add_run(profile, run):
    position = run.get("position")

    if position is None:
        return

    try:
        position = int(position)
    except Exception:
        return

    race_id = run.get("race_id")

    if race_id in profile["_seen_races"]:
        return

    profile["_seen_races"].add(race_id)

    track = run.get("course_name") or "Unknown"
    distance = str(run.get("distance") or "Unknown")
    trap = str(run.get("trap_number") or "Unknown")
    race_class = str(run.get("race_class") or "Unknown")

    update_bucket(profile["overall"], position)
    update_bucket(profile["tracks"][track], position)
    update_bucket(profile["distances"][distance], position)
    update_bucket(profile["traps"][trap], position)
    update_bucket(profile["classes"][race_class], position)

    run_time = parse_time(run.get("run_time"))

    if run_time:
        profile["run_times"].append(run_time)

        if (
            profile["best_time"] is None
            or run_time < profile["best_time"]
        ):
            profile["best_time"] = run_time

    if run.get("date"):
        profile["last_seen"] = max(
            profile["last_seen"] or run.get("date"),
            run.get("date"),
        )


def load_runner_records():
    records = []

    for file_path in sorted(RUNNER_RECORDS_DIR.glob("*.jsonl")):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

    return records


def build_profiles():
    records = load_runner_records()
    profiles = {}

    for record in records:
        dog_id = record.get("dog_id")
        dog_name = record.get("dog_name")

        if not dog_id or not dog_name:
            continue

        key = str(dog_id)

        if key not in profiles:
            profiles[key] = {
                "dog_id": dog_id,
                "dog_name": dog_name,
                "sex": record.get("sex"),
                "colour": record.get("colour"),
                "birth_date": record.get("birth_date"),
                "trainer": record.get("trainer"),
                "owner": record.get("owner"),
                "sire": record.get("sire"),
                "dam": record.get("dam"),
                "current_form": record.get("form"),
                "overall": empty_bucket(),
                "tracks": defaultdict(empty_bucket),
                "distances": defaultdict(empty_bucket),
                "traps": defaultdict(empty_bucket),
                "classes": defaultdict(empty_bucket),
                "best_time": None,
                "average_time": None,
                "run_times": [],
                "last_seen": None,
                "_seen_races": set(),
            }

        profile = profiles[key]

        for previous_run in record.get("previous_results", []):
            add_run(profile, previous_run)

    return profiles


def finalise_profile(profile):
    run_times = profile.pop("run_times", [])
    profile.pop("_seen_races", None)

    overall = profile["overall"]
    runs = overall["runs"]

    if runs:
        profile["win_rate"] = round(
            (overall["wins"] / runs) * 100,
            2,
        )
        profile["place_rate"] = round(
            (overall["places"] / runs) * 100,
            2,
        )
    else:
        profile["win_rate"] = 0
        profile["place_rate"] = 0

    if run_times:
        profile["average_time"] = round(mean(run_times), 2)

    profile["tracks"] = dict(profile["tracks"])
    profile["distances"] = dict(profile["distances"])
    profile["traps"] = dict(profile["traps"])
    profile["classes"] = dict(profile["classes"])

    return profile


def save_profiles(profiles):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    saved = 0

    for dog_id, profile in profiles.items():
        final_profile = finalise_profile(profile)

        file_path = OUTPUT_DIR / f"{dog_id}.json"

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(
                final_profile,
                f,
                ensure_ascii=False,
                indent=2,
            )

        saved += 1

    print(f"Built {saved} dog history profiles.")


def build_dog_history():
    profiles = build_profiles()
    save_profiles(profiles)


if __name__ == "__main__":
    build_dog_history()
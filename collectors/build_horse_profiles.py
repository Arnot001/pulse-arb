import json
from collections import defaultdict, Counter
from pathlib import Path


RUNNER_RECORDS_DIR = Path("data/horses/runner_records")
PULSE_SCORES_DIR = Path("data/horses/pulse_scores")
PROFILE_DIR = Path("data/horses/profiles")


def slugify(value):
    return (
        str(value or "")
        .lower()
        .replace("&", "and")
        .replace(".", "")
        .replace("'", "")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )


def load_jsonl_records(folder):
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


def latest_by_horse_id(records):
    latest = {}

    for record in records:
        horse_id = record.get("horse_id")
        stored_at = record.get("_stored_at", "")

        if not horse_id:
            continue

        current = latest.get(horse_id)

        if not current or stored_at > current.get("_stored_at", ""):
            latest[horse_id] = record

    return latest


def avg(values):
    clean = []

    for value in values:
        try:
            if value is not None:
                clean.append(float(value))
        except Exception:
            continue

    if not clean:
        return 0

    return round(sum(clean) / len(clean), 2)


def build_profile(horse_id, records, latest_scores):
    records = sorted(
        records,
        key=lambda item: item.get("off_dt") or item.get("_stored_at") or "",
    )

    latest = records[-1]
    latest_score = latest_scores.get(horse_id, {})

    courses = Counter(record.get("course") for record in records if record.get("course"))
    distances = Counter(record.get("distance_f") for record in records if record.get("distance_f"))
    goings = Counter(record.get("going") for record in records if record.get("going"))
    classes = Counter(record.get("race_class") for record in records if record.get("race_class"))
    trainers = Counter(record.get("trainer") for record in records if record.get("trainer"))
    jockeys = Counter(record.get("jockey") for record in records if record.get("jockey"))

    pulse_scores = [
        record.get("pulse_score")
        for record in records
        if record.get("pulse_score") is not None
    ]

    profile = {
        "horse": latest.get("horse"),
        "horse_id": horse_id,
        "age": latest.get("age"),
        "sex": latest.get("sex"),
        "latest_course": latest.get("course"),
        "latest_time": latest.get("off_time"),
        "latest_race": latest.get("race_name"),
        "latest_date": latest.get("date"),
        "latest_distance_f": latest.get("distance_f"),
        "latest_class": latest.get("race_class"),
        "latest_going": latest.get("going"),
        "latest_surface": latest.get("surface"),
        "latest_trainer": latest.get("trainer"),
        "latest_jockey": latest.get("jockey"),
        "latest_draw": latest.get("draw"),
        "latest_weight_lbs": latest.get("lbs"),
        "official_rating": latest.get("ofr"),
        "recent_form": latest.get("form"),
        "last_run_days": latest.get("last_run"),
        "profile_runs": len(records),
        "courses_seen": dict(courses.most_common()),
        "distances_seen": dict(distances.most_common()),
        "goings_seen": dict(goings.most_common()),
        "classes_seen": dict(classes.most_common()),
        "trainers_seen": dict(trainers.most_common()),
        "jockeys_seen": dict(jockeys.most_common()),
        "average_pulse_score": avg(pulse_scores),
        "best_pulse_score": max(pulse_scores) if pulse_scores else None,
        "latest_pulse_score": latest_score.get("pulse_score"),
        "latest_notes": latest_score.get("notes", []),
        "runs": records[-20:],
    }

    notes = []

    if profile["latest_pulse_score"] and profile["latest_pulse_score"] >= 80:
        notes.append("Elite latest Pulse Score")

    if profile["average_pulse_score"] >= 70:
        notes.append("Strong average Pulse profile")

    if profile["profile_runs"] >= 3:
        notes.append("Profile has multiple stored runs")

    if profile["latest_draw"] and profile["latest_draw"] <= 3:
        notes.append("Low draw today")

    if profile["last_run_days"] is not None:
        if profile["last_run_days"] <= 14:
            notes.append("Recent run timing")
        elif profile["last_run_days"] >= 90:
            notes.append("Returning from a break")

    profile["profile_notes"] = notes

    return profile


def build_horse_profiles():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    runner_records = load_jsonl_records(RUNNER_RECORDS_DIR)
    pulse_scores = load_jsonl_records(PULSE_SCORES_DIR)

    latest_scores = latest_by_horse_id(pulse_scores)

    grouped = defaultdict(list)

    for record in runner_records:
        horse_id = record.get("horse_id")

        if not horse_id:
            continue

        grouped[horse_id].append(record)

    saved = 0

    for horse_id, records in grouped.items():
        profile = build_profile(
            horse_id=horse_id,
            records=records,
            latest_scores=latest_scores,
        )

        file_name = slugify(profile["horse"]) + ".json"
        file_path = PROFILE_DIR / file_name

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        saved += 1

    print(f"Horse runner records loaded: {len(runner_records)}")
    print(f"Horse pulse scores loaded: {len(pulse_scores)}")
    print(f"Horse profiles saved: {saved}")


if __name__ == "__main__":
    build_horse_profiles()
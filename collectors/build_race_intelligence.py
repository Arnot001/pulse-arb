import json
from collections import defaultdict
from pathlib import Path


HORSE_PROFILE_DIR = Path("data/horses/profiles")
OUTPUT_DIR = Path("data/horses/race_intelligence")


def load_profiles():
    profiles = []

    if not HORSE_PROFILE_DIR.exists():
        return profiles

    for file_path in HORSE_PROFILE_DIR.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                profiles.append(json.load(f))
        except Exception:
            continue

    return profiles


def race_key(profile):
    return "|".join(
        [
            str(profile.get("latest_date") or ""),
            str(profile.get("latest_course") or ""),
            str(profile.get("latest_time") or ""),
            str(profile.get("latest_race") or ""),
        ]
    )


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


def rating_label(score):
    if score >= 85:
        return "HIGH"
    if score >= 70:
        return "GOOD"
    if score >= 55:
        return "MEDIUM"
    return "LOW"


def build_race_report(race_profiles):
    race_profiles = sorted(
        race_profiles,
        key=lambda item: item.get("horse_intelligence_score") or 0,
        reverse=True,
    )

    top = race_profiles[0] if race_profiles else None
    second = race_profiles[1] if len(race_profiles) > 1 else None

    top_score = top.get("horse_intelligence_score") or 0 if top else 0
    second_score = second.get("horse_intelligence_score") or 0 if second else 0
    gap = top_score - second_score

    scores = [
        horse.get("horse_intelligence_score") or 0
        for horse in race_profiles
    ]

    avg_score = avg(scores)

    if gap >= 20:
        race_shape = "CLEAR STANDOUT"
    elif gap >= 10:
        race_shape = "PULSE EDGE"
    elif gap >= 5:
        race_shape = "COMPETITIVE EDGE"
    else:
        race_shape = "OPEN RACE"

    confidence_score = round(
        min(
            100,
            max(
                0,
                (top_score * 0.6)
                + (gap * 1.5)
                + (avg_score * 0.2)
            ),
        )
    )

    dark_horse = None

    for horse in race_profiles[1:]:
        score = horse.get("horse_intelligence_score") or 0
        latest = horse.get("latest_pulse_score") or 0
        suitability = horse.get("suitability_score") or 0

        if score >= 55 and latest >= 55 and suitability >= 70:
            dark_horse = horse
            break

    if not dark_horse and len(race_profiles) >= 3:
        dark_horse = race_profiles[2]

    notes = []

    if top:
        notes.append(f"{top.get('horse')} is the top-rated Pulse IQ runner.")

    if gap >= 10:
        notes.append("The top runner has a clear intelligence gap over the field.")
    elif gap <= 4:
        notes.append("The race looks competitive with no clear standout.")

    if avg_score >= 70:
        notes.append("This race contains several strong intelligence profiles.")
    elif avg_score <= 45:
        notes.append("This race has a generally weak profile strength.")

    if dark_horse:
        notes.append(f"{dark_horse.get('horse')} is flagged as a possible dark horse.")

    report = {
        "race_id": top.get("latest_race") if top else None,
        "date": top.get("latest_date") if top else None,
        "course": top.get("latest_course") if top else None,
        "time": top.get("latest_time") if top else None,
        "race_name": top.get("latest_race") if top else None,
        "field_size": len(race_profiles),
        "average_intelligence": avg_score,
        "top_score": top_score,
        "second_score": second_score,
        "gap": gap,
        "confidence_score": confidence_score,
        "confidence": rating_label(confidence_score),
        "race_shape": race_shape,
        "top_runner": top,
        "main_threat": second,
        "dark_horse": dark_horse,
        "runners": race_profiles,
        "notes": notes,
    }

    return report


def slugify(value):
    return (
        str(value or "")
        .lower()
        .replace("&", "and")
        .replace(".", "")
        .replace("'", "")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "")
        .replace(" ", "_")
    )


def build_race_intelligence():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    profiles = load_profiles()
    grouped = defaultdict(list)

    for profile in profiles:
        key = race_key(profile)

        if key.strip("|"):
            grouped[key].append(profile)

    saved = 0

    reports = []

    for key, race_profiles in grouped.items():
        if not race_profiles:
            continue

        report = build_race_report(race_profiles)

        file_name = (
            slugify(report.get("date"))
            + "_"
            + slugify(report.get("course"))
            + "_"
            + slugify(report.get("time"))
            + ".json"
        )

        file_path = OUTPUT_DIR / file_name

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        reports.append(report)
        saved += 1

    leaderboard_path = Path("data/horses/race_intelligence_leaderboard.json")

    reports = sorted(
        reports,
        key=lambda item: item.get("confidence_score") or 0,
        reverse=True,
    )

    with leaderboard_path.open("w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    print(f"Horse profiles loaded: {len(profiles)}")
    print(f"Race groups built: {len(grouped)}")
    print(f"Race intelligence reports saved: {saved}")


if __name__ == "__main__":
    build_race_intelligence()
import json
from collections import Counter
from pathlib import Path


PROFILE_DIR = Path("data/horses/profiles")
ENRICH_VERSION = "profile_enrich_v2"


def most_common_label(items):
    if not items:
        return None

    counter = Counter(items)
    label, count = counter.most_common(1)[0]

    return {
        "value": label,
        "runs": count,
    }


def score_condition_match(latest_value, favourite):
    if not latest_value or not favourite:
        return 50

    if str(latest_value).lower() == str(favourite["value"]).lower():
        return 90

    return 55


def get_profile_signature(profile):
    return {
        "latest_course": profile.get("latest_course"),
        "latest_distance_f": profile.get("latest_distance_f"),
        "latest_going": profile.get("latest_going"),
        "latest_class": profile.get("latest_class"),
        "latest_pulse_score": profile.get("latest_pulse_score"),
        "average_pulse_score": profile.get("average_pulse_score"),
        "profile_runs": profile.get("profile_runs"),
        "runs_count": len(profile.get("runs", [])),
    }


def profile_already_enriched(profile):
    return (
        profile.get("enrich_version") == ENRICH_VERSION
        and profile.get("enrich_signature") == get_profile_signature(profile)
    )


def enrich_profile(profile):
    favourite_course = most_common_label(
        [
            run.get("course")
            for run in profile.get("runs", [])
            if run.get("course")
        ]
    )

    favourite_distance = most_common_label(
        [
            run.get("distance_f")
            for run in profile.get("runs", [])
            if run.get("distance_f")
        ]
    )

    favourite_going = most_common_label(
        [
            run.get("going")
            for run in profile.get("runs", [])
            if run.get("going")
        ]
    )

    favourite_class = most_common_label(
        [
            run.get("race_class")
            for run in profile.get("runs", [])
            if run.get("race_class")
        ]
    )

    course_score = score_condition_match(
        profile.get("latest_course"),
        favourite_course,
    )

    distance_score = score_condition_match(
        profile.get("latest_distance_f"),
        favourite_distance,
    )

    going_score = score_condition_match(
        profile.get("latest_going"),
        favourite_going,
    )

    class_score = score_condition_match(
        profile.get("latest_class"),
        favourite_class,
    )

    avg_pulse = profile.get("average_pulse_score") or 0
    latest_pulse = profile.get("latest_pulse_score") or avg_pulse

    suitability_score = round(
        (
            course_score
            + distance_score
            + going_score
            + class_score
        )
        / 4
    )

    intelligence_score = round(
        latest_pulse * 0.45
        + avg_pulse * 0.25
        + suitability_score * 0.30
    )

    strengths = []
    cautions = []

    if course_score >= 85:
        strengths.append("Today's course matches strongest profile pattern")
    else:
        cautions.append("Course does not strongly match stored profile")

    if distance_score >= 85:
        strengths.append("Today's distance matches strongest profile pattern")
    else:
        cautions.append("Distance not yet a clear profile strength")

    if going_score >= 85:
        strengths.append("Today's going matches known profile preference")
    else:
        cautions.append("Going is not clearly proven from stored profile")

    if class_score >= 85:
        strengths.append("Race class matches common profile level")

    if latest_pulse >= 80:
        strengths.append("Elite latest Pulse Score")
    elif latest_pulse >= 65:
        strengths.append("Positive latest Pulse Score")
    elif latest_pulse <= 40:
        cautions.append("Low latest Pulse Score")

    if profile.get("profile_runs", 0) < 3:
        cautions.append("Limited stored profile data")

    profile["favourite_course"] = favourite_course
    profile["favourite_distance"] = favourite_distance
    profile["favourite_going"] = favourite_going
    profile["favourite_class"] = favourite_class

    profile["course_suitability_score"] = course_score
    profile["distance_suitability_score"] = distance_score
    profile["going_suitability_score"] = going_score
    profile["class_suitability_score"] = class_score
    profile["suitability_score"] = suitability_score
    profile["horse_intelligence_score"] = intelligence_score

    profile["profile_strengths"] = strengths
    profile["profile_cautions"] = cautions

    profile["enrich_version"] = ENRICH_VERSION
    profile["enrich_signature"] = get_profile_signature(profile)

    return profile


def enrich_horse_profiles():
    if not PROFILE_DIR.exists():
        print(f"No horse profile folder found: {PROFILE_DIR}")
        return

    files = list(PROFILE_DIR.glob("*.json"))

    enriched = 0
    skipped = 0
    failed = 0

    for file_path in files:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                profile = json.load(f)

            if profile_already_enriched(profile):
                skipped += 1
                continue

            profile = enrich_profile(profile)

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, separators=(",", ":"))

            enriched += 1

        except Exception as exc:
            failed += 1
            print(f"Failed to enrich {file_path.name}: {exc}")

    print(f"Horse profiles found: {len(files)}")
    print(f"Horse profiles enriched: {enriched}")
    print(f"Horse profiles skipped: {skipped}")
    print(f"Horse profiles failed: {failed}")


if __name__ == "__main__":
    enrich_horse_profiles()
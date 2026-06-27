import json
from pathlib import Path


PROFILE_DIR = Path("data/horses/profiles")
REPORT_DIR = Path("data/horses/performance_reports")
OUTPUT_DIR = Path("data/horses/learning")


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


def same_value(a, b):
    return str(a or "").lower().strip() == str(b or "").lower().strip()


def load_latest_report():
    reports = sorted(REPORT_DIR.glob("*.json"))

    if not reports:
        return None

    with reports[-1].open("r", encoding="utf-8") as f:
        return json.load(f)


def load_profile(name):
    file_path = PROFILE_DIR / f"{slugify(name)}.json"

    if not file_path.exists():
        return None

    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def add_signal(learning, signal, reason):
    learning["signals"].append(
        {
            "signal": signal,
            "reason": reason,
        }
    )


def build_learning():
    report = load_latest_report()

    if report is None:
        print("No performance report found.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    learned = 0

    for miss in report["misses"]:
        profile = load_profile(miss["winner"])

        if profile is None:
            continue

        learning = {
            "date": report.get("date"),
            "horse": miss["winner"],
            "pulse_rank": miss["winner_rank"],
            "winner": True,
            "sp": miss["sp"],
            "course": miss["course"],
            "time": miss["time"],
            "top_pick": miss.get("top_pick"),
            "top_pick_score": miss.get("top_pick_score"),
            "winner_score": miss.get("winner_score"),
            "signals": [],
            "profile_snapshot": {
                "average_pulse_score": profile.get("average_pulse_score"),
                "latest_pulse_score": profile.get("latest_pulse_score"),
                "horse_intelligence_score": profile.get("horse_intelligence_score"),
                "suitability_score": profile.get("suitability_score"),
                "profile_runs": profile.get("profile_runs"),
                "favourite_course": profile.get("favourite_course"),
                "favourite_distance": profile.get("favourite_distance"),
                "favourite_going": profile.get("favourite_going"),
                "favourite_class": profile.get("favourite_class"),
            },
        }

        favourite_course = profile.get("favourite_course") or {}
        favourite_distance = profile.get("favourite_distance") or {}
        favourite_going = profile.get("favourite_going") or {}
        favourite_class = profile.get("favourite_class") or {}

        if same_value(miss["course"], favourite_course.get("value")):
            add_signal(
                learning,
                "Favourite course matched",
                f"Winner ran at its most common course: {miss['course']}",
            )

        if same_value(profile.get("latest_distance_f"), favourite_distance.get("value")):
            add_signal(
                learning,
                "Favourite distance matched",
                f"Winner ran at its most common distance: {profile.get('latest_distance_f')}f",
            )

        if same_value(profile.get("latest_going"), favourite_going.get("value")):
            add_signal(
                learning,
                "Favourite going matched",
                f"Winner ran on its most common going: {profile.get('latest_going')}",
            )

        if same_value(profile.get("latest_class"), favourite_class.get("value")):
            add_signal(
                learning,
                "Favourite class matched",
                f"Winner ran at its most common class: {profile.get('latest_class')}",
            )

        if (profile.get("average_pulse_score") or 0) >= 65:
            add_signal(
                learning,
                "Strong average Pulse profile",
                f"Average Pulse Score was {profile.get('average_pulse_score')}",
            )

        if (profile.get("horse_intelligence_score") or 0) >= 65:
            add_signal(
                learning,
                "Strong horse intelligence profile",
                f"Horse Intelligence was {profile.get('horse_intelligence_score')}",
            )

        if (profile.get("suitability_score") or 0) >= 70:
            add_signal(
                learning,
                "Strong suitability profile",
                f"Suitability Score was {profile.get('suitability_score')}",
            )

        if (profile.get("profile_runs") or 0) >= 3:
            add_signal(
                learning,
                "Stored history available",
                f"Profile had {profile.get('profile_runs')} stored runs",
            )

        for strength in profile.get("profile_strengths", []):
            add_signal(
                learning,
                "Profile strength existed",
                strength,
            )

        for caution in profile.get("profile_cautions", []):
            learning.setdefault("cautions", []).append(caution)

        file_path = OUTPUT_DIR / f"{slugify(learning['horse'])}.json"

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(
                learning,
                f,
                indent=2,
                ensure_ascii=False,
            )

        learned += 1

    print(f"Learning reports created: {learned}")


if __name__ == "__main__":
    build_learning()
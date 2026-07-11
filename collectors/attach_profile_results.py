import json
import re
from datetime import datetime
from pathlib import Path


PROFILE_DIR = Path("data/horses/profiles")
RESULT_DIR = Path("data/horses/runner_results")


def normalise(value):
    value = str(value or "").lower().strip()

    value = re.sub(
        r"\((aw|gb|ire|fr|usa|aus)\)",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.replace("&", "and")
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def parse_datetime(value):
    value = str(value or "").strip()

    if not value:
        return datetime.min

    value = value.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except Exception:
        return datetime.min


def load_jsonl(file_path):
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    return rows


def load_latest_results():
    latest_by_horse = {}

    if not RESULT_DIR.exists():
        return latest_by_horse

    for file_path in sorted(RESULT_DIR.glob("*.jsonl")):
        for row in load_jsonl(file_path):
            horse = row.get("horse")
            position = row.get("finish_position")

            if not horse or position is None:
                continue

            if row.get("status_runner") == "NonRunner":
                continue

            horse_key = normalise(horse)

            result_date = (
                row.get("result_date")
                or row.get("collection_date")
                or ""
            )

            stored_at = row.get("_stored_at") or ""

            result_sort_key = (
                result_date,
                parse_datetime(stored_at),
            )

            current = latest_by_horse.get(horse_key)

            if current and current["_sort_key"] >= result_sort_key:
                continue

            latest_by_horse[horse_key] = {
                "_sort_key": result_sort_key,
                "source": row.get("source"),
                "result_date": result_date,
                "course": row.get("course"),
                "race_time": row.get("race_time"),
                "race_name": row.get("race_name"),
                "race_id": row.get("race_id"),
                "status": row.get("status"),
                "finish_position": position,
                "sp": row.get("sp"),
                "favourite_position": row.get("favourite_position"),
                "going": row.get("going"),
                "distance": row.get("distance"),
                "field_size": row.get("field_size"),
                "trainer": row.get("trainer"),
                "jockey": row.get("jockey"),
                "distance_beaten": row.get("distance_beaten"),
                "won": str(position) == "1",
                "placed": str(position) in {"1", "2", "3"},
                "attached_at": datetime.now().isoformat(timespec="seconds"),
            }

    for result in latest_by_horse.values():
        result.pop("_sort_key", None)

    return latest_by_horse


def get_profile_horse_name(profile, file_path):
    return (
        profile.get("horse")
        or profile.get("horse_name")
        or profile.get("name")
        or file_path.stem
    )


def result_changed(profile, latest_result):
    current = profile.get("latest_result")

    if not current:
        return True

    tracked_fields = [
        "result_date",
        "course",
        "race_time",
        "race_id",
        "finish_position",
        "sp",
    ]

    return any(
        current.get(field) != latest_result.get(field)
        for field in tracked_fields
    )


def attach_profile_results():
    if not PROFILE_DIR.exists():
        print(f"No horse profile folder found: {PROFILE_DIR}")
        return

    latest_results = load_latest_results()
    profile_files = list(PROFILE_DIR.glob("*.json"))

    attached = 0
    unchanged = 0
    no_result = 0
    failed = 0

    for file_path in profile_files:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                profile = json.load(f)

            horse_name = get_profile_horse_name(profile, file_path)
            horse_key = normalise(horse_name)
            latest_result = latest_results.get(horse_key)

            if not latest_result:
                no_result += 1
                continue

            if not result_changed(profile, latest_result):
                unchanged += 1
                continue

            profile["latest_result"] = latest_result
            profile["latest_result_position"] = latest_result.get(
                "finish_position"
            )
            profile["latest_result_sp"] = latest_result.get("sp")
            profile["latest_result_won"] = latest_result.get("won")
            profile["latest_result_placed"] = latest_result.get("placed")
            profile["latest_result_date"] = latest_result.get("result_date")

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(
                    profile,
                    f,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

            attached += 1

        except Exception as exc:
            failed += 1
            print(f"Failed to update {file_path.name}: {exc}")

    print("=" * 60)
    print("HORSE PROFILE RESULTS ATTACHMENT")
    print("=" * 60)
    print(f"Profiles found:        {len(profile_files)}")
    print(f"Unique horse results:  {len(latest_results)}")
    print(f"Results attached:      {attached}")
    print(f"Already current:       {unchanged}")
    print(f"No matching result:    {no_result}")
    print(f"Failed:                {failed}")


if __name__ == "__main__":
    attach_profile_results()
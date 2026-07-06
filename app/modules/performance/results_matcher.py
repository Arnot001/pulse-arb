import json
from pathlib import Path


ODDS_DIR = Path("data/horses/odds_snapshots")
RESULT_DIRS = [
    Path("data/horses/sporting_life_results"),
    Path("data/horses/public_results"),
]


def normalise(value):
    return str(value or "").lower().strip()


def load_jsonl_files(folder):
    rows = []

    if not folder.exists():
        return rows

    for file_path in sorted(folder.glob("*.jsonl")):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass

    return rows


def load_odds_snapshots():
    return load_jsonl_files(ODDS_DIR)


def load_results():
    rows = []

    for folder in RESULT_DIRS:
        rows.extend(load_jsonl_files(folder))

    return rows


def build_result_index(results):
    index = {}

    for row in results:
        raw = row.get("raw", row)

        course = raw.get("course")
        race_time = (
            raw.get("race_time")
            or raw.get("off_time")
            or raw.get("time")
        )

        for runner in raw.get("positions", []):
            horse = runner.get("horse")
            position = runner.get("position")

            key = (
                normalise(course),
                normalise(race_time),
                normalise(horse),
            )

            index[key] = {
                "course": course,
                "race_time": race_time,
                "horse": horse,
                "position": position,
                "sp": runner.get("sp"),
                "favourite": runner.get("favourite"),
                "race_name": raw.get("race_name"),
                "race_stage": raw.get("race_stage"),
            }

    return index


def match_snapshots_to_results():
    snapshots = load_odds_snapshots()
    results = load_results()
    index = build_result_index(results)

    matched = []
    unmatched = []

    for bet in snapshots:
        key = (
            normalise(bet.get("course")),
            normalise(bet.get("race_time")),
            normalise(bet.get("horse")),
        )

        result = index.get(key)

        if not result:
            unmatched.append(bet)
            continue

        position = (
            result.get("position")
            or result.get("pos")
            or result.get("finishing_position")
        )

        won = str(position) == "1"

        enriched = dict(bet)
        enriched["result_position"] = position
        enriched["won"] = won
        enriched["result_matched"] = True

        matched.append(enriched)

    return {
        "snapshots": len(snapshots),
        "results": len(results),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "matched_rows": matched,
        "unmatched_rows": unmatched[:20],
    }


if __name__ == "__main__":
    report = match_snapshots_to_results()

    print("Snapshots:", report["snapshots"])
    print("Results:", report["results"])
    print("Matched:", report["matched"])
    print("Unmatched:", report["unmatched"])
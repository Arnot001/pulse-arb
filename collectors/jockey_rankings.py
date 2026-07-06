import json
from pathlib import Path
from collections import defaultdict
from app.data_store import append_jsonl, get_week_key

DEDupe_KEYS = set()


def should_store(key):
    if key in DEDupe_KEYS:
        return False

    DEDupe_KEYS.add(key)
    return True

def safe_score(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def build_jockey_rankings():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "pulse_scores" / f"{week_key}.jsonl"

    if not file_path.exists():
        print(f"No pulse scores found: {file_path}")
        return

    jockeys = defaultdict(lambda: {
        "jockey": None,
        "jockey_id": None,
        "rides": 0,
        "total_score": 0,
        "top_rated": 0,
    })

    seen_runners = set()
    bad_lines = 0

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                runner = json.loads(line)
            except Exception:
                bad_lines += 1
                continue

            runner_key = f'{runner.get("race_id")}:{runner.get("horse_id")}'
            if runner_key in seen_runners:
                continue
            seen_runners.add(runner_key)

            jockey_id = runner.get("jockey_id") or runner.get("jockey")
            jockey_name = runner.get("jockey")

            if not jockey_id or not jockey_name or jockey_name == "Non Runner":
                continue

            score = safe_score(runner.get("pulse_score"))

            jockeys[jockey_id]["jockey"] = jockey_name
            jockeys[jockey_id]["jockey_id"] = jockey_id
            jockeys[jockey_id]["rides"] += 1
            jockeys[jockey_id]["total_score"] += score

            if score >= 70:
                jockeys[jockey_id]["top_rated"] += 1

    saved = 0
    skipped = 0

    for jockey in jockeys.values():
        rides = jockey["rides"]

        if rides <= 0:
            continue

        avg_score = round(jockey["total_score"] / rides, 2)

        record = {
            "source": "pulse_horses",
            "week": week_key,
            "jockey": jockey["jockey"],
            "jockey_id": jockey["jockey_id"],
            "rides": rides,
            "average_pulse_score": avg_score,
            "top_rated_rides": jockey["top_rated"],
        }

        key = f'jockey_rank:{week_key}:{record["jockey_id"]}:{avg_score}:{rides}'

        if not should_store(key):
            skipped += 1
            continue

        append_jsonl(
            sport="horses",
            data_type="jockey_rankings",
            record=record,
        )

        saved += 1

    print(f"Saved {saved} jockey ranking records.")
    print(f"Skipped {skipped} duplicate jockey ranking records.")
    print(f"Bad pulse score lines skipped: {bad_lines}")


if __name__ == "__main__":
    build_jockey_rankings()
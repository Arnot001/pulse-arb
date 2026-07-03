import json
from pathlib import Path

from app.data_store import get_week_key
from app.modules.horses.scoring import calculate_horse_score


SCORE_VERSION = "horse_score_v6"


def load_existing_score_keys(output_path):
    existing = set()

    if not output_path.exists():
        return existing

    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            key = (
                f'{SCORE_VERSION}:'
                f'{record.get("race_id")}:'
                f'{record.get("horse_id")}:'
                f'{record.get("pulse_score")}'
            )

            existing.add(key)

    return existing


def save_horse_scores():
    week_key = get_week_key()

    input_path = (
        Path("data")
        / "horses"
        / "runner_records"
        / f"{week_key}.jsonl"
    )

    output_dir = (
        Path("data")
        / "horses"
        / "pulse_scores"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{week_key}.jsonl"

    if not input_path.exists():
        print(f"No runner records found: {input_path}")
        return

    existing_score_keys = load_existing_score_keys(output_path)

    saved = 0
    skipped = 0
    duplicate_runners = 0
    seen_runners = set()
    new_records = []

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            runner = json.loads(line)

            runner_key = (
                f'{runner.get("race_id")}:'
                f'{runner.get("horse_id")}'
            )

            if runner_key in seen_runners:
                duplicate_runners += 1
                continue

            seen_runners.add(runner_key)

            result = calculate_horse_score(runner)

            score_key = (
                f'{SCORE_VERSION}:'
                f'{runner.get("race_id")}:'
                f'{runner.get("horse_id")}:'
                f'{result["pulse_score"]}'
            )

            if score_key in existing_score_keys:
                skipped += 1
                continue

            record = {
                **runner,
                "score_version": SCORE_VERSION,
                "pulse_score": result["pulse_score"],
                "notes": result["notes"],
                "factors": result.get("factors", {}),
                "value_rating": result.get("value_rating"),
            }

            new_records.append(record)
            existing_score_keys.add(score_key)
            saved += 1

    if new_records:
        with output_path.open("a", encoding="utf-8") as f:
            for record in new_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Saved {saved} horse pulse scores.")
    print(f"Skipped {skipped} duplicate horse pulse scores.")
    print(f"Skipped {duplicate_runners} duplicate runner records.")


if __name__ == "__main__":
    save_horse_scores()
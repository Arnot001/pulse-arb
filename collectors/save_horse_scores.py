import json
from pathlib import Path

from app.data_store import append_jsonl, get_week_key
from app.dedupe import should_store
from app.modules.horses.scoring import calculate_horse_score


def save_horse_scores():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "runner_records" / f"{week_key}.jsonl"

    if not file_path.exists():
        print(f"No runner records found: {file_path}")
        return

    saved = 0
    skipped = 0
    seen = set()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            runner = json.loads(line)
            runner_key = f'{runner.get("race_id")}:{runner.get("horse_id")}'

            if runner_key in seen:
                continue
            seen.add(runner_key)

            result = calculate_horse_score(runner)

            score_key = (
                f'horse_score_v5:'
                f'{runner.get("race_id")}:'
                f'{runner.get("horse_id")}:'
                f'{result["pulse_score"]}'
            )

            if not should_store(score_key):
                skipped += 1
                continue

            record = {
                **runner,
                "pulse_score": result["pulse_score"],
                "notes": result["notes"],
                "factors": result.get("factors", {}),
                "value_rating": result.get("value_rating"),
            }

            append_jsonl(
                sport="horses",
                data_type="pulse_scores",
                record=record,
            )

            saved += 1

    print(f"Saved {saved} horse pulse scores.")
    print(f"Skipped {skipped} duplicate horse pulse scores.")


if __name__ == "__main__":
    save_horse_scores()
import json
from pathlib import Path
from collections import defaultdict

from app.data_store import append_jsonl, get_week_key
from app.dedupe import should_store


def build_trainer_rankings():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "pulse_scores" / f"{week_key}.jsonl"

    if not file_path.exists():
        print(f"No pulse scores found: {file_path}")
        return

    trainers = defaultdict(lambda: {
        "trainer": None,
        "trainer_id": None,
        "runs": 0,
        "total_score": 0,
        "top_rated": 0,
    })

    seen_runners = set()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            runner = json.loads(line)

            runner_key = f'{runner.get("race_id")}:{runner.get("horse_id")}'
            if runner_key in seen_runners:
                continue
            seen_runners.add(runner_key)

            trainer_id = runner.get("trainer_id") or runner.get("trainer")
            trainer_name = runner.get("trainer")

            if not trainer_id:
                continue

            score = runner.get("pulse_score", 0)

            trainers[trainer_id]["trainer"] = trainer_name
            trainers[trainer_id]["trainer_id"] = trainer_id
            trainers[trainer_id]["runs"] += 1
            trainers[trainer_id]["total_score"] += score

            if score >= 70:
                trainers[trainer_id]["top_rated"] += 1

    saved = 0
    skipped = 0

    for trainer in trainers.values():
        runs = trainer["runs"]

        if runs <= 0:
            continue

        avg_score = round(trainer["total_score"] / runs, 2)

        record = {
            "source": "pulse_horses",
            "week": week_key,
            "trainer": trainer["trainer"],
            "trainer_id": trainer["trainer_id"],
            "runs": runs,
            "average_pulse_score": avg_score,
            "top_rated_runners": trainer["top_rated"],
        }

        key = f'trainer_rank:{week_key}:{record["trainer_id"]}:{avg_score}:{runs}'

        if not should_store(key):
            skipped += 1
            continue

        append_jsonl(
            sport="horses",
            data_type="trainer_rankings",
            record=record,
        )

        saved += 1

    print(f"Saved {saved} trainer ranking records.")
    print(f"Skipped {skipped} duplicate trainer ranking records.")


if __name__ == "__main__":
    build_trainer_rankings()
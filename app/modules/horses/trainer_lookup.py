import json
from pathlib import Path

from app.data_store import get_week_key


def load_trainer_rankings():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "trainer_rankings" / f"{week_key}.jsonl"

    rankings = {}

    if not file_path.exists():
        return rankings

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)
            trainer_id = item.get("trainer_id")

            if trainer_id:
                rankings[trainer_id] = item

    return rankings


def get_trainer_bonus(trainer_id):
    rankings = load_trainer_rankings()
    trainer = rankings.get(trainer_id)

    if not trainer:
        return 0

    avg = trainer.get("average_pulse_score", 0)
    top_rated = trainer.get("top_rated_runners", 0)

    bonus = 0

    if avg >= 70:
        bonus += 3
    elif avg >= 60:
        bonus += 2
    elif avg >= 55:
        bonus += 1
    elif avg < 40:
        bonus -= 2

    if top_rated >= 2:
        bonus += 1

    return bonus
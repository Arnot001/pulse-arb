import json
from pathlib import Path

from app.data_store import get_week_key


def load_jockey_rankings():
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "jockey_rankings" / f"{week_key}.jsonl"

    rankings = {}

    if not file_path.exists():
        return rankings

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)
            jockey_id = item.get("jockey_id")

            if jockey_id:
                rankings[jockey_id] = item

    return rankings


def get_jockey_bonus(jockey_id):
    rankings = load_jockey_rankings()
    jockey = rankings.get(jockey_id)

    if not jockey:
        return 0

    avg = jockey.get("average_pulse_score", 0)
    top_rated = jockey.get("top_rated_rides", 0)

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
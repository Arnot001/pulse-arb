import json
from pathlib import Path

from app.data_store import get_week_key


def get_top_trainers(limit=10):
    week_key = get_week_key()

    file_path = (
        Path("data")
        / "horses"
        / "trainer_rankings"
        / f"{week_key}.jsonl"
    )

    if not file_path.exists():
        return []

    rows = []

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    rows.sort(
        key=lambda x: (
            x.get("average_pulse_score", 0),
            x.get("top_rated_runners", 0),
        ),
        reverse=True,
    )

    return rows[:limit]


def get_top_jockeys(limit=10):
    week_key = get_week_key()

    file_path = (
        Path("data")
        / "horses"
        / "jockey_rankings"
        / f"{week_key}.jsonl"
    )

    if not file_path.exists():
        return []

    rows = []

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    rows.sort(
        key=lambda x: (
            x.get("average_pulse_score", 0),
            x.get("top_rated_rides", 0),
        ),
        reverse=True,
    )

    return rows[:limit]
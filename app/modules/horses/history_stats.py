import json
from pathlib import Path
from collections import defaultdict


RESULTS_DIR = Path("data/horses/public_results")


def normalise(name):
    return str(name or "").strip().lower()


def build_horse_history():
    history = defaultdict(
        lambda: {
            "runs": 0,
            "wins": 0,
            "courses": defaultdict(
                lambda: {
                    "runs": 0,
                    "wins": 0,
                }
            ),
        }
    )

    if not RESULTS_DIR.exists():
        return history

    for file in RESULTS_DIR.glob("*.jsonl"):
        with file.open("r", encoding="utf-8") as f:

            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                race = record.get("raw", {})
                winner = race.get("winner", {})

                horse = winner.get("horse")
                course = race.get("course")

                if not horse:
                    continue

                key = normalise(horse)

                history[key]["runs"] += 1
                history[key]["wins"] += 1

                history[key]["courses"][course]["runs"] += 1
                history[key]["courses"][course]["wins"] += 1

    return history


HORSE_HISTORY = build_horse_history()


def get_horse_history(horse_name):
    return HORSE_HISTORY.get(normalise(horse_name))
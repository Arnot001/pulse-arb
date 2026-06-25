import json
from pathlib import Path


TIP_FILE = Path("data/horses/tipsters/tips.jsonl")


TIP_WEIGHTS = {
    "nap": 8,
    "top tip": 6,
    "watch out for": 3,
    "each way": 3,
    "ew": 3,
    "dark horse": 4,
    "daily tip": 4,
}


def normalise(text):
    return str(text or "").strip().lower()


def load_tipster_tips():
    if not TIP_FILE.exists():
        return []

    tips = []

    with TIP_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                tips.append(json.loads(line))
            except Exception:
                pass

    return tips


def get_tipster_support_for_horse(horse_name):
    horse_key = normalise(horse_name)
    matches = []

    for tip in load_tipster_tips():
        if normalise(tip.get("horse")) == horse_key:
            matches.append(tip)

    return matches


def get_tipster_boost(horse_name):
    matches = get_tipster_support_for_horse(horse_name)

    boost = 0

    for tip in matches:
        tip_type = normalise(tip.get("tip_type"))

        points = 4

        for key, value in TIP_WEIGHTS.items():
            if key in tip_type:
                points = value
                break

        boost += points

    return min(boost, 15), matches
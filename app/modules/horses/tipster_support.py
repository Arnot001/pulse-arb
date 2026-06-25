import json
from pathlib import Path


TIP_FILE = Path("data/horses/tipsters/tips.jsonl")


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

        if "nap" in tip_type:
            boost += 8
        elif "top tip" in tip_type:
            boost += 6
        else:
            boost += 4

    return min(boost, 15), matches
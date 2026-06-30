import json
from pathlib import Path


PROFILE_DIR = Path("data/horses/profiles")
INTELLIGENCE_DIR = Path("data/horses/intelligence")


def slugify(value):
    return (
        str(value or "")
        .lower()
        .replace("&", "and")
        .replace(".", "")
        .replace("'", "")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )


def normalise(value):
    return str(value or "").strip().lower()


def load_horse_intelligence(name):
    if not INTELLIGENCE_DIR.exists():
        return []

    matches = []

    for file in INTELLIGENCE_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                record = json.load(f)
        except Exception:
            continue

        if normalise(record.get("horse")) == normalise(name):
            matches.append(record)

    matches.sort(
        key=lambda item: item.get("off_dt") or item.get("date") or "",
        reverse=True,
    )

    return matches


def get_horse_profile(name: str):
    if not PROFILE_DIR.exists():
        return None

    file_name = slugify(name) + ".json"
    file_path = PROFILE_DIR / file_name

    if not file_path.exists():
        return None

    try:
        with file_path.open("r", encoding="utf-8") as f:
            profile = json.load(f)
    except Exception:
        return None

    intelligence_records = load_horse_intelligence(name)
    latest_intelligence = intelligence_records[0] if intelligence_records else None

    profile["intelligence_records"] = intelligence_records
    profile["latest_intelligence"] = latest_intelligence
    profile["market_events"] = []

    if latest_intelligence:
        profile["market_events"] = latest_intelligence.get("market_events", [])
        profile["result"] = latest_intelligence.get("result")

    return profile
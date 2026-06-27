import json
from pathlib import Path


PROFILE_DIR = Path("data/horses/profiles")


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


def get_horse_profile(name: str):
    if not PROFILE_DIR.exists():
        return None

    file_name = slugify(name) + ".json"
    file_path = PROFILE_DIR / file_name

    if not file_path.exists():
        return None

    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
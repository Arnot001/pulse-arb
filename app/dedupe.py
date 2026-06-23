import json
from pathlib import Path


SEEN_FILE = Path("data") / "_seen_keys.json"


def load_seen_keys():
    if not SEEN_FILE.exists():
        return set()

    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen_keys(keys):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(sorted(keys), indent=2),
        encoding="utf-8",
    )


def should_store(key):
    seen = load_seen_keys()

    if key in seen:
        return False

    seen.add(key)
    save_seen_keys(seen)
    return True
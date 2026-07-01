import json
from datetime import datetime, timezone
from pathlib import Path


STRATEGY_HISTORY_DIR = Path("data/strategy/history")


def save_strategy_history(discoveries, verified_strategies):
    STRATEGY_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)

    filename = now.strftime("%Y-%m-%d_%H-%M-%S.json")
    path = STRATEGY_HISTORY_DIR / filename

    snapshot = {
        "snapshot_at": now.isoformat(),
        "discoveries": discoveries,
        "verified_strategies": verified_strategies,
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return path


def load_history_snapshots():
    if not STRATEGY_HISTORY_DIR.exists():
        return []

    snapshots = []

    for file in sorted(STRATEGY_HISTORY_DIR.glob("*.json")):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                data["_path"] = str(file)
                snapshots.append(data)
        except Exception:
            continue

    return snapshots


def latest_snapshot():
    snapshots = load_history_snapshots()

    if not snapshots:
        return None

    return snapshots[-1]


def previous_snapshot():
    snapshots = load_history_snapshots()

    if len(snapshots) < 2:
        return None

    return snapshots[-2]
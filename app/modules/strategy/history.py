import json
from datetime import datetime, timezone
from pathlib import Path


STRATEGY_HISTORY_DIR = Path("data/strategy/history")


def save_strategy_history(discoveries, verified_strategies):
    STRATEGY_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    filename = f"{now.date().isoformat()}.json"
    path = STRATEGY_HISTORY_DIR / filename

    snapshot = {
        "snapshot_at": now.isoformat(),
        "discoveries": discoveries,
        "verified_strategies": verified_strategies,
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return path
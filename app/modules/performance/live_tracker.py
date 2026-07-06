import json
from pathlib import Path

LEDGER = Path("data/betting/bet_ledger_settled.jsonl")


def load_live_status():
    statuses = {}

    if not LEDGER.exists():
        return statuses

    with LEDGER.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            bet = json.loads(line)

            key = (
                bet.get("horse", "").lower().strip(),
                bet.get("course", "").lower().strip(),
                bet.get("race_time", "").strip(),
            )

            statuses[key] = {
                "status": bet.get("status", "WAITING"),
                "position": bet.get("result_position"),
                "sp": bet.get("sp"),
                "returned": bet.get("returned"),
                "profit": bet.get("profit"),
            }

    return statuses
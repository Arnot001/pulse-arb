import json
from pathlib import Path


ODDS_DIR = Path("data/horses/odds_snapshots")


def load_snapshots():
    rows = []

    if not ODDS_DIR.exists():
        return rows

    for file_path in sorted(ODDS_DIR.glob("*.jsonl")):
        snapshot_date = file_path.stem

        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    row = json.loads(line)
                    row["snapshot_date"] = row.get("snapshot_date") or snapshot_date
                    rows.append(row)
                except Exception:
                    pass

    return rows


def valid_bets():
    return [
        row for row in load_snapshots()
        if row.get("odds_success")
        and row.get("best_odds_decimal")
    ]


def simulate_level_stakes(stake=1.0):
    bets = valid_bets()
    total_staked = len(bets) * stake

    settled = [
        bet for bet in bets
        if bet.get("won") is not None
    ]

    returned = 0.0

    for bet in settled:
        if bet.get("won"):
            returned += stake * float(bet.get("best_odds_decimal", 0))

    profit = returned - (len(settled) * stake)

    roi = 0.0
    if settled:
        roi = round((profit / (len(settled) * stake)) * 100, 2)

    return {
        "logged_bets": len(bets),
        "settled_bets": len(settled),
        "stake_per_bet": stake,
        "total_logged_stake": round(total_staked, 2),
        "settled_stake": round(len(settled) * stake, 2),
        "returned": round(returned, 2),
        "profit": round(profit, 2),
        "roi": roi,
        "note": "Only settled matched results are included in profit.",
    }


if __name__ == "__main__":
    print(simulate_level_stakes(1.0))
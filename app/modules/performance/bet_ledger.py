import json
from pathlib import Path
from datetime import datetime

from app.modules.performance.bet_qualifier import qualifies_as_official_bet


LEDGER_DIR = Path("data/betting")
LEDGER_FILE = LEDGER_DIR / "bet_ledger.jsonl"
SETTLED_LEDGER_FILE = LEDGER_DIR / "bet_ledger_settled.jsonl"

ODDS_DIR = Path("data/horses/odds_snapshots")

LEDGER_DIR.mkdir(parents=True, exist_ok=True)


def make_bet_id(row):
    parts = [
        row.get("snapshot_date"),
        row.get("course"),
        row.get("race_time"),
        row.get("horse"),
        row.get("strategy"),
    ]

    return "|".join(str(part or "").lower().strip() for part in parts)


def load_jsonl(file_path):
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    return rows

def load_open_bets():
    return load_jsonl(LEDGER_FILE)


def load_settled_bets():
    return load_jsonl(SETTLED_LEDGER_FILE)


def load_official_settled_bets():
    return [
        bet for bet in load_settled_bets()
        if bet.get("official_bet") is True
    ]


def calculate_ledger_stats(bets):
    total = len(bets)
    winners = len([bet for bet in bets if bet.get("won") is True])
    losers = len([bet for bet in bets if bet.get("won") is False])

    stake = sum(float(bet.get("stake") or 0) for bet in bets)
    profit = sum(float(bet.get("profit") or 0) for bet in bets)

    strike_rate = round((winners / total) * 100, 2) if total else 0
    roi = round((profit / stake) * 100, 2) if stake else 0

    return {
        "total": total,
        "winners": winners,
        "losers": losers,
        "stake": round(stake, 2),
        "profit": round(profit, 2),
        "strike_rate": strike_rate,
        "roi": roi,
    }


def get_verified_official_stats():
    return calculate_ledger_stats(load_official_settled_bets())


def get_all_settled_stats():
    return calculate_ledger_stats(load_settled_bets())

def load_existing_ledger():
    rows = load_jsonl(LEDGER_FILE)
    return {row.get("bet_id"): row for row in rows if row.get("bet_id")}


def load_odds_snapshots():
    rows = []

    if not ODDS_DIR.exists():
        return rows

    for file_path in sorted(ODDS_DIR.glob("*.jsonl")):
        snapshot_date = file_path.stem

        for row in load_jsonl(file_path):
            row["snapshot_date"] = row.get("snapshot_date") or snapshot_date
            rows.append(row)

    return rows


def rebuild_ledger_from_snapshots():
    existing = load_existing_ledger()
    snapshots = load_odds_snapshots()

    added = 0
    skipped = 0

    with LEDGER_FILE.open("a", encoding="utf-8") as f:
        for row in snapshots:
            if not row.get("odds_success"):
                skipped += 1
                continue
            
            decimal_odds = row.get("best_odds_decimal") or 0

            if decimal_odds < 1.5 or decimal_odds > 10:
                skipped += 1
                continue

            bet_id = make_bet_id(row)

            if bet_id in existing:
                skipped += 1
                continue

            qualification = qualifies_as_official_bet(row)

            record = {
                "bet_id": bet_id,
                "status": "OPEN",

                "bet_type": qualification["bet_type"],
                "official_bet": qualification["qualifies"],
                "qualification_reasons": qualification["reasons"],
                "qualification_warnings": qualification["warnings"],

                "created_at": datetime.now().isoformat(timespec="seconds"),
                "date": row.get("snapshot_date"),
                "course": row.get("course"),
                "race_time": row.get("race_time"),
                "race_name": row.get("race_name"),
                "race_id": row.get("race_id"),

                "horse": row.get("horse"),
                "horse_id": row.get("horse_id"),

                "strategy": row.get("strategy"),
                "pulse_score": row.get("pulse_score"),

                "odds_source": row.get("odds_source"),
                "odds_url": row.get("odds_url"),
                "snapshot_time": row.get("snapshot_time"),
                "best_odds": row.get("best_odds"),
                "best_odds_decimal": row.get("best_odds_decimal"),
                "bookmaker": row.get("bookmaker"),

                "result_position": None,
                "sp": None,
                "won": None,

                "stake": 1.0,
                "returned": None,
                "profit": None,
                "roi": None,
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            existing[bet_id] = record
            added += 1

    return {
        "snapshots": len(snapshots),
        "added": added,
        "skipped": skipped,
        "ledger_file": str(LEDGER_FILE),
    }


if __name__ == "__main__":
    report = rebuild_ledger_from_snapshots()

    print("Bet Ledger Updated")
    print("-" * 40)
    print(f"Snapshots checked: {report['snapshots']}")
    print(f"Added: {report['added']}")
    print(f"Skipped: {report['skipped']}")
    print(f"File: {report['ledger_file']}")
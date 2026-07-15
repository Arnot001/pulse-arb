import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from app.modules.performance.each_way import (
    build_racecard_index,
    enrich_bet_with_each_way,
)


LEDGER_FILE = Path("data/betting/bet_ledger.jsonl")
SETTLED_FILE = Path("data/betting/bet_ledger_settled.jsonl")


def load_jsonl(file_path):
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open("r", encoding="utf-8") as file_handle:
        for line in file_handle:
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    return rows


def write_jsonl(file_path, rows):
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file_handle:
        for row in rows:
            file_handle.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )


def backup_file(file_path):
    if not file_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_name(
        f"{file_path.name}.{timestamp}.bak"
    )

    shutil.copy2(file_path, backup_path)

    return backup_path


def run(dry_run=True, force=False):
    racecard_index = build_racecard_index()
    settled_rows = load_jsonl(SETTLED_FILE)
    ledger_rows = load_jsonl(LEDGER_FILE)

    enriched_by_id = {}
    updated = 0
    skipped_existing = 0
    unavailable = 0
    racecard_missing = 0

    new_settled_rows = []

    for row in settled_rows:
        if (
            not force
            and "ew_profit" in row
        ):
            enriched = row
            skipped_existing += 1
        else:
            enriched = enrich_bet_with_each_way(
                row,
                racecard_index=racecard_index,
                unit_stake=float(
                    row.get("stake") or 1.0
                ),
            )
            updated += 1

        if not enriched.get("ew_available"):
            unavailable += 1

        if not enriched.get("ew_racecard_matched"):
            racecard_missing += 1

        bet_id = enriched.get("bet_id")

        if bet_id:
            enriched_by_id[bet_id] = enriched

        new_settled_rows.append(enriched)

    new_ledger_rows = []

    for row in ledger_rows:
        bet_id = row.get("bet_id")

        if (
            row.get("status") == "SETTLED"
            and bet_id in enriched_by_id
        ):
            new_ledger_rows.append(
                enriched_by_id[bet_id]
            )
        else:
            new_ledger_rows.append(row)

    report = {
        "settled_rows": len(settled_rows),
        "updated": updated,
        "skipped_existing": skipped_existing,
        "ew_unavailable": unavailable,
        "racecard_missing": racecard_missing,
        "dry_run": dry_run,
    }

    if dry_run:
        return report

    settled_backup = backup_file(SETTLED_FILE)
    ledger_backup = backup_file(LEDGER_FILE)

    write_jsonl(SETTLED_FILE, new_settled_rows)
    write_jsonl(LEDGER_FILE, new_ledger_rows)

    report["settled_backup"] = (
        str(settled_backup)
        if settled_backup
        else None
    )
    report["ledger_backup"] = (
        str(ledger_backup)
        if ledger_backup
        else None
    )

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Backfill estimated each-way settlement fields "
            "without changing existing win-only values."
        )
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes after creating timestamped backups.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalculate rows that already have E/W fields.",
    )

    args = parser.parse_args()

    report = run(
        dry_run=not args.write,
        force=args.force,
    )

    print("=" * 60)
    print("PULSE EACH-WAY BACKFILL")
    print("=" * 60)
    print(f"Dry run            : {report['dry_run']}")
    print(f"Settled rows       : {report['settled_rows']}")
    print(f"Rows calculated    : {report['updated']}")
    print(f"Existing E/W rows  : {report['skipped_existing']}")
    print(f"E/W unavailable    : {report['ew_unavailable']}")
    print(f"Racecard unmatched : {report['racecard_missing']}")

    if not report["dry_run"]:
        print(f"Settled backup     : {report['settled_backup']}")
        print(f"Ledger backup      : {report['ledger_backup']}")
        print("Write complete.")
    else:
        print()
        print("No files changed.")
        print(
            "Run with --write only after reviewing this report."
        )
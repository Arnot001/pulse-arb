import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app.modules.performance.bet_ledger import (
    LEDGER_FILE,
    SETTLED_LEDGER_FILE,
    ODDS_DIR,
    load_jsonl,
    make_bet_id,
    rebuild_ledger_from_snapshots,
)
from app.modules.performance.settlement import settle_bets


def run_module(label, module, arguments=None):
    arguments = arguments or []

    print()
    print(f"Running: {label}")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            module,
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print(
            f"FAILED: {label} "
            f"(return code {result.returncode})"
        )

    return result.returncode == 0


def save_jsonl(file_path, rows):
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with file_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def clean_decimal_odds(value):
    if value is None:
        return None

    try:
        value = float(value)
    except Exception:
        return None

    if value <= 1.0 or value > 1000:
        return None

    return value


def snapshot_sort_key(row):
    snapshot_time = row.get("snapshot_time") or ""

    try:
        return datetime.fromisoformat(snapshot_time)
    except Exception:
        return datetime.min


def is_valid_pre_race_snapshot(snapshot):
    decimal_odds = clean_decimal_odds(
        snapshot.get("best_odds_decimal")
    )

    if decimal_odds is None:
        return False

    if snapshot.get("odds_success") is False:
        return False

    minutes_before_off = snapshot.get(
        "minutes_before_off"
    )

    if minutes_before_off is not None:
        try:
            minutes_before_off = int(
                minutes_before_off
            )

            # Never recover a price recorded long after
            # the scheduled off.
            if minutes_before_off < -10:
                return False

        except Exception:
            pass

    return True


def load_best_snapshot_index():
    candidates = {}

    if not ODDS_DIR.exists():
        return candidates

    for file_path in sorted(
        ODDS_DIR.glob("*.jsonl")
    ):
        file_date = file_path.stem

        for snapshot in load_jsonl(file_path):
            snapshot = dict(snapshot)

            snapshot["snapshot_date"] = (
                snapshot.get("snapshot_date")
                or snapshot.get("race_date")
                or file_date
            )

            if not is_valid_pre_race_snapshot(snapshot):
                continue

            snapshot["best_odds_decimal"] = (
                clean_decimal_odds(
                    snapshot.get(
                        "best_odds_decimal"
                    )
                )
            )

            bet_id = make_bet_id(snapshot)

            if not bet_id.strip("|"):
                continue

            current = candidates.get(bet_id)

            # Keep the final valid price Pulse captured
            # before the race.
            if (
                current is None
                or snapshot_sort_key(snapshot)
                > snapshot_sort_key(current)
            ):
                candidates[bet_id] = snapshot

    return candidates


def build_bet_id(bet):
    existing = bet.get("bet_id")

    if existing:
        return existing

    return make_bet_id(
        {
            "snapshot_date": bet.get("date"),
            "course": bet.get("course"),
            "race_time": bet.get("race_time"),
            "horse": bet.get("horse"),
            "strategy": (
                bet.get("strategy")
                or "Pulse Top Pick"
            ),
        }
    )


def attach_snapshot_to_bet(bet, snapshot):
    updated = dict(bet)

    updated["odds_source"] = snapshot.get(
        "odds_source"
    )
    updated["odds_url"] = snapshot.get("odds_url")
    updated["snapshot_time"] = snapshot.get(
        "snapshot_time"
    )
    updated["snapshot_date"] = snapshot.get(
        "snapshot_date"
    )
    updated["minutes_before_off"] = snapshot.get(
        "minutes_before_off"
    )
    updated["best_odds"] = snapshot.get(
        "best_odds"
    )
    updated["best_odds_decimal"] = snapshot.get(
        "best_odds_decimal"
    )
    updated["bookmaker"] = snapshot.get(
        "bookmaker"
    )
    updated["odds_available"] = True
    updated["odds_recovered"] = True
    updated["odds_recovered_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    return updated


def recalculate_settled_profit(bet):
    updated = dict(bet)

    decimal_odds = clean_decimal_odds(
        updated.get("best_odds_decimal")
    )

    if decimal_odds is None:
        return updated, False

    if updated.get("won") is None:
        return updated, False

    stake = float(
        updated.get("stake") or 1.0
    )

    won = updated.get("won") is True

    returned = (
        stake * decimal_odds
        if won
        else 0.0
    )

    profit = returned - stake

    roi = (
        (profit / stake) * 100
        if stake
        else 0.0
    )

    new_returned = round(returned, 2)
    new_profit = round(profit, 2)
    new_roi = round(roi, 2)

    old_returned = updated.get("returned")
    old_profit = updated.get("profit")
    old_roi = updated.get("roi")

    changed = (
        old_returned != new_returned
        or old_profit != new_profit
        or old_roi != new_roi
    )

    if not changed:
        return updated, False

    updated["stake"] = stake
    updated["returned"] = new_returned
    updated["profit"] = new_profit
    updated["roi"] = new_roi
    updated["profit_recalculated_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    return updated, True


def recover_missing_odds():
    snapshot_index = load_best_snapshot_index()

    ledger_rows = load_jsonl(LEDGER_FILE)
    settled_rows = load_jsonl(
        SETTLED_LEDGER_FILE
    )

    ledger_recovered = 0
    settled_recovered = 0
    profit_recalculated = 0

    updated_ledger = []

    for bet in ledger_rows:
        updated = dict(bet)
        bet_id = build_bet_id(updated)
        updated["bet_id"] = bet_id

        if clean_decimal_odds(
            updated.get("best_odds_decimal")
        ) is None:
            snapshot = snapshot_index.get(bet_id)

            if snapshot:
                updated = attach_snapshot_to_bet(
                    updated,
                    snapshot,
                )

                ledger_recovered += 1

        if updated.get("status") == "SETTLED":
            updated, changed = (
                recalculate_settled_profit(
                    updated
                )
            )

            if changed:
                profit_recalculated += 1

        updated_ledger.append(updated)

    updated_settled = []

    for bet in settled_rows:
        updated = dict(bet)
        bet_id = build_bet_id(updated)
        updated["bet_id"] = bet_id

        if clean_decimal_odds(
            updated.get("best_odds_decimal")
        ) is None:
            snapshot = snapshot_index.get(bet_id)

            if snapshot:
                updated = attach_snapshot_to_bet(
                    updated,
                    snapshot,
                )

                settled_recovered += 1

        updated, changed = (
            recalculate_settled_profit(updated)
        )

        if changed:
            profit_recalculated += 1

        updated_settled.append(updated)

    save_jsonl(
        LEDGER_FILE,
        updated_ledger,
    )

    save_jsonl(
        SETTLED_LEDGER_FILE,
        updated_settled,
    )

    return {
        "snapshots_available": len(
            snapshot_index
        ),
        "ledger_recovered": ledger_recovered,
        "settled_recovered": settled_recovered,
        "profit_recalculated": (
            profit_recalculated
        ),
    }


def get_historical_open_bets():
    today = datetime.now().date().isoformat()

    return [
        bet
        for bet in load_jsonl(LEDGER_FILE)
        if bet.get("status") == "OPEN"
        and str(bet.get("date") or "") < today
    ]


def get_historical_open_dates():
    dates = set()

    for bet in get_historical_open_bets():
        value = str(
            bet.get("date") or ""
        )[:10]

        try:
            valid_date = datetime.strptime(
                value,
                "%Y-%m-%d",
            ).date()

            dates.add(valid_date.isoformat())

        except Exception:
            continue

    return sorted(dates)


def collect_missing_result_dates(dates):
    successful = []
    failed = []

    for target_date in dates:
        ok = run_module(
            (
                "Sporting Life Results "
                f"{target_date}"
            ),
            "collectors.sporting_life_results",
            [
                "--date",
                target_date,
            ],
        )

        if ok:
            successful.append(target_date)
        else:
            failed.append(target_date)

    return {
        "successful": successful,
        "failed": failed,
    }


def run():
    print("=" * 60)
    print("PULSE CATCH-UP ENGINE")
    print("=" * 60)

    open_before = get_historical_open_bets()
    missing_dates = get_historical_open_dates()

    print(
        "Historical open bets before catch-up: "
        f"{len(open_before)}"
    )

    print(
        "Historical dates requiring results: "
        f"{len(missing_dates)}"
    )

    if missing_dates:
        for target_date in missing_dates:
            print(f"- {target_date}")
    else:
        print("- None")

    print()
    print(
        "Running: Rebuild Ledger "
        "From All Snapshots"
    )

    ledger_report = (
        rebuild_ledger_from_snapshots()
    )

    print(
        f"Snapshots checked : "
        f"{ledger_report['snapshots']}"
    )
    print(
        f"New bets added    : "
        f"{ledger_report['added']}"
    )
    print(
        f"Updated with odds : "
        f"{ledger_report.get('updated', 0)}"
    )

    # Recover prices before settlement so newly
    # settled historical bets use the saved price.
    print()
    print("Running: Recover Historical Odds")

    recovery_before = recover_missing_odds()

    print(
        "Successful snapshots indexed : "
        f"{recovery_before['snapshots_available']}"
    )
    print(
        "Ledger prices recovered      : "
        f"{recovery_before['ledger_recovered']}"
    )
    print(
        "Settled prices recovered     : "
        f"{recovery_before['settled_recovered']}"
    )
    print(
        "Profits recalculated         : "
        f"{recovery_before['profit_recalculated']}"
    )

    date_report = collect_missing_result_dates(
        missing_dates
    )

    # Also collect current results so this command
    # remains useful during the race day.
    run_module(
        "Sporting Life Today Results",
        "collectors.sporting_life_results",
        ["--today"],
    )

    run_module(
        "BBC Current Results",
        "collectors.bbc_horse_results",
    )

    print()
    print("Running: Settle Historical Bets")

    settlement = settle_bets(1.0)

    print(
        f"Results indexed  : "
        f"{settlement['results_indexed']}"
    )
    print(
        f"Newly settled    : "
        f"{settlement['newly_settled']}"
    )
    print(
        f"Total settled    : "
        f"{settlement['total_settled']}"
    )
    print(
        f"Still open       : "
        f"{settlement['open']}"
    )

    # Synchronise and recalculate both ledger files
    # after newly settled bets have been written.
    print()
    print(
        "Running: Final Odds and "
        "Profit Reconciliation"
    )

    recovery_after = recover_missing_odds()

    print(
        "Ledger prices recovered      : "
        f"{recovery_after['ledger_recovered']}"
    )
    print(
        "Settled prices recovered     : "
        f"{recovery_after['settled_recovered']}"
    )
    print(
        "Profits recalculated         : "
        f"{recovery_after['profit_recalculated']}"
    )

    run_module(
        "Attach Profile Results",
        "collectors.attach_profile_results",
    )

    historical_open_after = (
        get_historical_open_bets()
    )

    total_odds_recovered = (
        recovery_before["ledger_recovered"]
        + recovery_before["settled_recovered"]
        + recovery_after["ledger_recovered"]
        + recovery_after["settled_recovered"]
    )

    total_profit_recalculations = (
        recovery_before["profit_recalculated"]
        + recovery_after["profit_recalculated"]
    )

    print()
    print("=" * 60)
    print("CATCH-UP COMPLETE")
    print("=" * 60)

    print(
        f"Historical open before : "
        f"{len(open_before)}"
    )
    print(
        f"Dates requested        : "
        f"{len(missing_dates)}"
    )
    print(
        f"Dates downloaded       : "
        f"{len(date_report['successful'])}"
    )
    print(
        f"Date downloads failed  : "
        f"{len(date_report['failed'])}"
    )
    print(
        f"Newly settled          : "
        f"{settlement['newly_settled']}"
    )
    print(
        f"Historical open after  : "
        f"{len(historical_open_after)}"
    )
    print(
        f"Odds recovered         : "
        f"{total_odds_recovered}"
    )
    print(
        f"Profits recalculated   : "
        f"{total_profit_recalculations}"
    )

    if date_report["failed"]:
        print()
        print("Failed result dates:")

        for target_date in date_report["failed"]:
            print(f"- {target_date}")

    if settlement.get("unmatched_samples"):
        print()
        print("Still unmatched:")

        for item in settlement[
            "unmatched_samples"
        ]:
            print(
                f"- {item['date']} | "
                f"{item['course']} | "
                f"{item['race_time']} | "
                f"{item['horse']}"
            )

    return {
        "ledger": ledger_report,
        "date_report": date_report,
        "recovery_before": recovery_before,
        "recovery_after": recovery_after,
        "settlement": settlement,
        "historical_open_after": len(
            historical_open_after
        ),
    }


if __name__ == "__main__":
    run()
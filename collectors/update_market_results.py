import subprocess
import sys

from app.modules.performance.bet_ledger import (
    rebuild_ledger_from_snapshots,
    get_all_settled_stats,
    get_verified_official_stats,
)
from app.modules.performance.settlement import settle_bets


def run_module(label, module):
    print(f"\nRunning: {label}")

    result = subprocess.run(
        [sys.executable, "-m", module],
        text=True,
        capture_output=True,
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    return result.returncode == 0


def run():
    print("=" * 60)
    print("PULSE LIVE RESULTS UPDATE")
    print("=" * 60)

    # 1. Pull newly finished race results.
    bbc_ok = run_module(
        "BBC Horse Results",
        "collectors.bbc_horse_results",
    )

    if not bbc_ok:
        print("FAILED: BBC Horse Results")
        return

    # 2. Import any odds snapshots not yet added to the ledger.
    print("\nRunning: Update Bet Ledger")
    ledger_report = rebuild_ledger_from_snapshots()

    print(f"Snapshots checked : {ledger_report['snapshots']}")
    print(f"New bets added    : {ledger_report['added']}")
    print(f"Snapshots skipped : {ledger_report['skipped']}")

    # 3. Settle newly completed ledger bets.
    print("\nRunning: Settle Bet Ledger")
    settlement = settle_bets(1.0)

    # 4. Attach completed results to horse intelligence profiles.
    profiles_ok = run_module(
        "Attach Profile Results",
        "collectors.attach_profile_results",
    )

    if not profiles_ok:
        print("WARNING: Horse profile result attachment failed")

    # 5. Read live stats directly from the settled ledger.
    all_stats = get_all_settled_stats()
    official_stats = get_verified_official_stats()

    print("\n" + "=" * 60)
    print("LIVE SETTLEMENT SUMMARY")
    print("=" * 60)

    print(f"Results indexed  : {settlement['results_indexed']}")
    print(f"Already settled  : {settlement['already_settled']}")
    print(f"Newly settled    : {settlement['newly_settled']}")
    print(f"Total settled    : {settlement['total_settled']}")
    print(f"Open bets        : {settlement['open']}")

    print("\nALL PULSE PICKS")
    print(f"Settled          : {all_stats['total']}")
    print(f"Winners          : {all_stats['winners']}")
    print(f"Profit           : {all_stats['profit']} pts")
    print(f"ROI              : {all_stats['roi']}%")

    print("\nOFFICIAL PULSE")
    print(f"Settled          : {official_stats['total']}")
    print(f"Winners          : {official_stats['winners']}")
    print(f"Profit           : {official_stats['profit']} pts")
    print(f"ROI              : {official_stats['roi']}%")

    print("=" * 60)
    print("✓ Pulse live results update complete.")


if __name__ == "__main__":
    run()
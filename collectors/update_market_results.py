import subprocess
import sys

from app.modules.notifications import (
    send_new_settlement_notifications,
)
from app.modules.performance.bet_ledger import (
    rebuild_ledger_from_snapshots,
    get_all_settled_stats,
    get_verified_official_stats,
    load_settled_bets,
)
from app.modules.performance.settlement import settle_bets


def run_module(label, module):
    print(
        f"\nRunning: {label}",
        flush=True,
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            module,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    if process.stdout:
        for line in process.stdout:
            print(
                line,
                end="",
                flush=True,
            )

    return_code = process.wait()

    return return_code == 0


def get_bet_key(bet):
    return (
        bet.get("bet_id")
        or "|".join(
            [
                str(bet.get("date") or ""),
                str(bet.get("course") or ""),
                str(bet.get("race_time") or ""),
                str(bet.get("horse") or ""),
            ]
        )
    )


def run():
    print("=" * 60)
    print("PULSE LIVE RESULTS UPDATE")
    print("=" * 60)

    # 1. Capture approaching-race prices for ROI.
    odds_ok = run_module(
        "Horse Odds Snapshots",
        "collectors.horse_odds_snapshots",
    )

    if not odds_ok:
        print(
            "WARNING: Horse odds snapshot update failed. "
            "Live processing will continue."
        )

    # 2. Refresh rolling market intelligence.
    #
    # This is deliberately separate from frozen bet prices.
    # It repeatedly samples Oddschecker so steamers and drifters
    # can be detected over time.
    market_ok = run_module(
        "Live Market Movers",
        "collectors.live_oddschecker_once",
    )

    if not market_ok:
        print(
            "WARNING: Live market mover update failed. "
            "Results collection will continue."
        )

    # 3. Turn snapshot rows into ledger entries.
    print("\nRunning: Update Bet Ledger")

    try:
        ledger_report = rebuild_ledger_from_snapshots()

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
        print(
            f"Snapshots skipped : "
            f"{ledger_report['skipped']}"
        )

    except Exception as exc:
        print(f"FAILED: Update Bet Ledger - {exc}")
        return

    settled_before = load_settled_bets()

    settled_before_ids = {
        get_bet_key(bet)
        for bet in settled_before
    }

    # 4. Pull newly finished race results.
    bbc_ok = run_module(
        "BBC Horse Results",
        "collectors.bbc_horse_results",
    )

    if not bbc_ok:
        print("FAILED: BBC Horse Results")
        return

    # 5. Settle completed bets.
    print("\nRunning: Settle Bet Ledger")

    try:
        settlement = settle_bets(1.0)

    except Exception as exc:
        print(f"FAILED: Settle Bet Ledger - {exc}")
        return

    settled_after = load_settled_bets()

    newly_settled_bets = [
        bet
        for bet in settled_after
        if get_bet_key(bet) not in settled_before_ids
    ]

    # 6. Send Discord / Telegram notifications.
    try:
        notification_report = (
            send_new_settlement_notifications(
                newly_settled_bets
            )
        )

        if notification_report.get("sent"):
            print(
                "Notifications sent: "
                f"Discord={notification_report['discord']} | "
                f"Telegram={notification_report['telegram']} | "
                f"Bets={notification_report['bets']}"
            )

        elif notification_report.get("errors"):
            print("Notification errors:")

            for error in notification_report["errors"]:
                print(f"- {error}")

        else:
            print(
                "Notifications: "
                f"{notification_report.get('reason')}"
            )

    except Exception as exc:
        print(f"WARNING: Notification step failed - {exc}")

    # 7. Attach completed results to horse profiles.
    profiles_ok = run_module(
        "Attach Profile Results",
        "collectors.attach_profile_results",
    )

    if not profiles_ok:
        print(
            "WARNING: Horse profile result "
            "attachment failed"
        )

    # 8. Read fresh performance totals.
    all_stats = get_all_settled_stats()
    official_stats = get_verified_official_stats()

    print("\n" + "=" * 60)
    print("LIVE SETTLEMENT SUMMARY")
    print("=" * 60)

    print(
        f"Results indexed  : "
        f"{settlement['results_indexed']}"
    )
    print(
        f"Already settled  : "
        f"{settlement['already_settled']}"
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
        f"Open bets        : "
        f"{settlement['open']}"
    )

    print("\nALL PULSE PICKS")
    print(f"Settled          : {all_stats['total']}")
    print(f"Winners          : {all_stats['winners']}")
    print(
        f"Priced bets      : "
        f"{all_stats.get('priced_total', 0)}"
    )
    print(f"Profit           : {all_stats['profit']} pts")
    print(f"ROI              : {all_stats['roi']}%")

    print("\nOFFICIAL PULSE")
    print(f"Settled          : {official_stats['total']}")
    print(f"Winners          : {official_stats['winners']}")
    print(
        f"Priced bets      : "
        f"{official_stats.get('priced_total', 0)}"
    )
    print(
        f"Profit           : "
        f"{official_stats['profit']} pts"
    )
    print(f"ROI              : {official_stats['roi']}%")

    print("=" * 60)
    print("OK - Pulse live results update complete.")


if __name__ == "__main__":
    run()
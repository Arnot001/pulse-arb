from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
from pathlib import Path

from app.modules.arbitrage.engine import engine
from app.modules.arbitrage.scanner import scan_market


LIVE_MARKET_DIR = Path(
    "data/horses/live_market"
)


def load_latest_snapshot():
    files = sorted(
        LIVE_MARKET_DIR.glob("*.jsonl"),
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            "No live market JSONL files found."
        )

    for file_path in files:
        lines = file_path.read_text(
            encoding="utf-8"
        ).splitlines()

        for line in reversed(lines):
            if not line.strip():
                continue

            try:
                snapshot = json.loads(line)
            except json.JSONDecodeError:
                continue

            if snapshot.get("runners"):
                return snapshot

    raise RuntimeError(
        "No usable snapshot with runners found."
    )


def main():
    snapshot = load_latest_snapshot()

    market = engine.load_snapshot(
        snapshot
    )

    analysis = scan_market(
        market
    )

    print("=" * 70)
    print("PULSE HORSE ARB TEST")
    print("=" * 70)

    print(
        f"Race: {analysis.get('race') or 'Unknown'}"
    )

    print(
        f"Course: {analysis.get('course') or 'Unknown'}"
    )

    print(
        f"Runners: {analysis['runner_count']}"
    )

    print(
        "Market percentage: "
        f"{analysis['overround'] * 100:.2f}%"
    )

    print(
        "Back/Back Arb: "
        f"{analysis['back_back_possible']}"
    )

    arb = analysis.get(
        "back_back_arb"
    )

    if not arb:
        print()
        print("No back/back arbitrage found.")
        return

    print()
    print("=" * 70)
    print("BACK/BACK ARBITRAGE FOUND")
    print("=" * 70)

    print(
        f"Market Percentage: "
        f"{arb['market_percentage']:.2f}%"
    )

    print(
        f"Total Stake: "
        f"£{arb['total_stake']:.2f}"
    )

    print(
        f"Guaranteed Return: "
        f"£{arb['guaranteed_return']:.2f}"
    )

    print(
        f"Guaranteed Profit: "
        f"£{arb['guaranteed_profit']:.2f}"
    )

    print(
        f"ROI: {arb['roi']:.2f}%"
    )

    print()
    print("BET INSTRUCTIONS")
    print("-" * 70)

    for bet in arb["bets"]:
        print(
            f"{bet['horse']} | "
            f"{bet['bookmaker']} | "
            f"{bet['decimal']:.2f} | "
            f"Stake £{bet['stake']:.2f} | "
            f"Return £{bet['return']:.2f}"
        )


if __name__ == "__main__":
    main()
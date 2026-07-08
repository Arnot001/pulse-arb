from datetime import datetime

from app.modules.performance.bet_ledger import load_jsonl, LEDGER_FILE
from app.modules.performance.settlement import settle_bets


def run():
    bets = load_jsonl(LEDGER_FILE)

    open_bets = [
        bet for bet in bets
        if bet.get("status") == "OPEN"
    ]

    if not open_bets:
        print("No open bets.")
        return

    now = datetime.now()

    eligible = []

    for bet in open_bets:
        try:
            race_dt = datetime.strptime(
                f"{bet['date']} {bet['race_time']}",
                "%Y-%m-%d %H:%M",
            )

            # wait 10 minutes after scheduled off
            if now >= race_dt.replace(minute=race_dt.minute) and (now - race_dt).total_seconds() >= 600:
                eligible.append(bet)

        except Exception:
            continue

    print(f"Open bets: {len(open_bets)}")
    print(f"Eligible for settlement: {len(eligible)}")

    if not eligible:
        print("Nothing to settle yet.")
        return

    report = settle_bets()

    print(report)


if __name__ == "__main__":
    run()
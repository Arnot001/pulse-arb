import time
from datetime import datetime

from collectors.catch_up_results import run as run_catch_up
from collectors.update_market_results import (
    run as update_market_results,
)


CHECK_EVERY_SECONDS = 300


def run_loop():
    print("=" * 60)
    print("PULSE LIVE ENGINE STARTED")
    print("=" * 60)
    print("Checks every 5 minutes. Press CTRL+C to stop.")

    # Repair anything missed while Pulse was offline before
    # beginning the normal live five-minute cycle.
    try:
        run_catch_up()
    except Exception as exc:
        print(f"Pulse catch-up error: {exc}")
        print(
            "Live monitoring will still start."
        )

    while True:
        print()
        print("-" * 60)
        print(
            "Pulse Live Check: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        print("-" * 60)

        try:
            update_market_results()
        except Exception as exc:
            print(f"Pulse Live Engine error: {exc}")

        print(
            f"Next check in "
            f"{CHECK_EVERY_SECONDS // 60} minutes."
        )

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    run_loop()
import time
from datetime import datetime

from collectors.update_market_results import run as update_market_results


CHECK_EVERY_SECONDS = 300  # 5 minutes


def run_loop():
    print("=" * 60)
    print("PULSE LIVE ENGINE STARTED")
    print("=" * 60)
    print("Checks every 5 minutes. Press CTRL+C to stop.")

    while True:
        print("\n" + "-" * 60)
        print(f"Pulse Live Check: {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 60)

        try:
            update_market_results()
        except Exception as exc:
            print(f"Pulse Live Engine error: {exc}")

        print(f"Next check in {CHECK_EVERY_SECONDS // 60} minutes.")
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    run_loop()
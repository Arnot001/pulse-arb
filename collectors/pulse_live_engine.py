import threading
import time
from datetime import datetime
from typing import Callable, Optional

from collectors.update_market_results import (
    run as update_market_results,
)


CHECK_EVERY_SECONDS = 300
WAIT_CHECK_SECONDS = 2

# Shared with app.main so manual updates and the live engine
# cannot run browser collectors simultaneously.
LIVE_ENGINE_BUSY = threading.Event()


def run_loop(
    is_manual_update_running: Optional[Callable[[], bool]] = None,
    has_manual_update_completed: Optional[Callable[[], bool]] = None,
):
    print("=" * 60)
    print("PULSE LIVE ENGINE STARTED")
    print("=" * 60)
    print("Waiting for the first manual update to complete.")

    def manual_update_running():
        if is_manual_update_running is None:
            return False

        try:
            return bool(is_manual_update_running())
        except Exception as exc:
            print(f"Could not check manual update status: {exc}")
            return False

    def manual_update_completed():
        if has_manual_update_completed is None:
            return False

        try:
            return bool(has_manual_update_completed())
        except Exception as exc:
            print(f"Could not check manual update completion: {exc}")
            return False

    # Pulse Live must not perform its first check until the user has
    # completed at least one manual update during this app session.
    while not manual_update_completed():
        time.sleep(WAIT_CHECK_SECONDS)

    print("Manual update complete.")
    print("Pulse Live monitoring is now active.")
    print(
        f"Checks every "
        f"{CHECK_EVERY_SECONDS // 60} minutes."
    )

    while True:
        # A new manual update may start later. Wait for it to finish
        # rather than skipping the whole five-minute cycle.
        while manual_update_running():
            print(
                "Manual Pulse update is running. "
                "Live monitoring is waiting."
            )
            time.sleep(WAIT_CHECK_SECONDS)

        print()
        print("-" * 60)
        print(
            "Pulse Live Check: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        print("-" * 60)

        LIVE_ENGINE_BUSY.set()

        try:
            update_market_results()
        except Exception as exc:
            print(f"Pulse Live Engine error: {exc}")
        finally:
            LIVE_ENGINE_BUSY.clear()

        print(
            f"Next check in "
            f"{CHECK_EVERY_SECONDS // 60} minutes."
        )

        # Sleep in small chunks so a manual update starting during
        # this period is detected before the next live check.
        slept = 0

        while slept < CHECK_EVERY_SECONDS:
            time.sleep(WAIT_CHECK_SECONDS)
            slept += WAIT_CHECK_SECONDS

            if manual_update_running():
                break


if __name__ == "__main__":
    run_loop()
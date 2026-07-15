from app.browser_manager import get_browser_manager
from collectors.live_oddschecker import (
    collect_all_discovered_races,
)


def run():
    browser_manager = get_browser_manager()

    try:
        browser_manager.start(
            headless=None
        )

        result = collect_all_discovered_races(
            headless=None,
            limit=20,
        )

        print()
        print("=" * 60)
        print("ODDSCHECKER ONE-SHOT UPDATE COMPLETE")
        print("=" * 60)
        print(
            f"Discovered : "
            f"{result.get('discovered', 0)}"
        )
        print(
            f"Saved      : "
            f"{result.get('saved', 0)}"
        )
        print(
            f"Failed     : "
            f"{result.get('failed', 0)}"
        )

    finally:
        browser_manager.stop()


if __name__ == "__main__":
    run()
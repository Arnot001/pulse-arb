import json
import time
from datetime import datetime
from pathlib import Path

from app.modules.horses.routes import get_horse_race_groups
from app.modules.odds.oddschecker import get_best_odds


OUTPUT_DIR = Path("data/horses/odds_snapshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_today_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return OUTPUT_DIR / f"{today}.jsonl"


def snapshot_pulse_picks():
    races = get_horse_race_groups()
    output_file = get_today_file()

    saved = 0
    failed = 0

    with output_file.open("a", encoding="utf-8") as f:
        for race in races:
            pick = race.get("pulse_pick")

            if not pick:
                continue

            course = race.get("course")
            race_time = race.get("time")
            horse = pick.get("horse")

            print(f"Checking odds: {course} {race_time} - {horse}")

            try:
                odds = get_best_odds(
                    course=course,
                    race_time=race_time,
                    horse=horse,
                    headless=False,
                )
            except Exception as exc:
                odds = {
                    "success": False,
                    "best_odds": None,
                    "best_odds_decimal": None,
                    "bookmaker": None,
                    "url": None,
                    "error": str(exc),
                }

            record = {
                "snapshot_time": datetime.now().isoformat(timespec="seconds"),
                "course": course,
                "race_time": race_time,
                "race_name": race.get("race_name"),
                "race_id": pick.get("race_id"),
                "horse": horse,
                "horse_id": pick.get("horse_id"),
                "pulse_score": pick.get("pulse_score"),
                "strategy": "Pulse Top Pick",
                "odds_source": "oddschecker",
                "best_odds": odds.get("best_odds"),
                "best_odds_decimal": odds.get("best_odds_decimal"),
                "bookmaker": odds.get("bookmaker"),
                "odds_url": odds.get("url"),
                "odds_success": odds.get("success"),
                "odds_error": odds.get("error"),
                "minutes_before_off": None,
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            if odds.get("success"):
                saved += 1
            else:
                failed += 1

            time.sleep(1.5)

    print(f"Saved {saved} real Pulse pick odds snapshots.")
    print(f"Failed: {failed}")
    print(f"File: {output_file}")


if __name__ == "__main__":
    snapshot_pulse_picks()
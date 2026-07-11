import json
import time
from datetime import datetime
from pathlib import Path

from app.modules.horses.routes import get_horse_race_groups
from app.modules.odds.manager import OddsProviderManager


OUTPUT_DIR = Path("data/horses/odds_snapshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_today_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return OUTPUT_DIR / f"{today}.jsonl"


def minutes_until_race(race_time):
    try:
        now = datetime.now()
        hour, minute = map(int, race_time.split(":"))

        race_dt = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        return int((race_dt - now).total_seconds() / 60)

    except Exception:
        return None


def snapshot_pulse_picks():
    races = get_horse_race_groups()
    output_file = get_today_file()

    odds_manager = OddsProviderManager()
    odds_manager.preload()

    saved = 0
    failed = 0
    skipped = 0

    with output_file.open("a", encoding="utf-8") as f:
        for race in races:
            pick = race.get("pulse_pick")

            if not pick:
                continue

            course = race.get("course")
            race_time = race.get("time")
            horse = pick.get("horse")

            mins = minutes_until_race(race_time)

            if mins is not None and mins < 0:
                print(f"Skipping finished race: {course} {race_time}")
                skipped += 1
                continue

            print(f"Checking odds: {course} {race_time} - {horse}")

            try:
                odds = odds_manager.get_best_odds(
                    course=course,
                    race_time=race_time,
                    horse=horse,
                )

            except Exception as exc:
                odds = {
                    "success": False,
                    "best_odds": None,
                    "best_odds_decimal": None,
                    "bookmaker": None,
                    "url": None,
                    "odds_source": "none",
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
                "odds_source": odds.get("odds_source"),
                "best_odds": odds.get("best_odds"),
                "best_odds_decimal": odds.get("best_odds_decimal"),
                "bookmaker": odds.get("bookmaker"),
                "odds_url": odds.get("url"),
                "odds_success": odds.get("success"),
                "odds_error": odds.get("error"),
                "minutes_before_off": mins,
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            if odds.get("success"):
                saved += 1
            else:
                failed += 1

            time.sleep(0.25)

    print()
    print(f"Saved: {saved}")
    print(f"Failed: {failed}")
    print(f"Skipped finished races: {skipped}")
    print(f"File: {output_file}")


if __name__ == "__main__":
    snapshot_pulse_picks()
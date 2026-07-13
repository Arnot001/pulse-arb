import json
import time
from datetime import datetime
from pathlib import Path

from app.modules.horses.routes import get_horse_race_groups
from app.modules.odds.manager import OddsProviderManager


OUTPUT_DIR = Path("data/horses/odds_snapshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOT_WINDOW_MINUTES = 30
GRACE_AFTER_OFF_MINUTES = 10


def get_today_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return OUTPUT_DIR / f"{today}.jsonl"


def minutes_until_race(race_time):
    try:
        now = datetime.now()
        hour, minute = map(int, str(race_time).split(":"))

        # Racecard times may use 12-hour format without AM/PM.
        # During afternoon/evening racing, convert suitable hours.
        if hour <= 12:
            candidate = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            afternoon_candidate = now.replace(
                hour=(hour % 12) + 12,
                minute=minute,
                second=0,
                microsecond=0,
            )

            # Pick whichever interpretation is closest to now.
            if abs(
                (afternoon_candidate - now).total_seconds()
            ) < abs(
                (candidate - now).total_seconds()
            ):
                race_dt = afternoon_candidate
            else:
                race_dt = candidate

        else:
            race_dt = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

        return int((race_dt - now).total_seconds() / 60)

    except Exception:
        return None


def make_snapshot_key(course, race_time, horse):
    return "|".join(
        [
            str(course or "").lower().strip(),
            str(race_time or "").lower().strip(),
            str(horse or "").lower().strip(),
            "pulse top pick",
        ]
    )


def load_existing_snapshots(file_path):
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    return rows


def build_snapshot_index(rows):
    index = {}

    for row in rows:
        key = make_snapshot_key(
            row.get("course"),
            row.get("race_time"),
            row.get("horse"),
        )

        index[key] = row

    return index


def save_snapshots(file_path, rows):
    with file_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )


def snapshot_pulse_picks():
    races = get_horse_race_groups()
    output_file = get_today_file()

    existing_rows = load_existing_snapshots(output_file)
    snapshot_index = build_snapshot_index(existing_rows)

    candidates = []

    too_early = 0
    finished = 0
    invalid_time = 0
    already_captured = 0
    no_pick = 0

    for race in races:
        pick = race.get("pulse_pick")

        if not pick:
            no_pick += 1
            continue

        course = race.get("course")
        race_time = race.get("time")
        horse = pick.get("horse")

        mins = minutes_until_race(race_time)

        if mins is None:
            print(
                f"Skipping invalid race time: "
                f"{course} {race_time}"
            )
            invalid_time += 1
            continue

        # Wait until the race is within the capture window.
        if mins > SNAPSHOT_WINDOW_MINUTES:
            too_early += 1
            continue

        # Stop attempting once sufficiently past the scheduled off.
        if mins < -GRACE_AFTER_OFF_MINUTES:
            finished += 1
            continue

        snapshot_key = make_snapshot_key(
            course,
            race_time,
            horse,
        )

        existing = snapshot_index.get(snapshot_key)

        # Once a valid price is captured, freeze that snapshot.
        if (
            existing
            and existing.get("odds_success") is True
            and existing.get("best_odds_decimal") is not None
        ):
            already_captured += 1
            continue

        candidates.append(
            {
                "race": race,
                "pick": pick,
                "course": course,
                "race_time": race_time,
                "horse": horse,
                "minutes_before_off": mins,
                "snapshot_key": snapshot_key,
            }
        )

    saved = 0
    failed = 0

    if candidates:
        print("Preloading odds providers...")

        odds_manager = OddsProviderManager()
        odds_manager.preload()

        for item in candidates:
            race = item["race"]
            pick = item["pick"]
            course = item["course"]
            race_time = item["race_time"]
            horse = item["horse"]
            mins = item["minutes_before_off"]
            snapshot_key = item["snapshot_key"]

            print(
                f"Checking odds: {course} {race_time} "
                f"- {horse} ({mins} mins)"
            )

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
                "snapshot_date": datetime.now().strftime(
                    "%Y-%m-%d"
                ),
                "snapshot_time": datetime.now().isoformat(
                    timespec="seconds"
                ),
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
                "best_odds_decimal": odds.get(
                    "best_odds_decimal"
                ),
                "bookmaker": odds.get("bookmaker"),
                "odds_url": odds.get("url"),
                "odds_success": bool(
                    odds.get("success")
                ),
                "odds_error": odds.get("error"),
                "minutes_before_off": mins,
            }

            # Replace a failed attempt with the latest attempt,
            # rather than endlessly appending duplicate rows.
            snapshot_index[snapshot_key] = record

            if record["odds_success"]:
                saved += 1
            else:
                failed += 1

            time.sleep(0.25)

    final_rows = list(snapshot_index.values())

    # Always save rows, including failed attempts, so every
    # approaching Pulse pick can enter the bet ledger.
    save_snapshots(output_file, final_rows)

    print()
    print("=" * 60)
    print("HORSE ODDS SNAPSHOT SUMMARY")
    print("=" * 60)
    print(f"Races loaded:          {len(races)}")
    print(f"Eligible now:          {len(candidates)}")
    print(f"Odds captured:         {saved}")
    print(f"Odds failed:           {failed}")
    print(f"Already captured:      {already_captured}")
    print(f"Too early:             {too_early}")
    print(f"Finished:              {finished}")
    print(f"Invalid race times:    {invalid_time}")
    print(f"No Pulse pick:         {no_pick}")
    print(f"Snapshot rows today:   {len(final_rows)}")
    print(f"File: {output_file}")


if __name__ == "__main__":
    snapshot_pulse_picks()
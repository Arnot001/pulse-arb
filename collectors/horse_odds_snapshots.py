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


def parse_race_date(race):
    possible_dates = [
        race.get("date"),
        race.get("race_date"),
        race.get("meeting_date"),
        race.get("collection_date"),
    ]

    for value in possible_dates:
        if not value:
            continue

        text = str(value).strip()[:10]

        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except Exception:
            continue

    return datetime.now().date()


def build_race_datetime(race):
    race_time = str(race.get("time") or "").strip()

    if not race_time:
        return None

    try:
        parts = race_time.split(":")

        if len(parts) != 2:
            return None

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23:
            return None

        if minute < 0 or minute > 59:
            return None

        # Pulse racecards commonly use 12-hour times without AM/PM.
        #
        # Racing shown as 1:30 through 9:59 is normally afternoon
        # or evening racing, so convert it once and keep it stable.
        #
        # 10:00, 11:00 and 12:00 remain unchanged because morning
        # and midday international meetings can genuinely use them.
        if 1 <= hour <= 9:
            hour += 12

        race_date = parse_race_date(race)

        return datetime.combine(
            race_date,
            datetime.min.time(),
        ).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

    except Exception:
        return None


def minutes_until_race(race):
    race_dt = build_race_datetime(race)

    if race_dt is None:
        return None

    now = datetime.now()

    return int((race_dt - now).total_seconds() / 60)


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

        race_dt = build_race_datetime(race)
        mins = minutes_until_race(race)

        if race_dt is None or mins is None:
            print(
                f"Skipping invalid race datetime: "
                f"{course} {race_time}"
            )
            invalid_time += 1
            continue

        if mins > SNAPSHOT_WINDOW_MINUTES:
            too_early += 1
            continue

        if mins < -GRACE_AFTER_OFF_MINUTES:
            finished += 1
            continue

        snapshot_key = make_snapshot_key(
            course,
            race_time,
            horse,
        )

        existing = snapshot_index.get(snapshot_key)

        # Freeze the first valid pre-race price for ROI.
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
                "race_datetime": race_dt,
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
            race_dt = item["race_datetime"]
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

            now = datetime.now()

            record = {
                "snapshot_date": now.strftime("%Y-%m-%d"),
                "snapshot_time": now.isoformat(
                    timespec="seconds"
                ),
                "race_date": race_dt.strftime("%Y-%m-%d"),
                "race_datetime": race_dt.isoformat(
                    timespec="minutes"
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

            # Failed captures are replaced next cycle.
            # Successful captures remain frozen.
            snapshot_index[snapshot_key] = record

            record["odds_success"] = (
                odds.get("success")
                and odds.get("best_odds_decimal") is not None
            )
        else:
            failed += 1

        time.sleep(0.25)

    final_rows = list(snapshot_index.values())

    save_snapshots(output_file, final_rows)

    print()
    print("=" * 60)
    print("HORSE ODDS SNAPSHOT SUMMARY")
    print("=" * 60)
    print(f"Current time:          {datetime.now().isoformat(timespec='seconds')}")
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
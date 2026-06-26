import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from app.data_store import append_jsonl


BASE_URL = "https://www.sportinglife.com"
RACECARDS_DIR = Path("data/dogs/racecards")
RUNNER_RECORDS_DIR = Path("data/dogs/runner_records")


def get_today():
    return datetime.now(timezone.utc).date().isoformat()


def get_latest_racecard_file():
    files = sorted(RACECARDS_DIR.glob("*.jsonl"))

    if not files:
        raise RuntimeError("No dog racecard files found.")

    return files[-1]


def get_next_data(html):
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")

    if not script or not script.string:
        raise RuntimeError("Could not find __NEXT_DATA__ JSON on race page.")

    return json.loads(script.string)


def build_race_url(record):
    race_date = record.get("race_date") or record.get("meeting_date")
    track = str(record.get("track", "")).lower().replace(" ", "-")
    race_id = record.get("race_id")

    if not race_date or not track or not race_id:
        return None

    return (
        f"{BASE_URL}/greyhounds/racecards/"
        f"{race_date}/{track}/racecard/{race_id}"
    )


def load_todays_racecard_records():
    today = get_today()
    file_path = get_latest_racecard_file()
    records = []

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            record = json.loads(line)

            if record.get("collection_date") != today:
                continue

            records.append(record)

    return records


def load_existing_runner_race_ids():
    existing = set()

    if not RUNNER_RECORDS_DIR.exists():
        return existing

    for file_path in RUNNER_RECORDS_DIR.glob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                race_id = record.get("race_id")

                if race_id:
                    existing.add(race_id)

    return existing


def extract_race(data):
    return (
        data.get("props", {})
        .get("pageProps", {})
        .get("race")
    )


def collect_dog_runner_records():
    collection_date = get_today()
    racecards = load_todays_racecard_records()
    already_saved_races = load_existing_runner_race_ids()

    saved = 0
    skipped = 0
    failed = 0
    duplicate = 0
    seen_races = set()

    total = len(racecards)

    for index, racecard in enumerate(racecards, start=1):
        race_id = racecard.get("race_id")

        if not race_id or race_id in seen_races:
            continue

        seen_races.add(race_id)

        if race_id in already_saved_races:
            duplicate += 1
            continue

        url = build_race_url(racecard)

        if not url:
            skipped += 1
            continue

        print(
            f"Processing dog race {index}/{total}: "
            f"{racecard.get('track')} {racecard.get('race_time')} "
            f"({race_id})"
        )

        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            response.raise_for_status()

            data = get_next_data(response.text)
            race = extract_race(data)

            if not race:
                skipped += 1
                print(f"Skipped race {race_id}: no race data found.")
                continue

            race_summary = race.get("race_summary", {})
            runs = race.get("runs", [])

            if not runs:
                skipped += 1
                print(f"Skipped race {race_id}: no runner data found.")
                continue

            for run in runs:
                greyhound = run.get("greyhound", {})
                trainer = greyhound.get("trainer", {})
                owner = greyhound.get("owner", {})
                sire = greyhound.get("sire", {})
                dam = greyhound.get("dam", {})
                formsummary = greyhound.get("formsummary", {})

                record = {
                    "source": "sporting_life",
                    "collection_date": collection_date,

                    "track": race_summary.get("course_name"),
                    "race_date": race_summary.get("date"),
                    "race_time": race_summary.get("time"),
                    "race_name": race_summary.get("name"),
                    "race_class": race_summary.get("race_class"),
                    "distance": race_summary.get("distance"),
                    "race_stage": race_summary.get("race_stage"),
                    "race_id": (
                        race_summary
                        .get("race_summary_reference", {})
                        .get("id")
                    ),

                    "run_id": (
                        run
                        .get("run_reference", {})
                        .get("id")
                    ),
                    "trap": run.get("cloth_number"),
                    "finish_position": run.get("finish_position"),
                    "sectional_time": run.get("sectional_time"),
                    "run_time": run.get("run_time"),
                    "best_run_time": run.get("best_run_time"),
                    "run_status": run.get("run_status"),
                    "reserve": run.get("reserve"),

                    "dog_id": (
                        greyhound
                        .get("greyhound_reference", {})
                        .get("id")
                    ),
                    "dog_name": greyhound.get("name"),
                    "colour": greyhound.get("colour"),
                    "age": greyhound.get("age"),
                    "birth_date": greyhound.get("birth_date"),
                    "sex": greyhound.get("sex"),
                    "trainer": trainer.get("name"),
                    "owner": owner.get("name"),
                    "sire": sire.get("name"),
                    "dam": dam.get("name"),
                    "form": formsummary.get("display_text"),

                    "previous_results": greyhound.get("previous_results", []),
                    "raw": run,
                }

                append_jsonl(
                    sport="dogs",
                    data_type="runner_records",
                    record=record,
                )

                saved += 1

        except Exception as exc:
            failed += 1
            print(f"Failed race {race_id}: {exc}")

        time.sleep(0.2)

    print(
        f"Saved {saved} dog runner records. "
        f"Skipped {skipped}. "
        f"Duplicates {duplicate}. "
        f"Failed {failed}."
    )


if __name__ == "__main__":
    collect_dog_runner_records()
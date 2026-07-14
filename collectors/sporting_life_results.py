import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from app.data_store import append_jsonl


BASE_URL = "https://www.sportinglife.com/racing/results"
RACECARD_DIR = Path("data/horses/racecards")


def normal_time(value):
    value = str(value or "").strip()

    if not value:
        return ""

    parts = value.split(":")

    if len(parts) >= 2:
        try:
            hour = int(parts[0])
            minute = int(parts[1])

            return f"{hour}:{minute:02d}"
        except Exception:
            return value

    return value


def normalise(value):
    return str(value or "").strip().lower()


def extract_next_data(html):
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">'
        r"(.*?)"
        r"</script>",
        html,
        flags=re.DOTALL,
    )

    if not match:
        return None

    return json.loads(match.group(1))


def load_racecard_runner_lookup():
    lookup = {}

    if not RACECARD_DIR.exists():
        return lookup

    for file_path in RACECARD_DIR.glob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except Exception:
                    continue

                raw = record.get("raw", record)

                date = (
                    raw.get("date")
                    or record.get("date")
                    or record.get("collection_date")
                )

                course = normalise(
                    raw.get("course")
                    or record.get("course")
                )

                runners = (
                    raw.get("runners")
                    or record.get("runners")
                    or []
                )

                for runner in runners:
                    horse = normalise(runner.get("horse"))

                    if not date or not course or not horse:
                        continue

                    key = (
                        str(date)[:10],
                        course,
                        horse,
                    )

                    lookup[key] = {
                        "race_id": raw.get("race_id"),
                        "course": (
                            raw.get("course")
                            or record.get("course")
                        ),
                        "date": str(date)[:10],
                        "off_time": (
                            raw.get("off_time")
                            or raw.get("time")
                            or record.get("race_time")
                        ),
                        "off_dt": raw.get("off_dt"),
                        "race_name": raw.get("race_name"),
                        "race_class": raw.get("race_class"),
                        "distance_f": raw.get("distance_f"),
                        "going": raw.get("going"),
                        "surface": raw.get("surface"),
                        "field_size": raw.get("field_size"),
                        "horse": runner.get("horse"),
                        "horse_id": runner.get("horse_id"),
                        "trainer": runner.get("trainer"),
                        "trainer_id": runner.get("trainer_id"),
                        "jockey": runner.get("jockey"),
                        "jockey_id": runner.get("jockey_id"),
                        "draw": runner.get("draw"),
                        "number": runner.get("number"),
                        "age": runner.get("age"),
                        "lbs": runner.get("lbs"),
                        "ofr": runner.get("ofr"),
                        "last_run": runner.get("last_run"),
                        "form": runner.get("form"),
                    }

    return lookup


def validate_date(value):
    try:
        parsed = datetime.strptime(
            str(value),
            "%Y-%m-%d",
        ).date()

        return parsed.isoformat()

    except Exception as exc:
        raise ValueError(
            f"Invalid result date: {value}. "
            "Expected YYYY-MM-DD."
        ) from exc


def get_target(mode="yesterday", target_date=None):
    today = datetime.now(timezone.utc).date()

    if target_date:
        selected_date = validate_date(target_date)

        return (
            selected_date,
            f"{BASE_URL}/{selected_date}",
        )

    if mode == "today":
        return today.isoformat(), BASE_URL

    yesterday = today - timedelta(days=1)

    return (
        yesterday.isoformat(),
        f"{BASE_URL}/yesterday",
    )


def collect_sporting_life_results(
    mode="yesterday",
    target_date=None,
):
    collection_date = (
        datetime.now(timezone.utc)
        .date()
        .isoformat()
    )

    selected_date, url = get_target(
        mode=mode,
        target_date=target_date,
    )

    runner_lookup = load_racecard_runner_lookup()

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )

    response.raise_for_status()

    data = extract_next_data(response.text)

    if not data:
        print("No Sporting Life __NEXT_DATA__ found.")

        return {
            "target_date": selected_date,
            "saved_races": 0,
            "saved_runners": 0,
            "matched_runners": 0,
            "skipped": 0,
            "success": False,
        }

    meetings = (
        data.get("props", {})
        .get("pageProps", {})
        .get("meetings", [])
    )

    saved_races = 0
    saved_runners = 0
    matched_runners = 0
    skipped = 0

    for meeting in meetings:
        for race in meeting.get("races", []):
            race_date = str(
                race.get("date") or ""
            )[:10]

            if race_date != selected_date:
                skipped += 1
                continue

            top_horses = race.get("top_horses") or []

            if not top_horses:
                skipped += 1
                continue

            course = race.get("course_name")

            race_time = normal_time(
                race.get("time")
                or race.get("off_time")
            )

            enriched_positions = []

            for horse in top_horses:
                horse_name = horse.get("name")

                lookup_key = (
                    selected_date,
                    normalise(course),
                    normalise(horse_name),
                )

                extra = runner_lookup.get(
                    lookup_key,
                    {},
                )

                if extra:
                    matched_runners += 1

                position_record = {
                    "position": horse.get("position"),
                    "horse": horse_name,
                    "sp": horse.get("odds"),
                    "favourite": horse.get("favourite"),
                    "horse_id": extra.get("horse_id"),
                    "trainer": extra.get("trainer"),
                    "trainer_id": extra.get("trainer_id"),
                    "jockey": extra.get("jockey"),
                    "jockey_id": extra.get("jockey_id"),
                    "draw": extra.get("draw"),
                    "number": extra.get("number"),
                }

                enriched_positions.append(
                    position_record
                )

                runner_result = {
                    "source": "sporting_life_enriched",
                    "collection_date": collection_date,
                    "result_date": selected_date,
                    "course": course,
                    "race_time": race_time,
                    "race_name": race.get("name"),
                    "race_class": (
                        race.get("race_class")
                        or extra.get("race_class")
                    ),
                    "distance": race.get("distance"),
                    "distance_f": extra.get("distance_f"),
                    "going": (
                        race.get("going")
                        or extra.get("going")
                    ),
                    "surface": extra.get("surface"),
                    "field_size": (
                        extra.get("field_size")
                        or len(top_horses)
                    ),
                    "race_id": extra.get("race_id"),
                    "horse": horse_name,
                    "horse_id": extra.get("horse_id"),
                    "trainer": extra.get("trainer"),
                    "trainer_id": extra.get("trainer_id"),
                    "jockey": extra.get("jockey"),
                    "jockey_id": extra.get("jockey_id"),
                    "draw": extra.get("draw"),
                    "number": extra.get("number"),
                    "age": extra.get("age"),
                    "lbs": extra.get("lbs"),
                    "ofr": extra.get("ofr"),
                    "last_run": extra.get("last_run"),
                    "form": extra.get("form"),
                    "finish_position": horse.get("position"),
                    "sp": horse.get("odds"),
                    "favourite": horse.get("favourite"),
                    "matched_racecard": bool(extra),
                }

                append_jsonl(
                    sport="horses",
                    data_type="runner_results",
                    record=runner_result,
                )

                saved_runners += 1

            winner_data = next(
                (
                    item
                    for item in enriched_positions
                    if str(item.get("position")) == "1"
                ),
                enriched_positions[0],
            )

            winner = {
                "position": 1,
                "horse": winner_data.get("horse"),
                "sp": winner_data.get("sp"),
                "horse_id": winner_data.get("horse_id"),
                "trainer": winner_data.get("trainer"),
                "trainer_id": winner_data.get(
                    "trainer_id"
                ),
                "jockey": winner_data.get("jockey"),
                "jockey_id": winner_data.get(
                    "jockey_id"
                ),
            }

            race_record = {
                "source": "sporting_life",
                "collection_date": collection_date,
                "result_date": selected_date,
                "url": url,
                "raw": {
                    "course": course,
                    "race_time": race_time,
                    "race_name": race.get("name"),
                    "race_class": race.get("race_class"),
                    "distance": race.get("distance"),
                    "going": race.get("going"),
                    "race_stage": race.get("race_stage"),
                    "winner": winner,
                    "positions": enriched_positions,
                },
            }

            append_jsonl(
                sport="horses",
                data_type="sporting_life_results",
                record=race_record,
            )

            saved_races += 1

    print(f"Mode: {mode}")

    if target_date:
        print("Mode override: specific date")

    print(f"URL: {url}")
    print(f"Target result date: {selected_date}")
    print(
        f"Sporting Life meetings found: "
        f"{len(meetings)}"
    )
    print(
        f"Racecard runner lookup size: "
        f"{len(runner_lookup)}"
    )
    print(
        f"Saved {saved_races} Sporting Life "
        "race result records."
    )
    print(
        f"Saved {saved_runners} enriched "
        "runner result records."
    )
    print(
        f"Matched racecard runners: "
        f"{matched_runners}/{saved_runners}"
    )
    print(f"Skipped {skipped} races.")

    return {
        "target_date": selected_date,
        "url": url,
        "saved_races": saved_races,
        "saved_runners": saved_runners,
        "matched_runners": matched_runners,
        "skipped": skipped,
        "success": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--today",
        action="store_true",
        help=(
            "Collect today's results instead of "
            "yesterday's results."
        ),
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Collect results for a specific date "
            "in YYYY-MM-DD format."
        ),
    )

    args = parser.parse_args()

    selected_mode = (
        "today"
        if args.today
        else "yesterday"
    )

    collect_sporting_life_results(
        mode=selected_mode,
        target_date=args.date,
    )
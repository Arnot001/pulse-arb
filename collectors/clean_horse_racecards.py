import json
from pathlib import Path

from app.data_store import append_jsonl, get_week_key
from app.dedupe import should_store
from app.utils import to_int, to_float


def clean_horse_racecards():
    week_key = get_week_key()
    input_file = Path("data") / "horses" / "racecards" / f"{week_key}.jsonl"

    if not input_file.exists():
        print(f"No racecard file found: {input_file}")
        return

    saved = 0
    skipped = 0

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)
            race = item.get("raw", {})

            race_id = race.get("race_id")
            runners = race.get("runners", [])

            for runner in runners:
                horse_id = runner.get("horse_id")
                runner_key = f"horse_runner:{race.get('date')}:{race_id}:{horse_id}"

                if not should_store(runner_key):
                    skipped += 1
                    continue

                record = {
                    "source": "the_racing_api",
                    "race_id": race_id,
                    "course": race.get("course"),
                    "date": race.get("date"),
                    "off_time": race.get("off_time"),
                    "off_dt": race.get("off_dt"),
                    "race_name": race.get("race_name"),
                    "distance_f": to_float(race.get("distance_f")),
                    "race_class": race.get("race_class"),
                    "race_type": race.get("type"),
                    "going": race.get("going"),
                    "surface": race.get("surface"),
                    "field_size": to_int(race.get("field_size")),
                    "horse": runner.get("horse"),
                    "horse_id": horse_id,
                    "age": to_int(runner.get("age")),
                    "sex": runner.get("sex"),
                    "trainer": runner.get("trainer"),
                    "trainer_id": runner.get("trainer_id"),
                    "jockey": runner.get("jockey"),
                    "jockey_id": runner.get("jockey_id"),
                    "draw": to_int(runner.get("draw")),
                    "number": to_int(runner.get("number")),
                    "lbs": to_int(runner.get("lbs")),
                    "ofr": runner.get("ofr"),
                    "last_run": to_int(runner.get("last_run")),
                    "form": runner.get("form"),
                    "headgear": runner.get("headgear"),
                }

                append_jsonl(
                    sport="horses",
                    data_type="runner_records",
                    record=record,
                )

                saved += 1

    print(f"Saved {saved} cleaned horse runner records.")
    print(f"Skipped {skipped} duplicate runner records.")


if __name__ == "__main__":
    clean_horse_racecards()
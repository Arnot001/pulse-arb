import json
from pathlib import Path

from app.data_store import get_week_key
from app.utils import to_int, to_float


def load_existing_runner_keys(output_path):
    existing = set()

    if not output_path.exists():
        return existing

    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            runner_key = (
                f"horse_runner:"
                f"{record.get('date')}:"
                f"{record.get('race_id')}:"
                f"{record.get('horse_id')}"
            )

            existing.add(runner_key)

    return existing


def clean_horse_racecards():
    week_key = get_week_key()

    input_file = (
        Path("data")
        / "horses"
        / "racecards"
        / f"{week_key}.jsonl"
    )

    output_dir = (
        Path("data")
        / "horses"
        / "runner_records"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{week_key}.jsonl"

    if not input_file.exists():
        print(f"No racecard file found: {input_file}")
        return

    existing_keys = load_existing_runner_keys(output_file)

    saved = 0
    skipped = 0
    new_records = []

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)
            race = item.get("raw", {})

            race_id = race.get("race_id")
            race_date = race.get("date")
            runners = race.get("runners", [])

            for runner in runners:
                horse_id = runner.get("horse_id")

                runner_key = (
                    f"horse_runner:"
                    f"{race_date}:"
                    f"{race_id}:"
                    f"{horse_id}"
                )

                if runner_key in existing_keys:
                    skipped += 1
                    continue

                record = {
                    "source": "the_racing_api",
                    "race_id": race_id,
                    "course": race.get("course"),
                    "date": race_date,
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

                new_records.append(record)
                existing_keys.add(runner_key)
                saved += 1

    if new_records:
        with output_file.open("a", encoding="utf-8") as f:
            for record in new_records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Saved {saved} cleaned horse runner records.")
    print(f"Skipped {skipped} duplicate runner records.")


if __name__ == "__main__":
    clean_horse_racecards()
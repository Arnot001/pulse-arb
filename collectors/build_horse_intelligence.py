import json
from pathlib import Path

from app.modules.horses.scoring import calculate_horse_score
from app.modules.horses.intelligence_store import upsert_intelligence_record


def load_runner_records():
    path = Path("data/horses/runner_records")
    records = []

    if not path.exists():
        return records

    for file in sorted(path.glob("*.jsonl")):
        with file.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    return records


def build_horse_intelligence():
    runners = load_runner_records()

    saved = 0

    for runner in runners:
        score_data = calculate_horse_score(runner)

        record = {
            "source": "runner_records",
            "race_id": runner.get("race_id"),
            "course": runner.get("course"),
            "date": runner.get("date"),
            "off_time": runner.get("off_time"),
            "off_dt": runner.get("off_dt"),
            "race_name": runner.get("race_name"),
            "distance_f": runner.get("distance_f"),
            "race_class": runner.get("race_class"),
            "race_type": runner.get("race_type"),
            "going": runner.get("going"),
            "surface": runner.get("surface"),
            "field_size": runner.get("field_size"),
            "horse": runner.get("horse"),
            "horse_id": runner.get("horse_id"),
            "age": runner.get("age"),
            "sex": runner.get("sex"),
            "trainer": runner.get("trainer"),
            "trainer_id": runner.get("trainer_id"),
            "jockey": runner.get("jockey"),
            "jockey_id": runner.get("jockey_id"),
            "draw": runner.get("draw"),
            "number": runner.get("number"),
            "lbs": runner.get("lbs"),
            "ofr": runner.get("ofr"),
            "last_run": runner.get("last_run"),
            "form": runner.get("form"),
            "headgear": runner.get("headgear"),
            "pulse_score": score_data.get("pulse_score"),
            "raw_score": score_data.get("raw_score"),
            "pulse_notes": score_data.get("notes"),
            "pulse_factors": score_data.get("factors"),
            "tipsters": score_data.get("tipsters"),
            "value_rating": score_data.get("value_rating"),
            "market_events": [],
            "result": None,
        }

        upsert_intelligence_record(record)
        saved += 1

    print(f"Built/updated {saved} horse intelligence records.")


if __name__ == "__main__":
    build_horse_intelligence()
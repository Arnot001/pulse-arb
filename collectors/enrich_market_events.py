import json
from pathlib import Path
from urllib.parse import urlparse
from app.modules.horses.intelligence_store import upsert_intelligence_record
from app.modules.horses.intelligence_store import append_market_event_to_intelligence
from app.data_store import append_jsonl
from app.modules.horses.scoring import calculate_horse_score


def clean(value):
    return str(value or "").strip()


def normalise(value):
    return clean(value).lower()


def parse_oddschecker_url(url):
    parts = urlparse(url).path.strip("/").split("/")

    # horse-racing/ffos-las/18:09/winner
    if len(parts) >= 4:
        return {
            "course_slug": parts[1],
            "off_time": parts[2],
        }

    return {
        "course_slug": "",
        "off_time": "",
    }


def slug_to_course(slug):
    return clean(slug).replace("-", " ").lower()


def load_latest_runner_records():
    path = Path("data/horses/runner_records")
    runners = []

    if not path.exists():
        return runners

    for file in sorted(path.glob("*.jsonl"), reverse=True):
        with file.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    runners.append(json.loads(line))
                except Exception:
                    pass

    return runners


def find_runner_match(event, runner_records):
    url_bits = parse_oddschecker_url(event.get("url", ""))

    event_horse = normalise(event.get("horse"))
    event_course = slug_to_course(url_bits.get("course_slug"))

    horse_matches = []

    for runner in runner_records:
        runner_horse = normalise(runner.get("horse"))

        if runner_horse == event_horse:
            horse_matches.append(runner)

    if not horse_matches:
        return None

    for runner in horse_matches:
        runner_course = normalise(runner.get("course"))

        if event_course and event_course in runner_course:
            return runner

    return horse_matches[0]


def load_market_events():
    path = Path("data/horses/market_events")
    events = []

    if not path.exists():
        return events

    for file in sorted(path.glob("*.jsonl")):
        with file.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    return events


def enrich_market_events():
    events = load_market_events()
    runner_records = load_latest_runner_records()

    saved = 0
    matched = 0

    for event in events:
        runner = find_runner_match(event, runner_records)

        enriched = dict(event)

        if runner:
            matched += 1
            score_data = calculate_horse_score(runner)

            enriched["matched_runner"] = True
            enriched["race_id"] = runner.get("race_id")
            enriched["course"] = runner.get("course")
            enriched["date"] = runner.get("date")
            enriched["off_time"] = runner.get("off_time")
            enriched["race_name"] = runner.get("race_name")
            enriched["distance_f"] = runner.get("distance_f")
            enriched["race_class"] = runner.get("race_class")
            enriched["going"] = runner.get("going")
            enriched["surface"] = runner.get("surface")
            enriched["field_size"] = runner.get("field_size")
            enriched["trainer"] = runner.get("trainer")
            enriched["trainer_id"] = runner.get("trainer_id")
            enriched["jockey_id"] = runner.get("jockey_id")
            enriched["pulse_score"] = score_data.get("pulse_score")
            enriched["pulse_notes"] = score_data.get("notes")
            enriched["pulse_factors"] = score_data.get("factors")
            
            market_event = {
                "event_type": event.get("event_type"),
                "detected_at": event.get("detected_at"),
                "previous_best_odds": event.get("previous_best_odds"),
                "previous_best_odds_decimal": event.get("previous_best_odds_decimal"),
                "best_odds": event.get("best_odds"),
                "best_odds_decimal": event.get("best_odds_decimal"),
                "movement_pct": event.get("movement_pct"),
                "market_rank": event.get("market_rank"),
                "url": event.get("url"),
            }

            append_market_event_to_intelligence(
                {
                    "race_id": runner.get("race_id"),
                    "horse_id": runner.get("horse_id"),
                    "horse": runner.get("horse"),
                },
                market_event,
            )
            
        else:
            enriched["matched_runner"] = False

        append_jsonl(
            sport="horses",
            data_type="enriched_market_events",
            record=enriched,
        )

        saved += 1

    print(f"Enriched market events saved: {saved}")
    print(f"Matched runner records: {matched}/{saved}")


if __name__ == "__main__":
    enrich_market_events()
import json
from pathlib import Path
from datetime import datetime, timezone


INTELLIGENCE_DIR = Path("data/horses/intelligence")


def make_intelligence_key(race_id, horse_id, horse):
    if race_id and horse_id:
        return f"{race_id}__{horse_id}"

    safe_horse = str(horse or "").strip().lower().replace(" ", "_")
    return f"{race_id or 'unknown_race'}__{safe_horse}"


def intelligence_path(key):
    INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
    return INTELLIGENCE_DIR / f"{key}.json"


def load_intelligence_record(key):
    path = intelligence_path(key)

    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_intelligence_record(record):
    key = make_intelligence_key(
        record.get("race_id"),
        record.get("horse_id"),
        record.get("horse"),
    )

    record["intelligence_key"] = key
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = intelligence_path(key)

    with path.open("w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    return path


def upsert_intelligence_record(base_record, updates=None):
    key = make_intelligence_key(
        base_record.get("race_id"),
        base_record.get("horse_id"),
        base_record.get("horse"),
    )

    existing = load_intelligence_record(key) or {}

    merged = {
        **existing,
        **base_record,
    }

    if updates:
        merged.update(updates)

    return save_intelligence_record(merged)

def append_market_event_to_intelligence(base_record, market_event):
    key = make_intelligence_key(
        base_record.get("race_id"),
        base_record.get("horse_id"),
        base_record.get("horse"),
    )

    record = load_intelligence_record(key) or dict(base_record)

    existing_events = record.get("market_events", [])

    event_key = "|".join(
        [
            str(market_event.get("event_type")),
            str(market_event.get("detected_at")),
            str(market_event.get("previous_best_odds")),
            str(market_event.get("best_odds")),
            str(market_event.get("movement_pct")),
        ]
    )

    existing_keys = {
        "|".join(
            [
                str(item.get("event_type")),
                str(item.get("detected_at")),
                str(item.get("previous_best_odds")),
                str(item.get("best_odds")),
                str(item.get("movement_pct")),
            ]
        )
        for item in existing_events
    }

    if event_key not in existing_keys:
        existing_events.append(market_event)

    record["market_events"] = existing_events

    return save_intelligence_record(record)
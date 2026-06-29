import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.data_store import append_jsonl
from collectors.real_horses import collect_real_horse_racecards


STATE_FILE = Path("data/horses/intelligence_state/racecard_snapshot.json")
DEFAULT_INTERVAL_SECONDS = 300


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def normalise(value):
    return str(value or "").strip().lower()


def make_runner_key(race, runner):
    return "|".join(
        [
            str(race.get("date") or ""),
            normalise(race.get("course")),
            str(race.get("off_time") or ""),
            normalise(runner.get("horse")),
        ]
    )


def make_race_key(race):
    return "|".join(
        [
            str(race.get("date") or ""),
            normalise(race.get("course")),
            str(race.get("off_time") or ""),
            normalise(race.get("race_name")),
        ]
    )


def load_latest_racecards():
    racecard_dir = Path("data/horses/racecards")
    latest = {}

    if not racecard_dir.exists():
        return latest

    for file in racecard_dir.glob("*.jsonl"):
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    item = json.loads(line)
                except Exception:
                    continue

                race = item.get("raw", {})
                race_key = make_race_key(race)

                if not race_key:
                    continue

                latest[race_key] = race

    return latest


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def hash_value(value):
    raw = json.dumps(value, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_snapshot(racecards):
    snapshot = {}

    for race_key, race in racecards.items():
        runners = race.get("runners", [])

        runner_states = {}

        for runner in runners:
            runner_key = make_runner_key(race, runner)

            runner_states[runner_key] = {
                "horse": runner.get("horse"),
                "horse_id": runner.get("horse_id"),
                "trainer": runner.get("trainer"),
                "trainer_id": runner.get("trainer_id"),
                "jockey": runner.get("jockey"),
                "jockey_id": runner.get("jockey_id"),
                "number": runner.get("number"),
                "draw": runner.get("draw"),
            }

        snapshot[race_key] = {
            "race_id": race.get("race_id"),
            "course": race.get("course"),
            "date": race.get("date"),
            "off_time": race.get("off_time"),
            "off_dt": race.get("off_dt"),
            "race_name": race.get("race_name"),
            "going": race.get("going"),
            "race_status": race.get("race_status"),
            "field_size": race.get("field_size"),
            "runners": runner_states,
        }

    return snapshot


def emit_event(event_type, race, extra=None):
    extra = extra or {}

    event = {
        "source": "race_intelligence",
        "event_type": event_type,
        "detected_at": now_utc(),
        "race_id": race.get("race_id"),
        "course": race.get("course"),
        "date": race.get("date"),
        "off_time": race.get("off_time"),
        "off_dt": race.get("off_dt"),
        "race_name": race.get("race_name"),
        **extra,
    }

    event["event_hash"] = hash_value(
        {
            "event_type": event_type,
            "race_id": event.get("race_id"),
            "course": event.get("course"),
            "date": event.get("date"),
            "off_time": event.get("off_time"),
            "race_name": event.get("race_name"),
            "extra": extra,
        }
    )

    append_jsonl(
        sport="horses",
        data_type="race_intelligence",
        record=event,
    )

    print(f"EVENT | {event_type} | {event.get('course')} {event.get('off_time')} | {extra}")


def compare_snapshots(previous, current):
    events = 0

    for race_key, current_race in current.items():
        previous_race = previous.get(race_key)

        if not previous_race:
            emit_event("new_race_seen", current_race)
            events += 1
            continue

        for field in ["going", "race_status", "field_size", "off_time"]:
            old_value = previous_race.get(field)
            new_value = current_race.get(field)

            if old_value != new_value:
                emit_event(
                    f"{field}_changed",
                    current_race,
                    {
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value,
                    },
                )
                events += 1

        previous_runners = previous_race.get("runners", {})
        current_runners = current_race.get("runners", {})

        for runner_key, previous_runner in previous_runners.items():
            if runner_key not in current_runners:
                emit_event(
                    "runner_removed_possible_non_runner",
                    current_race,
                    {
                        "horse": previous_runner.get("horse"),
                        "horse_id": previous_runner.get("horse_id"),
                        "trainer": previous_runner.get("trainer"),
                        "trainer_id": previous_runner.get("trainer_id"),
                    },
                )
                events += 1

        for runner_key, current_runner in current_runners.items():
            if runner_key not in previous_runners:
                emit_event(
                    "runner_added",
                    current_race,
                    {
                        "horse": current_runner.get("horse"),
                        "horse_id": current_runner.get("horse_id"),
                        "trainer": current_runner.get("trainer"),
                        "trainer_id": current_runner.get("trainer_id"),
                    },
                )
                events += 1

        for runner_key, current_runner in current_runners.items():
            previous_runner = previous_runners.get(runner_key)

            if not previous_runner:
                continue

            old_number = previous_runner.get("number")
            new_number = current_runner.get("number")

            if old_number != new_number:
                emit_event(
                    "runner_number_changed_possible_non_runner",
                    current_race,
                    {
                        "horse": current_runner.get("horse"),
                        "horse_id": current_runner.get("horse_id"),
                        "old_number": old_number,
                        "new_number": new_number,
                    },
                )
                events += 1

    return events


def collect_race_intelligence_once(fetch_latest=True):
    if fetch_latest:
        collect_real_horse_racecards()

    racecards = load_latest_racecards()
    current = build_snapshot(racecards)
    previous = load_state()

    events = compare_snapshots(previous, current)

    save_state(current)

    print(f"Race intelligence scan complete. Events saved: {events}")
    return events


def monitor_race_intelligence(interval_seconds=DEFAULT_INTERVAL_SECONDS):
    print("Pulse Race Intelligence Monitor started.")
    print(f"Checking every {interval_seconds} seconds.")

    while True:
        try:
            collect_race_intelligence_once(fetch_latest=True)
        except KeyboardInterrupt:
            print("Pulse Race Intelligence Monitor stopped.")
            break
        except Exception as e:
            print(f"Race intelligence monitor error: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    monitor_race_intelligence()
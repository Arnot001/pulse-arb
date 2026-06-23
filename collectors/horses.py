from app.data_store import append_jsonl


def collect_horse_racecards():
    sample_race = {
        "source": "manual_test",
        "track": "Cheltenham",
        "race_time": "2026-06-23T14:30:00Z",
        "race_name": "Sample Handicap",
        "horse_name": "Pulse Runner",
        "odds": None,
        "status": "racecard",
    }

    path = append_jsonl(
        sport="horses",
        data_type="racecards",
        record=sample_race,
    )

    print(f"Saved horse racecard to {path}")


if __name__ == "__main__":
    collect_horse_racecards()
from app.data_store import append_jsonl


def collect_dog_racecards():
    sample_race = {
        "source": "manual_test",
        "track": "Romford",
        "race_time": "2026-06-23T19:42:00Z",
        "dog_name": "Pulse Hound",
        "trap": 3,
        "odds": None,
        "status": "racecard",
    }

    path = append_jsonl(
        sport="dogs",
        data_type="racecards",
        record=sample_race,
    )

    print(f"Saved dog racecard to {path}")


if __name__ == "__main__":
    collect_dog_racecards()
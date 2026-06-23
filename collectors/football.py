from app.data_store import append_jsonl


def collect_football_fixtures():
    sample_fixture = {
        "source": "manual_test",
        "league": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "kickoff": "2026-06-23T20:00:00Z",
        "status": "scheduled",
    }

    path = append_jsonl(
        sport="football",
        data_type="fixtures",
        record=sample_fixture,
    )

    print(f"Saved football fixture to {path}")


if __name__ == "__main__":
    collect_football_fixtures()
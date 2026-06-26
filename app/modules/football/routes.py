import json
from pathlib import Path


LEADERBOARD_PATH = Path("data/football/team_profiles_leaderboard.json")


def get_football_leaderboard():
    if not LEADERBOARD_PATH.exists():
        return []

    try:
        with LEADERBOARD_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
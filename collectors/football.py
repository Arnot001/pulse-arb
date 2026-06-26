import csv
import hashlib
import io
import json
from pathlib import Path

import requests

from app.data_store import append_jsonl


SOURCE_URL = "https://www.football-data.co.uk/fixtures.csv"
EXISTING_FIXTURES_DIR = Path("data/football/fixtures")


def make_match_id(source, date_text, home_team, away_team):
    raw = f"{source}|{date_text}|{home_team}|{away_team}".lower().strip()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def read_existing_match_ids(folder):
    ids = set()

    if not folder.exists():
        return ids

    for file_path in folder.glob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    match_id = record.get("match_id")
                    if match_id:
                        ids.add(match_id)
                except Exception:
                    continue

    return ids


def fetch_fixtures():
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()

    text = response.content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    fixtures = []

    for row in reader:
        date_text = (row.get("Date") or "").strip()
        time_text = (row.get("Time") or "").strip()
        league = (row.get("Div") or "").strip()
        home_team = (row.get("HomeTeam") or "").strip()
        away_team = (row.get("AwayTeam") or "").strip()

        if not date_text or not home_team or not away_team:
            continue

        match_id = make_match_id(
            source="football_data",
            date_text=date_text,
            home_team=home_team,
            away_team=away_team,
        )

        fixtures.append(
            {
                "match_id": match_id,
                "source": "football_data",
                "source_url": SOURCE_URL,
                "league": league,
                "date": date_text,
                "kickoff_time": time_text,
                "home_team": home_team,
                "away_team": away_team,
                "status": "scheduled",
                "raw": row,
            }
        )

    return fixtures


def collect_football_fixtures():
    existing_ids = read_existing_match_ids(EXISTING_FIXTURES_DIR)

    try:
        fixtures = fetch_fixtures()
    except Exception as exc:
        print(f"Football fixtures source failed: {exc}")
        print("Football fixtures saved: 0")
        print("Football fixtures skipped duplicates: 0")
        return

    saved = 0
    skipped = 0

    for fixture in fixtures:
        if fixture["match_id"] in existing_ids:
            skipped += 1
            continue

        append_jsonl(
            sport="football",
            data_type="fixtures",
            record=fixture,
        )

        saved += 1

    print(f"Football fixtures saved: {saved}")
    print(f"Football fixtures skipped duplicates: {skipped}")


if __name__ == "__main__":
    collect_football_fixtures()
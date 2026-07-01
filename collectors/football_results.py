import csv
import hashlib
import io
import json
from pathlib import Path

import requests

from app.data_store import append_jsonl


SEASON_URLS = [
    {
        "league": "E0",
        "league_name": "Premier League",
        "country": "England",
        "season": "2025-2026",
        "url": "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
    },
    {
        "league": "E1",
        "league_name": "Championship",
        "country": "England",
        "season": "2025-2026",
        "url": "https://www.football-data.co.uk/mmz4281/2526/E1.csv",
    },
    {
        "league": "E2",
        "league_name": "League One",
        "country": "England",
        "season": "2025-2026",
        "url": "https://www.football-data.co.uk/mmz4281/2526/E2.csv",
    },
    {
        "league": "E3",
        "league_name": "League Two",
        "country": "England",
        "season": "2025-2026",
        "url": "https://www.football-data.co.uk/mmz4281/2526/E3.csv",
    },
    {
        "league": "EC",
        "league_name": "National League",
        "country": "England",
        "season": "2025-2026",
        "url": "https://www.football-data.co.uk/mmz4281/2526/EC.csv",
    },
]

EXISTING_RESULTS_DIR = Path("data/football/results")


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


def to_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def fetch_csv(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    text = response.content.decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def row_to_result(row, source_info):
    date_text = (row.get("Date") or "").strip()
    time_text = (row.get("Time") or "").strip()
    home_team = (row.get("HomeTeam") or "").strip()
    away_team = (row.get("AwayTeam") or "").strip()

    home_score = to_int(row.get("FTHG"))
    away_score = to_int(row.get("FTAG"))

    if not date_text or not home_team or not away_team:
        return None

    if home_score is None or away_score is None:
        return None

    if home_score > away_score:
        winner = "home"
    elif away_score > home_score:
        winner = "away"
    else:
        winner = "draw"

    match_id = make_match_id(
        source="football_data",
        date_text=date_text,
        home_team=home_team,
        away_team=away_team,
    )

    return {
        "match_id": match_id,
        "source": "football_data",
        "source_url": source_info["url"],
        "league": source_info["league"],
        "league_name": source_info["league_name"],
        "country": source_info["country"],
        "season": source_info["season"],
        "date": date_text,
        "kickoff_time": time_text,
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "status": "finished",
        "half_time_home": to_int(row.get("HTHG")),
        "half_time_away": to_int(row.get("HTAG")),
        "half_time_result": row.get("HTR"),
        "full_time_result": row.get("FTR"),
        "home_shots": to_int(row.get("HS")),
        "away_shots": to_int(row.get("AS")),
        "home_shots_on_target": to_int(row.get("HST")),
        "away_shots_on_target": to_int(row.get("AST")),
        "home_corners": to_int(row.get("HC")),
        "away_corners": to_int(row.get("AC")),
        "home_fouls": to_int(row.get("HF")),
        "away_fouls": to_int(row.get("AF")),
        "home_yellow_cards": to_int(row.get("HY")),
        "away_yellow_cards": to_int(row.get("AY")),
        "home_red_cards": to_int(row.get("HR")),
        "away_red_cards": to_int(row.get("AR")),
        "raw": row,
    }


def fetch_results():
    results = []

    for source_info in SEASON_URLS:
        try:
            rows = fetch_csv(source_info["url"])
        except Exception as exc:
            print(f"Football results source failed for {source_info['league_name']}: {exc}")
            continue

        for row in rows:
            result = row_to_result(row, source_info)

            if result:
                results.append(result)

    return results


def collect_football_results():
    existing_ids = read_existing_match_ids(EXISTING_RESULTS_DIR)

    results = fetch_results()

    saved = 0
    skipped = 0

    for result in results:
        if result["match_id"] in existing_ids:
            skipped += 1
            continue

        append_jsonl(
            sport="football",
            data_type="results",
            record=result,
        )

        saved += 1

    print(f"Football results saved: {saved}")
    print(f"Football results skipped duplicates: {skipped}")


if __name__ == "__main__":
    collect_football_results()
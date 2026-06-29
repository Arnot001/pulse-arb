import json
import re
from datetime import datetime, timedelta, timezone

import requests

from app.data_store import append_jsonl


URL = "https://www.sportinglife.com/racing/results/yesterday"


def normal_time(value):
    value = str(value or "").strip()

    if not value:
        return ""

    parts = value.split(":")

    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"

    return value


def extract_next_data(html):
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )

    if not match:
        return None

    return json.loads(match.group(1))


def collect_sporting_life_results():
    collection_date = datetime.now(timezone.utc).date().isoformat()
    target_date = (
        datetime.now(timezone.utc).date()
        - timedelta(days=1)
    ).isoformat()

    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )

    response.raise_for_status()

    data = extract_next_data(response.text)

    if not data:
        print("No Sporting Life __NEXT_DATA__ found.")
        return

    meetings = data["props"]["pageProps"].get("meetings", [])

    saved = 0
    skipped = 0

    for meeting in meetings:
        for race in meeting.get("races", []):
            if race.get("date") != target_date:
                skipped += 1
                continue

            top_horses = race.get("top_horses") or []

            if not top_horses:
                skipped += 1
                continue

            winner_data = top_horses[0]

            winner = {
                "position": 1,
                "horse": winner_data.get("name"),
                "sp": winner_data.get("odds"),
            }

            record = {
                "source": "sporting_life",
                "collection_date": collection_date,
                "result_date": target_date,
                "url": URL,
                "raw": {
                    "course": race.get("course_name"),
                    "race_time": normal_time(
                        race.get("time") or race.get("off_time")
                    ),
                    "race_name": race.get("name"),
                    "race_class": race.get("race_class"),
                    "distance": race.get("distance"),
                    "going": race.get("going"),
                    "race_stage": race.get("race_stage"),
                    "winner": winner,
                    "positions": [
                        {
                            "position": horse.get("position"),
                            "horse": horse.get("name"),
                            "sp": horse.get("odds"),
                            "favourite": horse.get("favourite"),
                        }
                        for horse in top_horses
                    ],
                },
            }

            append_jsonl(
                sport="horses",
                data_type="sporting_life_results",
                record=record,
            )

            saved += 1

    print(f"Target result date: {target_date}")
    print(f"Sporting Life meetings found: {len(meetings)}")
    print(f"Saved {saved} Sporting Life result records.")
    print(f"Skipped {skipped} races.")
    

if __name__ == "__main__":
    collect_sporting_life_results()
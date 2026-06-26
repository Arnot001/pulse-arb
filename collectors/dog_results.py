import json
import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from app.data_store import append_jsonl


URL = "https://www.sportinglife.com/greyhounds/results"


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def get_next_data(html):
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")

    if not script or not script.string:
        raise RuntimeError("Could not find __NEXT_DATA__ JSON on page.")

    return json.loads(script.string)


def collect_dog_results():
    collection_date = datetime.now(timezone.utc).date().isoformat()

    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()

    data = get_next_data(response.text)

    meetings = (
        data.get("props", {})
        .get("pageProps", {})
        .get("meetings", [])
    )

    saved = 0

    for meeting in meetings:
        meeting_summary = meeting.get("meeting_summary", {})
        course = meeting_summary.get("course", {})
        course_name = course.get("name")

        races = meeting.get("races", [])

        for race in races:
            record = {
                "source": "sporting_life",
                "collection_date": collection_date,
                "track": course_name or race.get("course_name"),
                "meeting_date": meeting_summary.get("date"),
                "race_date": race.get("date"),
                "race_time": race.get("time"),
                "race_name": clean_text(race.get("name")),
                "race_class": race.get("race_class"),
                "distance": race.get("distance"),
                "prizes": race.get("prizes"),
                "winning_time": race.get("winning_time"),
                "race_stage": race.get("race_stage"),
                "has_handicap": race.get("has_handicap"),
                "meeting_id": (
                    meeting_summary
                    .get("meeting_reference", {})
                    .get("id")
                ),
                "race_id": (
                    race
                    .get("race_summary_reference", {})
                    .get("id")
                ),
                "raw": race,
            }

            append_jsonl(
                sport="dogs",
                data_type="results",
                record=record,
            )

            saved += 1

    print(f"Saved {saved} real dog result records.")


if __name__ == "__main__":
    collect_dog_results()
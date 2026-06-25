import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from app.data_store import append_jsonl


URL = "https://www.attheraces.com/results"


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract_races(text):
    races = []

    course_pattern = re.compile(
        r"([A-Z][A-Za-z\s'().-]+) Results\s+"
    )

    course_matches = list(course_pattern.finditer(text))

    for i, course_match in enumerate(course_matches):
        course = clean_text(course_match.group(1))

        junk = "To view results from further in the past use the date picker above."
        course = course.replace(junk, "").strip()

        start = course_match.end()
        end = (
            course_matches[i + 1].start()
            if i + 1 < len(course_matches)
            else len(text)
        )

        course_text = text[start:end]

        race_pattern = re.compile(
            r"(\d+)\s+(\d{2}:\d{2})\s+-\s+(.+?)\s+"
            r"1st\s+\((\d+)\)\s+(.+?)\s+(\d+/\d+|Evens|SP)",
            re.IGNORECASE,
        )

        for match in race_pattern.finditer(course_text):
            winner = {
                "position": 1,
                "draw_or_number": match.group(4),
                "horse": clean_text(match.group(5)),
                "sp": match.group(6),
            }

            races.append(
                {
                    "course": course,
                    "race_number": match.group(1),
                    "race_time": match.group(2),
                    "race_name": clean_text(match.group(3)),
                    "winner": winner,
                    "positions": [winner],
                }
            )

    return races


def collect_public_horse_results():
    today = datetime.now(timezone.utc).date().isoformat()

    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = clean_text(soup.get_text(" "))

    races = extract_races(text)

    saved = 0

    for race in races:
        record = {
            "source": "at_the_races",
            "collection_date": today,
            "result_date": today,
            "url": URL,
            "raw": race,
        }

        append_jsonl(
            sport="horses",
            data_type="public_results",
            record=record,
        )

        saved += 1

    print(f"Saved {saved} ATR public result records.")


if __name__ == "__main__":
    collect_public_horse_results()
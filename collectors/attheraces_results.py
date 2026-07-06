import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.attheraces.com/results"
OUTPUT_DIR = Path("data/horses/attheraces_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_target(mode):
    today = datetime.now(timezone.utc).date()

    if mode == "yesterday":
        return (today - timedelta(days=1)).isoformat(), f"{BASE_URL}/yesterday"

    return today.isoformat(), BASE_URL


def get_week_file():
    year, week, _ = datetime.now().isocalendar()
    return OUTPUT_DIR / f"{year}-W{week:02d}.jsonl"


def clean_text(value):
    return " ".join(str(value or "").replace("\xa0", " ").split())


def collect_attheraces_results(mode="today"):
    result_date, url = get_target(mode)

    html = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    ).text

    soup = BeautifulSoup(html, "html.parser")

    lines = [
        clean_text(line)
        for line in soup.get_text("\n").splitlines()
        if clean_text(line)
    ]

    output_file = get_week_file()

    current_course = None
    current_race = None
    records = []

    race_pattern = re.compile(r"^(?:\d+\s+)?(\d{2}:\d{2})\s+-\s+(.+)$")
    pos_pattern = re.compile(
        r"^(1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th|13th|14th|15th|16th|17th|18th|19th|20th)\s+\((\d+)\)\s+(.+?)\s+([0-9]+/[0-9]+|[0-9]+)(?:\s+[A-Z0-9]+)?$"
    )
    full_pos_pattern = re.compile(
        r"^F:\s+(\d+(?:st|nd|rd|th))\s+\((\d+)\)\s+(.+?)\s+([0-9]+/[0-9]+|[0-9]+)(?:\s+[A-Z0-9]+)?$"
    )

    for line in lines:
        if line.endswith(" Results"):
            current_course = line.replace(" Results", "").strip()
            continue

        race_match = race_pattern.match(line)

        if race_match and current_course:
            if current_race:
                records.append(current_race)

            current_race = {
                "source": "attheraces",
                "collection_date": datetime.now(timezone.utc).date().isoformat(),
                "result_date": result_date,
                "course": current_course,
                "race_time": race_match.group(1),
                "race_name": race_match.group(2),
                "raw": {
                    "course": current_course,
                    "race_time": race_match.group(1),
                    "race_name": race_match.group(2),
                    "positions": [],
                },
            }
            continue

        if not current_race:
            continue

        match = pos_pattern.match(line) or full_pos_pattern.match(line)

        if match:
            pos_text = match.group(1)
            number = match.group(2)
            horse = match.group(3).strip()
            sp = match.group(4).strip()

            position = int(re.sub(r"\D", "", pos_text))

            current_race["raw"]["positions"].append(
                {
                    "position": position,
                    "number": number,
                    "horse": horse,
                    "sp": sp,
                }
            )

    if current_race:
        records.append(current_race)

    saved = 0

    with output_file.open("a", encoding="utf-8") as f:
        for record in records:
            if not record["raw"]["positions"]:
                continue

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved += 1

    print(f"Mode: {mode}")
    print(f"URL: {url}")
    print(f"ATR results saved: {saved}")
    print(f"File: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--yesterday", action="store_true")
    args = parser.parse_args()

    mode = "today"
    if args.yesterday:
        mode = "yesterday"

    collect_attheraces_results(mode)
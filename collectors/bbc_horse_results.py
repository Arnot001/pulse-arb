import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.data_store import append_jsonl


RESULTS_URL = "https://www.bbc.co.uk/sport/horse-racing/uk-ireland/results"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def extract_initial_data(html):
    match = re.search(r'window\.__INITIAL_DATA__="(.*?)";', html)

    if not match:
        return None

    raw = match.group(1)
    decoded = raw.encode("utf-8").decode("unicode_escape")
    return json.loads(decoded)


def find_race_data(data):
    for key, value in data.get("data", {}).items():
        if key.startswith("horse-racing-racecard?"):
            return value.get("data", {}).get("race")

    return None


def discover_race_urls():
    response = requests.get(
        RESULTS_URL,
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/sport/horse-racing/race/p-" not in href:
            continue

        if href.startswith("http"):
            urls.add(href)
        else:
            urls.add("https://www.bbc.co.uk" + href)

    return sorted(urls)


def save_race_results(race, collection_date):
    result_date = race.get("dateTime", "")[:10]
    course = race.get("racecourse", {}).get("name")
    race_time = race.get("time")

    saved_runners = 0

    for runner in race.get("participants", []):
        record = {
            "source": "bbc_sport",
            "collection_date": collection_date,
            "result_date": result_date,
            "course": course,
            "race_time": race_time,
            "race_name": race.get("raceName"),
            "race_id": race.get("raceId"),
            "status": race.get("status"),
            "going": race.get("going", {}).get("brief"),
            "distance": race.get("distance", {}).get("displayDistance"),
            "field_size": race.get("numberOfRunners"),

            "horse": runner.get("horseName"),
            "finish_position": runner.get("rank"),
            "sp": runner.get("startingPrice") or runner.get("odds"),
            "favourite_position": runner.get("favouritePosition"),
            "trainer": runner.get("trainer"),
            "jockey": runner.get("jockey"),
            "age": runner.get("age"),
            "weight": runner.get("weight"),
            "distance_beaten": runner.get("distance"),
            "status_runner": runner.get("status"),

            "raw": runner,
        }

        append_jsonl(
            sport="horses",
            data_type="runner_results",
            record=record,
        )

        saved_runners += 1

    return saved_runners


def collect_bbc_horse_results():
    collection_date = datetime.now(timezone.utc).date().isoformat()

    race_urls = discover_race_urls()

    print("BBC Horse Results")
    print("-" * 40)
    print(f"Found race URLs: {len(race_urls)}")

    saved_races = 0
    saved_runners = 0
    skipped = 0

    for url in race_urls:
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=20,
            )
            response.raise_for_status()

            data = extract_initial_data(response.text)

            if not data:
                skipped += 1
                print(f"SKIP no initial data: {url}")
                continue

            race = find_race_data(data)

            if not race:
                skipped += 1
                print(f"SKIP no race data: {url}")
                continue

            print(
                f"{race.get('racecourse', {}).get('name')} "
                f"{race.get('time')} "
                f"STATUS={race.get('status')}"
            )

            if race.get("status") != "PostEvent":
                skipped += 1
                continue

            runners_saved = save_race_results(race, collection_date)

            saved_races += 1
            saved_runners += runners_saved

            print(
                f"OK {race.get('racecourse', {}).get('name')} "
                f"{race.get('time')} | {race.get('raceId')} | "
                f"{runners_saved} runners"
            )

            time.sleep(0.3)

        except Exception as exc:
            skipped += 1
            print(f"FAILED {url}: {exc}")

    print("-" * 40)
    print(f"Saved races: {saved_races}")
    print(f"Saved runners: {saved_runners}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    collect_bbc_horse_results()
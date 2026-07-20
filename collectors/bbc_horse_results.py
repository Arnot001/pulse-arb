import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.data_store import append_jsonl


RESULTS_URL = "https://www.bbc.co.uk/sport/horse-racing/uk-ireland/results"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1


def build_session():
    """
    Build a reusable requests session with limited automatic retries.

    Retries temporary connection errors and common transient server errors,
    but does not leave the live engine blocked for a long period.
    """
    retry_strategy = Retry(
        total=REQUEST_RETRIES,
        connect=REQUEST_RETRIES,
        read=REQUEST_RETRIES,
        status=REQUEST_RETRIES,
        backoff_factor=RETRY_BACKOFF_SECONDS,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def extract_initial_data(html):
    match = re.search(r'window\.__INITIAL_DATA__="(.*?)";', html)

    if not match:
        return None

    raw = match.group(1)

    try:
        decoded = raw.encode("utf-8").decode("unicode_escape")
        return json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"WARNING: BBC initial data could not be decoded: {exc}")
        return None


def find_race_data(data):
    if not isinstance(data, dict):
        return None

    for key, value in data.get("data", {}).items():
        if not key.startswith("horse-racing-racecard?"):
            continue

        if not isinstance(value, dict):
            continue

        return value.get("data", {}).get("race")

    return None


def discover_race_urls(session):
    """
    Discover BBC race result URLs.

    Returns an empty list when BBC is temporarily unavailable so that the
    wider live engine can continue running.
    """
    try:
        response = session.get(
            RESULTS_URL,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

    except requests.exceptions.Timeout:
        print(
            "WARNING: BBC results request timed out. "
            "Results collection will retry on the next live-engine cycle."
        )
        return []

    except requests.exceptions.ConnectionError as exc:
        print(
            "WARNING: BBC results could not be reached "
            f"({type(exc).__name__}). "
            "Results collection will retry on the next live-engine cycle."
        )
        return []

    except requests.exceptions.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        print(
            f"WARNING: BBC results returned HTTP {status_code}. "
            "Results collection will retry on the next live-engine cycle."
        )
        return []

    except requests.exceptions.RequestException as exc:
        print(
            "WARNING: BBC results request failed: "
            f"{type(exc).__name__}: {exc}"
        )
        return []

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
    session = build_session()

    print("BBC Horse Results")
    print("-" * 40)

    try:
        race_urls = discover_race_urls(session)

        print(f"Found race URLs: {len(race_urls)}")

        if not race_urls:
            print("No BBC race URLs available during this cycle.")
            print("The live engine will retry on its next scheduled check.")
            print("-" * 40)
            print("Saved races: 0")
            print("Saved runners: 0")
            print("Skipped: 0")
            return {
                "saved_races": 0,
                "saved_runners": 0,
                "skipped": 0,
                "source_available": False,
            }

        saved_races = 0
        saved_runners = 0
        skipped = 0

        for url in race_urls:
            try:
                response = session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
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

                course = race.get("racecourse", {}).get("name")
                race_time = race.get("time")
                race_status = race.get("status")

                print(
                    f"{course} "
                    f"{race_time} "
                    f"STATUS={race_status}"
                )

                if race_status != "PostEvent":
                    skipped += 1
                    continue

                runners_saved = save_race_results(
                    race,
                    collection_date,
                )

                saved_races += 1
                saved_runners += runners_saved

                print(
                    f"OK {course} "
                    f"{race_time} | {race.get('raceId')} | "
                    f"{runners_saved} runners"
                )

                time.sleep(0.3)

            except requests.exceptions.Timeout:
                skipped += 1
                print(f"SKIP timed out: {url}")

            except requests.exceptions.ConnectionError:
                skipped += 1
                print(f"SKIP connection failed: {url}")

            except requests.exceptions.HTTPError as exc:
                skipped += 1

                status_code = (
                    exc.response.status_code
                    if exc.response is not None
                    else "unknown"
                )

                print(f"SKIP HTTP {status_code}: {url}")

            except requests.exceptions.RequestException as exc:
                skipped += 1
                print(
                    f"SKIP request failure: {url} | "
                    f"{type(exc).__name__}: {exc}"
                )

            except Exception as exc:
                skipped += 1
                print(
                    f"SKIP unexpected failure: {url} | "
                    f"{type(exc).__name__}: {exc}"
                )

        print("-" * 40)
        print(f"Saved races: {saved_races}")
        print(f"Saved runners: {saved_runners}")
        print(f"Skipped: {skipped}")

        return {
            "saved_races": saved_races,
            "saved_runners": saved_runners,
            "skipped": skipped,
            "source_available": True,
        }

    finally:
        session.close()


if __name__ == "__main__":
    collect_bbc_horse_results()
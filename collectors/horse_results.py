import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from app.data_store import append_jsonl

load_dotenv()

BASE_URL = "https://api.theracingapi.com/v1"


def get_auth():
    username = os.getenv("RACING_API_USERNAME")
    password = os.getenv("RACING_API_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "Missing RACING_API_USERNAME or RACING_API_PASSWORD in .env"
        )

    return username, password


def collect_horse_results():
    auth = get_auth()

    target_date = (
        datetime.now(timezone.utc).date()
        - timedelta(days=1)
    ).isoformat()

    url = f"{BASE_URL}/results"

    response = requests.get(
        url,
        auth=auth,
        params={"date": target_date},
        timeout=20,
    )

    if response.status_code == 401:
        print(
            "The Racing API results endpoint is not authorised on this plan. "
            "Use public results scraping instead."
        )
        return

    response.raise_for_status()
    data = response.json()

    saved = 0
    races = data.get("results", data if isinstance(data, list) else [])

    for race in races:
        record = {
            "source": "the_racing_api",
            "collection_date": datetime.now(timezone.utc).date().isoformat(),
            "result_date": target_date,
            "raw": race,
        }

        append_jsonl(
            sport="horses",
            data_type="results",
            record=record,
        )

        saved += 1

    print(f"Saved {saved} horse result records for {target_date}.")


if __name__ == "__main__":
    collect_horse_results()
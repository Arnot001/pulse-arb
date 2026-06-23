import os
import requests
from datetime import datetime, timezone
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


def collect_real_horse_racecards():
    auth = get_auth()

    today = datetime.now(timezone.utc).date().isoformat()

    url = f"{BASE_URL}/racecards/free"

    response = requests.get(
        url,
        auth=auth,
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    saved = 0

    for race in data.get("racecards", data if isinstance(data, list) else []):
        record = {
            "source": "the_racing_api",
            "collection_date": today,
            "raw": race,
        }

        append_jsonl(
            sport="horses",
            data_type="racecards",
            record=record,
        )

        saved += 1

    print(f"Saved {saved} real horse racecard records.")


if __name__ == "__main__":
    collect_real_horse_racecards()
import hashlib
import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.data_store import append_jsonl


URL = "https://www.britishhorseracing.com/racing-updates/"
DEFAULT_INTERVAL_SECONDS = 300


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def event_hash(event):
    raw = json.dumps(event, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_bha_updates():
    response = requests.get(
        URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": "https://www.google.com/",
        },
        timeout=20,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = clean_text(soup.get_text(" "))

    events = []

    keywords = [
        "Non Runners",
        "Going",
        "Weather",
        "Inspections",
        "Abandoned",
        "Delayed",
    ]

    for keyword in keywords:
        if keyword.lower() in text.lower():
            events.append(
                {
                    "source": "bha",
                    "event_type": keyword.lower().replace(" ", "_"),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "url": URL,
                    "summary": keyword,
                    "raw_text_sample": text[:5000],
                }
            )

    return events


def collect_bha_intelligence_once():
    events = fetch_bha_updates()
    saved = 0

    for event in events:
        event["event_hash"] = event_hash(event)

        append_jsonl(
            sport="horses",
            data_type="bha_intelligence",
            record=event,
        )

        saved += 1

    print(f"BHA intelligence events saved: {saved}")
    return saved


def monitor_bha_intelligence(interval_seconds=DEFAULT_INTERVAL_SECONDS):
    print("Pulse BHA Intelligence Monitor started.")
    print(f"Checking every {interval_seconds} seconds.")

    while True:
        try:
            collect_bha_intelligence_once()
        except KeyboardInterrupt:
            print("BHA Intelligence Monitor stopped.")
            break
        except Exception as e:
            print(f"BHA monitor error: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    monitor_bha_intelligence()
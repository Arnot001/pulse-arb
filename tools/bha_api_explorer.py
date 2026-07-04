import json
import time
from pathlib import Path

import requests


BASE_URL = "https://api09.horseracing.software/bha/v1"

OUTPUT_DIR = Path("data/race_intelligence/api_explorer")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


ENDPOINTS = [
    "fixtures",
    "courses",
    "meetings",
    "racecards",
    "races",
    "entries",
    "runners",
    "horses",
    "jockeys",
    "trainers",
    "results",
    "nonrunners",
    "updates",
    "going",
]


def probe(endpoint):
    url = f"{BASE_URL}/{endpoint}"

    params = {
        "fromdate": "20260703",
        "todate": "20260705",
        "per_page": 5,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Origin": "https://www.britishhorseracing.com",
                "Referer": "https://www.britishhorseracing.com/",
            },
        )

        content_type = response.headers.get("content-type", "")

        record = {
            "endpoint": endpoint,
            "url": response.url,
            "status_code": response.status_code,
            "content_type": content_type,
            "ok": response.ok,
        }

        if "application/json" in content_type:
            try:
                data = response.json()
                record["sample"] = data
            except Exception as exc:
                record["sample_error"] = str(exc)
                record["text_sample"] = response.text[:1000]
        else:
            record["text_sample"] = response.text[:1000]

        return record

    except Exception as exc:
        return {
            "endpoint": endpoint,
            "url": url,
            "status_code": None,
            "ok": False,
            "error": str(exc),
        }


def main():
    results = []

    for endpoint in ENDPOINTS:
        print(f"Probing /{endpoint}...")

        result = probe(endpoint)
        results.append(result)

        status = result.get("status_code")
        ok = "OK" if result.get("ok") else "NO"

        print(f"{ok} | {status} | /{endpoint}")

        time.sleep(0.75)

    output_file = OUTPUT_DIR / "bha_api_probe.json"

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"Saved API probe results to: {output_file}")

    print()
    print("Summary")
    print("-" * 60)

    for result in results:
        print(
            f"{str(result.get('status_code')):<6}"
            f"{'OK' if result.get('ok') else 'NO':<5}"
            f"/{result['endpoint']}"
        )


if __name__ == "__main__":
    main()
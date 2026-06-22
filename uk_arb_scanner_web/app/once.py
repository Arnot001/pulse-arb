import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from app.core.scanner import run_scan


load_dotenv()


def print_summary(results):
    Path("app/output").mkdir(parents=True, exist_ok=True)

    with open("app/output/latest_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print()
    print("=== UK Arb Scanner Daily Results ===")
    print(f"Events found: {len(results.get('events', []))}")
    print(f"Arbs found: {len(results.get('arbs', []))}")
    print(f"Near-arbs found: {len(results.get('near_arbs', []))}")
    print("Saved: app/output/latest_results.json")


if __name__ == "__main__":
    results = asyncio.run(run_scan(send_alerts=True))
    print_summary(results)
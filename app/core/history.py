import json
from pathlib import Path
from collections import defaultdict


OUTPUT_DIR = Path("app/output")
HISTORY_FILE = OUTPUT_DIR / "scan_history.jsonl"
LATEST_SCAN_FILE = OUTPUT_DIR / "latest_scan.json"


def save_scan_results(results):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item) + "\n")


def save_latest_scan(arbs, near_arbs, last_scan, api_remaining=None, api_used=None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "arbs": arbs,
        "near_arbs": near_arbs,
        "last_scan": last_scan,
        "api_remaining": api_remaining,
        "api_used": api_used,
    }

    with LATEST_SCAN_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_latest_scan():
    if not LATEST_SCAN_FILE.exists():
        return {
            "arbs": [],
            "near_arbs": [],
            "last_scan": None,
            "api_remaining": None,
            "api_used": None,
        }

    try:
        with LATEST_SCAN_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "arbs": [],
            "near_arbs": [],
            "last_scan": None,
            "api_remaining": None,
            "api_used": None,
        }


def load_history():
    if not HISTORY_FILE.exists():
        return []

    rows = []

    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    return rows


def get_sport_stats():
    rows = load_history()
    sports = defaultdict(list)

    for row in rows:
        sport = row.get("sport")
        profit = row.get("profit_percent")

        if sport is not None and profit is not None:
            sports[sport].append(profit)

    output = []

    for sport, profits in sports.items():
        output.append({
            "sport": sport,
            "count": len(profits),
            "avg_profit": round(sum(profits) / len(profits), 2),
            "best_profit": round(max(profits), 2),
        })

    output.sort(key=lambda x: x["avg_profit"], reverse=True)
    return output


def get_bookmaker_stats():
    rows = load_history()
    books = defaultdict(list)

    for row in rows:
        profit = row.get("profit_percent")

        if profit is None:
            continue

        for book in row.get("books", []):
            books[book].append(profit)

    output = []

    for bookmaker, profits in books.items():
        output.append({
            "bookmaker": bookmaker,
            "count": len(profits),
            "avg_profit": round(sum(profits) / len(profits), 2),
            "best_profit": round(max(profits), 2),
        })

    output.sort(key=lambda x: x["avg_profit"], reverse=True)
    return output
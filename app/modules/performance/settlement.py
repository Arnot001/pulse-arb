import json
import re
from pathlib import Path
from datetime import datetime


LEDGER_FILE = Path("data/betting/bet_ledger.jsonl")
SETTLED_FILE = Path("data/betting/bet_ledger_settled.jsonl")

RESULT_DIRS = [
    Path("data/horses/attheraces_results"),
    Path("data/horses/sporting_life_results"),
    Path("data/horses/public_results"),
    Path("data/horses/runner_results"),
]


def normalise(value):
    value = str(value or "").lower().strip()

    value = re.sub(
        r"\((aw|gb|ire|fr|usa|aus)\)",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.replace("&", "and")
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def normalise_time(value):
    value = str(value or "").strip()

    if not value:
        return ""

    parts = value.split(":")

    if len(parts) != 2:
        return value

    try:
        hour = int(parts[0])
        minute = int(parts[1])

        if hour > 12:
            hour -= 12

        return f"{hour}:{minute:02d}"

    except Exception:
        return value


def load_jsonl(file_path):
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except Exception:
                pass

    return rows


def load_results():
    rows = []

    for folder in RESULT_DIRS:
        if not folder.exists():
            continue

        for file_path in sorted(folder.glob("*.jsonl")):
            rows.extend(load_jsonl(file_path))

    return rows


def build_result_index():
    index = {}

    for row in load_results():
        if row.get("horse") and row.get("finish_position") is not None:
            result_date = row.get("result_date") or row.get("collection_date")
            course = row.get("course")
            race_time = row.get("race_time")
            horse = row.get("horse")

            key = (
                normalise(result_date),
                normalise(course),
                normalise_time(race_time),
                normalise(horse),
            )

            index[key] = {
                "result_date": result_date,
                "course": course,
                "race_time": race_time,
                "horse": horse,
                "position": row.get("finish_position"),
                "sp": row.get("sp"),
                "favourite": (
                    row.get("favourite")
                    or row.get("favourite_position")
                ),
                "race_stage": row.get("status"),
                "source": row.get("source"),
            }

            continue

        raw = row.get("raw", row)
        result_date = row.get("result_date") or row.get("collection_date")
        course = raw.get("course")
        race_time = raw.get("race_time")

        for runner in raw.get("positions", []):
            horse = runner.get("horse")

            key = (
                normalise(result_date),
                normalise(course),
                normalise_time(race_time),
                normalise(horse),
            )

            index[key] = {
                "result_date": result_date,
                "course": course,
                "race_time": race_time,
                "horse": horse,
                "position": runner.get("position"),
                "sp": runner.get("sp"),
                "favourite": runner.get("favourite"),
                "race_stage": raw.get("race_stage"),
                "source": row.get("source"),
            }

    return index


def build_loose_result_index(index):
    loose = {}

    for key, result in index.items():
        result_date, course, race_time, horse = key
        loose_key = (result_date, course, horse)
        loose.setdefault(loose_key, []).append(result)

    return loose


def settle_bets(stake=1.0):
    bets = load_jsonl(LEDGER_FILE)
    index = build_result_index()
    loose_index = build_loose_result_index(index)

    settled_rows = []
    open_bets = []
    updated_bets = []
    newly_settled = []
    unmatched_samples = []

    already_settled_count = 0

    for bet in bets:
        if bet.get("status") == "SETTLED":
            already_settled_count += 1
            settled_rows.append(bet)
            updated_bets.append(bet)
            continue

        key = (
            normalise(bet.get("date")),
            normalise(bet.get("course")),
            normalise_time(bet.get("race_time")),
            normalise(bet.get("horse")),
        )

        result = index.get(key)

        if not result:
            loose_key = (
                normalise(bet.get("date")),
                normalise(bet.get("course")),
                normalise(bet.get("horse")),
            )

            loose_matches = loose_index.get(loose_key, [])

            if len(loose_matches) == 1:
                result = loose_matches[0]

        if not result:
            open_bets.append(bet)
            updated_bets.append(bet)

            if len(unmatched_samples) < 20:
                unmatched_samples.append({
                    "date": bet.get("date"),
                    "course": bet.get("course"),
                    "race_time": bet.get("race_time"),
                    "horse": bet.get("horse"),
                    "normalised_key": key,
                })

            continue

        bet_stake = float(bet.get("stake") or stake)
        won = str(result.get("position")) == "1"
        decimal_odds = bet.get("best_odds_decimal")

        if decimal_odds:
            decimal_odds = float(decimal_odds)
            returned = bet_stake * decimal_odds if won else 0.0
            profit = returned - bet_stake
            roi = round((profit / bet_stake) * 100, 2)
        else:
            returned = None
            profit = None
            roi = None

        settled_bet = dict(bet)
        settled_bet["status"] = "SETTLED"
        settled_bet["settled_at"] = datetime.now().isoformat(timespec="seconds")
        settled_bet["result_position"] = result.get("position")
        settled_bet["sp"] = result.get("sp")
        settled_bet["won"] = won
        settled_bet["stake"] = bet_stake
        settled_bet["returned"] = returned
        settled_bet["profit"] = profit
        settled_bet["roi"] = roi
        settled_bet["result_source"] = result.get("source")

        settled_rows.append(settled_bet)
        updated_bets.append(settled_bet)
        newly_settled.append(settled_bet)

    SETTLED_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SETTLED_FILE.open("w", encoding="utf-8") as f:
        for row in settled_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with LEDGER_FILE.open("w", encoding="utf-8") as f:
        for row in updated_bets:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {
        "ledger_bets": len(bets),
        "results_indexed": len(index),
        "already_settled": already_settled_count,
        "newly_settled": len(newly_settled),
        "total_settled": len(settled_rows),
        "open": len(open_bets),
        "unmatched_samples": unmatched_samples,
        "settled_file": str(SETTLED_FILE),
        "ledger_file": str(LEDGER_FILE),
    }


if __name__ == "__main__":
    report = settle_bets(1.0)

    print("Settlement Complete")
    print("-" * 50)
    print(f"Ledger bets:       {report['ledger_bets']}")
    print(f"Results indexed:   {report['results_indexed']}")
    print(f"Already settled:   {report['already_settled']}")
    print(f"Newly settled:     {report['newly_settled']}")
    print(f"Total settled:     {report['total_settled']}")
    print(f"Still open:        {report['open']}")

    if report["unmatched_samples"]:
        print()
        print("Unmatched open bets:")
        for item in report["unmatched_samples"]:
            print(
                f"- {item['date']} | {item['course']} | "
                f"{item['race_time']} | {item['horse']}"
            )

    print()
    print(f"File: {report['settled_file']}")

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.modules.performance.each_way import (
    build_racecard_index,
    enrich_bet_with_each_way,
)


LEDGER_FILE = Path("data/betting/bet_ledger.jsonl")
SETTLED_FILE = Path("data/betting/bet_ledger_settled.jsonl")

RESULT_DIRS = [
    Path("data/horses/attheraces_results"),
    Path("data/horses/sporting_life_results"),
    Path("data/horses/public_results"),
    Path("data/horses/runner_results"),
]


COUNTRY_SUFFIX_PATTERN = re.compile(
    r"\((?:"
    r"aw|gb|ire|fr|usa|aus|a|br|chi|jpn|rsa|can|ger|"
    r"ita|spa|nz|arg|uru|hk|uae"
    r")\)",
    flags=re.IGNORECASE,
)


def normalise(value):
    value = str(value or "").lower().strip()

    value = COUNTRY_SUFFIX_PATTERN.sub("", value)

    value = value.replace("&", "and")
    value = value.replace("’", "'")
    value = value.replace("`", "'")

    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def parse_time_minutes(value):
    value = str(value or "").strip()

    if not value:
        return None

    parts = value.split(":")

    if len(parts) < 2:
        return None

    try:
        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or hour > 23:
            return None

        if minute < 0 or minute > 59:
            return None

        return (hour * 60) + minute

    except Exception:
        return None


def twelve_hour_minutes(total_minutes):
    if total_minutes is None:
        return None

    hour = (total_minutes // 60) % 24
    minute = total_minutes % 60

    if hour == 0:
        hour = 12
    elif hour > 12:
        hour -= 12

    return (hour * 60) + minute


def times_match(left, right):
    left_minutes = parse_time_minutes(left)
    right_minutes = parse_time_minutes(right)

    if left_minutes is None or right_minutes is None:
        return False

    # Exact 24-hour match.
    if left_minutes == right_minutes:
        return True

    # 12-hour versus 24-hour representation.
    if twelve_hour_minutes(left_minutes) == twelve_hour_minutes(
        right_minutes
    ):
        return True

    # Some sources store UTC while others show UK local/BST.
    if abs(left_minutes - right_minutes) == 60:
        return True

    # Handles 12-hour display plus one-hour timezone difference.
    left_12 = twelve_hour_minutes(left_minutes)
    right_12 = twelve_hour_minutes(right_minutes)

    if (
        left_12 is not None
        and right_12 is not None
        and abs(left_12 - right_12) == 60
    ):
        return True

    return False


def position_number(value):
    if value is None:
        return None

    text = str(value).strip().lower()

    if not text:
        return None

    match = re.match(r"^(\d+)", text)

    if not match:
        return None

    try:
        return int(match.group(1))
    except Exception:
        return None


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
                continue

    return rows


def load_results():
    rows = []

    for folder in RESULT_DIRS:
        if not folder.exists():
            continue

        for file_path in sorted(folder.glob("*.jsonl")):
            rows.extend(load_jsonl(file_path))

    return rows


def make_runner_key(result_date, course, race_time, horse):
    return (
        normalise(result_date),
        normalise(course),
        str(race_time or "").strip(),
        normalise(horse),
    )


def make_race_key(result_date, course, race_time):
    return (
        normalise(result_date),
        normalise(course),
        str(race_time or "").strip(),
    )


def better_runner_result(existing, candidate):
    if existing is None:
        return candidate

    existing_position = position_number(
        existing.get("position")
    )
    candidate_position = position_number(
        candidate.get("position")
    )

    # Never allow a duplicate None-position row to overwrite
    # a valid finishing result.
    if (
        existing_position is not None
        and candidate_position is None
    ):
        return existing

    if (
        candidate_position is not None
        and existing_position is None
    ):
        return candidate

    # Prefer Sporting Life enriched/full results where available.
    preferred_sources = {
        "sporting_life_enriched": 3,
        "sporting_life": 2,
        "bbc_sport": 1,
    }

    existing_priority = preferred_sources.get(
        existing.get("source"),
        0,
    )
    candidate_priority = preferred_sources.get(
        candidate.get("source"),
        0,
    )

    if candidate_priority > existing_priority:
        return candidate

    return existing


def add_runner_result(index, result):
    key = make_runner_key(
        result.get("result_date"),
        result.get("course"),
        result.get("race_time"),
        result.get("horse"),
    )

    if not all(key):
        return

    index[key] = better_runner_result(
        index.get(key),
        result,
    )


def add_race_record(race_index, race):
    key = make_race_key(
        race.get("result_date"),
        race.get("course"),
        race.get("race_time"),
    )

    if not all(key):
        return

    existing = race_index.get(key)

    if existing is None:
        race_index[key] = race
        return

    existing_positions = existing.get("positions") or []
    candidate_positions = race.get("positions") or []

    if len(candidate_positions) > len(existing_positions):
        race_index[key] = race


def build_result_indexes():
    runner_index = {}
    race_index = {}

    for row in load_results():
        result_date = (
            row.get("result_date")
            or row.get("collection_date")
        )

        # Flat runner result format.
        if row.get("horse"):
            runner_result = {
                "result_date": result_date,
                "course": row.get("course"),
                "race_time": row.get("race_time"),
                "horse": row.get("horse"),
                "position": row.get("finish_position"),
                "sp": row.get("sp"),
                "favourite": (
                    row.get("favourite")
                    or row.get("favourite_position")
                ),
                "race_stage": row.get("status"),
                "source": row.get("source"),
            }

            add_runner_result(
                runner_index,
                runner_result,
            )

        raw = row.get("raw")

        if not isinstance(raw, dict):
            continue

        course = raw.get("course")
        race_time = raw.get("race_time")
        positions = raw.get("positions") or []

        winner = raw.get("winner") or {}

        if not winner and positions:
            winner = next(
                (
                    item
                    for item in positions
                    if position_number(
                        item.get("position")
                    ) == 1
                ),
                {},
            )

        race_record = {
            "result_date": result_date,
            "course": course,
            "race_time": race_time,
            "race_name": raw.get("race_name"),
            "race_stage": raw.get("race_stage"),
            "winner": winner,
            "positions": positions,
            "source": row.get("source"),
        }

        add_race_record(
            race_index,
            race_record,
        )

        for runner in positions:
            runner_result = {
                "result_date": result_date,
                "course": course,
                "race_time": race_time,
                "horse": runner.get("horse"),
                "position": runner.get("position"),
                "sp": runner.get("sp"),
                "favourite": runner.get("favourite"),
                "race_stage": raw.get("race_stage"),
                "source": row.get("source"),
            }

            add_runner_result(
                runner_index,
                runner_result,
            )

    return runner_index, race_index


def build_loose_runner_index(runner_index):
    loose = defaultdict(list)

    for key, result in runner_index.items():
        result_date, course, race_time, horse = key

        loose_key = (
            result_date,
            course,
            horse,
        )

        loose[loose_key].append(result)

    return loose


def find_runner_result(
    bet,
    runner_index,
    loose_runner_index,
):
    target_date = normalise(bet.get("date"))
    target_course = normalise(bet.get("course"))
    target_horse = normalise(bet.get("horse"))
    target_time = bet.get("race_time")

    # First attempt: date/course/horse with compatible time.
    for key, result in runner_index.items():
        result_date, course, race_time, horse = key

        if result_date != target_date:
            continue

        if course != target_course:
            continue

        if horse != target_horse:
            continue

        if times_match(target_time, race_time):
            return result, "runner_exact_or_time_alias"

    # Second attempt: unique date/course/horse.
    loose_key = (
        target_date,
        target_course,
        target_horse,
    )

    matches = loose_runner_index.get(loose_key, [])

    valid_matches = [
        result
        for result in matches
        if position_number(result.get("position"))
        is not None
    ]

    if len(valid_matches) == 1:
        return valid_matches[0], "runner_loose_unique"

    return None, None


def find_race_result(bet, race_index):
    target_date = normalise(bet.get("date"))
    target_course = normalise(bet.get("course"))
    target_time = bet.get("race_time")

    possible = []

    for key, race in race_index.items():
        result_date, course, race_time = key

        if result_date != target_date:
            continue

        if course != target_course:
            continue

        if times_match(target_time, race_time):
            possible.append(race)

    if len(possible) == 1:
        return possible[0], "race_exact_or_time_alias"

    # If there is only one completed result for that
    # date/course, use it as a final fallback.
    same_course = [
        race
        for key, race in race_index.items()
        if key[0] == target_date
        and key[1] == target_course
    ]

    if len(same_course) == 1:
        return same_course[0], "race_course_unique"

    return None, None


def settle_from_completed_race(bet, race):
    winner = race.get("winner") or {}
    winner_name = normalise(winner.get("horse"))
    bet_horse = normalise(bet.get("horse"))

    positions = race.get("positions") or []

    for runner in positions:
        if normalise(runner.get("horse")) != bet_horse:
            continue

        return {
            "position": runner.get("position"),
            "sp": runner.get("sp"),
            "source": race.get("source"),
            "race_stage": race.get("race_stage"),
            "winner": winner.get("horse"),
        }

    if winner_name and winner_name == bet_horse:
        return {
            "position": 1,
            "sp": winner.get("sp"),
            "source": race.get("source"),
            "race_stage": race.get("race_stage"),
            "winner": winner.get("horse"),
        }

    # Sporting Life's summary may only include top finishers.
    # Once the race is confirmed complete, absence from the
    # displayed positions means the selection did not win.
    if winner_name:
        return {
            "position": "UNPLACED",
            "sp": None,
            "source": race.get("source"),
            "race_stage": race.get("race_stage"),
            "winner": winner.get("horse"),
        }

    return None


def settle_bets(stake=1.0):
    bets = load_jsonl(LEDGER_FILE)

    runner_index, race_index = build_result_indexes()
    racecard_index = build_racecard_index()

    loose_runner_index = build_loose_runner_index(
        runner_index
    )

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

        result, match_method = find_runner_result(
            bet,
            runner_index,
            loose_runner_index,
        )

        if result:
            result_position = position_number(
                result.get("position")
            )

            # Ignore duplicate BBC records that represent the
            # runner but contain no confirmed finish position.
            if result_position is None:
                result = None
                match_method = None

        if not result:
            race, race_match_method = find_race_result(
                bet,
                race_index,
            )

            if race:
                result = settle_from_completed_race(
                    bet,
                    race,
                )

                if result:
                    match_method = race_match_method

        if not result:
            open_bets.append(bet)
            updated_bets.append(bet)

            if len(unmatched_samples) < 30:
                unmatched_samples.append({
                    "date": bet.get("date"),
                    "course": bet.get("course"),
                    "race_time": bet.get("race_time"),
                    "horse": bet.get("horse"),
                })

            continue

        raw_position = result.get("position")
        numeric_position = position_number(raw_position)
        won = numeric_position == 1

        bet_stake = float(
            bet.get("stake") or stake
        )

        decimal_odds = bet.get(
            "best_odds_decimal"
        )

        if decimal_odds is not None:
            try:
                decimal_odds = float(decimal_odds)
            except Exception:
                decimal_odds = None

        if decimal_odds:
            returned = (
                bet_stake * decimal_odds
                if won
                else 0.0
            )

            profit = returned - bet_stake

            roi = round(
                (profit / bet_stake) * 100,
                2,
            )
        else:
            returned = None
            profit = None
            roi = None

        settled_bet = dict(bet)

        settled_bet["status"] = "SETTLED"
        settled_bet["settled_at"] = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        settled_bet["result_position"] = (
            numeric_position
            if numeric_position is not None
            else raw_position
        )

        settled_bet["sp"] = result.get("sp")
        settled_bet["won"] = won
        settled_bet["stake"] = bet_stake

        settled_bet["returned"] = (
            round(returned, 2)
            if returned is not None
            else None
        )

        settled_bet["profit"] = (
            round(profit, 2)
            if profit is not None
            else None
        )

        settled_bet["roi"] = roi

        settled_bet["result_source"] = (
            result.get("source")
        )

        settled_bet["result_match_method"] = (
            match_method
        )

        settled_bet["race_winner"] = (
            result.get("winner")
        )

        # Add a separate simulated each-way result without altering
        # the established win-only stake, return, profit or ROI.
        settled_bet = enrich_bet_with_each_way(
            settled_bet,
            racecard_index=racecard_index,
            unit_stake=bet_stake,
        )

        settled_rows.append(settled_bet)
        updated_bets.append(settled_bet)
        newly_settled.append(settled_bet)

    SETTLED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with SETTLED_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        for row in settled_rows:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    with LEDGER_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        for row in updated_bets:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    return {
        "ledger_bets": len(bets),
        "runner_results_indexed": len(
            runner_index
        ),
        "races_indexed": len(race_index),
        "results_indexed": (
            len(runner_index)
            + len(race_index)
        ),
        "already_settled": (
            already_settled_count
        ),
        "newly_settled": len(
            newly_settled
        ),
        "total_settled": len(
            settled_rows
        ),
        "open": len(open_bets),
        "unmatched_samples": (
            unmatched_samples
        ),
        "settled_file": str(
            SETTLED_FILE
        ),
        "ledger_file": str(
            LEDGER_FILE
        ),
    }


if __name__ == "__main__":
    report = settle_bets(1.0)

    print("Settlement Complete")
    print("-" * 60)
    print(
        f"Ledger bets:          "
        f"{report['ledger_bets']}"
    )
    print(
        f"Runner results:       "
        f"{report['runner_results_indexed']}"
    )
    print(
        f"Completed races:      "
        f"{report['races_indexed']}"
    )
    print(
        f"Already settled:      "
        f"{report['already_settled']}"
    )
    print(
        f"Newly settled:        "
        f"{report['newly_settled']}"
    )
    print(
        f"Total settled:        "
        f"{report['total_settled']}"
    )
    print(
        f"Still open:           "
        f"{report['open']}"
    )

    if report["unmatched_samples"]:
        print()
        print("Still unmatched:")

        for item in report[
            "unmatched_samples"
        ]:
            print(
                f"- {item['date']} | "
                f"{item['course']} | "
                f"{item['race_time']} | "
                f"{item['horse']}"
            )

    print()
    print(f"File: {report['settled_file']}")
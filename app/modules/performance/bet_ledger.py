import json
from pathlib import Path
from datetime import datetime

from app.modules.performance.bet_qualifier import qualifies_as_official_bet


LEDGER_DIR = Path("data/betting")
LEDGER_FILE = LEDGER_DIR / "bet_ledger.jsonl"
SETTLED_LEDGER_FILE = LEDGER_DIR / "bet_ledger_settled.jsonl"

ODDS_DIR = Path("data/horses/odds_snapshots")

LEDGER_DIR.mkdir(parents=True, exist_ok=True)


def make_bet_id(row):
    parts = [
        row.get("snapshot_date"),
        row.get("course"),
        row.get("race_time"),
        row.get("horse"),
        row.get("strategy"),
    ]

    return "|".join(
        str(part or "").lower().strip()
        for part in parts
    )


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


def load_open_bets():
    return load_jsonl(LEDGER_FILE)


def load_settled_bets():
    return load_jsonl(SETTLED_LEDGER_FILE)


def load_official_settled_bets():
    return [
        bet
        for bet in load_settled_bets()
        if bet.get("official_bet") is True
    ]


def filter_performance_bets(
    bets,
    min_score=None,
    bet_group="all",
):
    """
    Filter settled bets for Performance Centre analysis.

    bet_group values:
        all         - every settled Pulse selection
        official    - official Pulse bets only
        watchlist   - non-official selections scoring 80+
        predictions - non-official selections scoring below 80
    """

    filtered = []

    try:
        parsed_min_score = (
            int(min_score)
            if min_score is not None
            else None
        )
    except (TypeError, ValueError):
        parsed_min_score = None

    valid_groups = {
        "all",
        "official",
        "watchlist",
        "predictions",
    }

    if bet_group not in valid_groups:
        bet_group = "all"

    for bet in bets:
        try:
            pulse_score = int(
                float(bet.get("pulse_score") or 0)
            )
        except (TypeError, ValueError):
            pulse_score = 0

        if (
            parsed_min_score is not None
            and pulse_score < parsed_min_score
        ):
            continue

        is_official = bet.get("official_bet") is True

        if bet_group == "official" and not is_official:
            continue

        if (
            bet_group == "watchlist"
            and (
                is_official
                or pulse_score < 80
            )
        ):
            continue

        if (
            bet_group == "predictions"
            and (
                is_official
                or pulse_score >= 80
            )
        ):
            continue

        filtered.append(bet)

    return filtered


def calculate_ledger_stats(bets):
    total = len(bets)

    winners = len([
        bet
        for bet in bets
        if bet.get("won") is True
    ])

    losers = len([
        bet
        for bet in bets
        if bet.get("won") is False
    ])

    # ROI and profit should only use bets that had a captured price.
    priced_bets = [
        bet
        for bet in bets
        if bet.get("best_odds_decimal") is not None
        and bet.get("profit") is not None
    ]

    stake = sum(
        float(bet.get("stake") or 0)
        for bet in priced_bets
    )

    profit = sum(
        float(bet.get("profit") or 0)
        for bet in priced_bets
    )

    strike_rate = (
        round((winners / total) * 100, 2)
        if total
        else 0
    )

    roi = (
        round((profit / stake) * 100, 2)
        if stake
        else 0
    )

    return {
        "total": total,
        "winners": winners,
        "losers": losers,
        "priced_total": len(priced_bets),
        "stake": round(stake, 2),
        "profit": round(profit, 2),
        "strike_rate": strike_rate,
        "roi": roi,
    }


def get_verified_official_stats(min_score=None):
    return calculate_ledger_stats(
        filter_performance_bets(
            load_official_settled_bets(),
            min_score=min_score,
            bet_group="official",
        )
    )


def get_all_settled_stats(
    min_score=None,
    bet_group="all",
):
    return calculate_ledger_stats(
        filter_performance_bets(
            load_settled_bets(),
            min_score=min_score,
            bet_group=bet_group,
        )
    )


def calculate_each_way_stats(bets):
    eligible = [
        bet
        for bet in bets
        if bet.get("ew_available") is True
        and bet.get("ew_profit") is not None
        and bet.get("ew_total_stake") is not None
    ]

    total = len(eligible)

    placed = len([
        bet
        for bet in eligible
        if bet.get("placed") is True
    ])

    unplaced = len([
        bet
        for bet in eligible
        if bet.get("placed") is False
    ])

    stake = sum(
        float(bet.get("ew_total_stake") or 0)
        for bet in eligible
    )

    profit = sum(
        float(bet.get("ew_profit") or 0)
        for bet in eligible
    )

    place_rate = (
        round((placed / total) * 100, 2)
        if total
        else 0
    )

    roi = (
        round((profit / stake) * 100, 2)
        if stake
        else 0
    )

    return {
        "total": total,
        "placed": placed,
        "unplaced": unplaced,
        "stake": round(stake, 2),
        "profit": round(profit, 2),
        "place_rate": place_rate,
        "roi": roi,
    }


def get_verified_official_each_way_stats(
    min_score=None,
):
    return calculate_each_way_stats(
        filter_performance_bets(
            load_official_settled_bets(),
            min_score=min_score,
            bet_group="official",
        )
    )


def get_all_settled_each_way_stats(
    min_score=None,
    bet_group="all",
):
    return calculate_each_way_stats(
        filter_performance_bets(
            load_settled_bets(),
            min_score=min_score,
            bet_group=bet_group,
        )
    )


def get_bankroll_history(
    start_bank=100.0,
    min_score=None,
    bet_group="all",
):
    bankroll = start_bank
    history = []

    def history_sort_key(row):
        race_date = str(
            row.get("date") or ""
        )[:10]

        race_time = str(
            row.get("race_time") or ""
        ).strip()

        try:
            parts = race_time.split(":")

            hour = int(parts[0])
            minute = int(parts[1])

            if 1 <= hour <= 9:
                hour += 12

            sortable_time = f"{hour:02d}:{minute:02d}"

        except Exception:
            sortable_time = "99:99"

        return (
            race_date,
            sortable_time,
            row.get("settled_at") or "",
            row.get("bet_id") or "",
        )

    settled = sorted(
        filter_performance_bets(
            load_settled_bets(),
            min_score=min_score,
            bet_group=bet_group,
        ),
        key=history_sort_key,
    )

    for index, bet in enumerate(settled, start=1):
        profit = bet.get("profit")

        if profit is not None:
            bankroll += float(profit)

        race_date = str(
            bet.get("date") or ""
        )[:10]

        race_time = str(
            bet.get("race_time") or ""
        ).strip()

        race_datetime = None

        if race_date and race_time:
            try:
                parts = race_time.split(":")

                hour = int(parts[0])
                minute = int(parts[1])

                if 1 <= hour <= 9:
                    hour += 12

                race_datetime = (
                    f"{race_date}T"
                    f"{hour:02d}:{minute:02d}:00"
                )

            except Exception:
                race_datetime = None

        history.append({
            "x": index,
            "bankroll": round(bankroll, 2),
            "profit": (
                round(float(profit), 2)
                if profit is not None
                else None
            ),
            "horse": bet.get("horse"),
            "course": bet.get("course"),
            "date": race_date,
            "race_time": race_time,
            "race_datetime": race_datetime,
            "settled_at": bet.get("settled_at"),
            "won": bet.get("won"),
            "pulse_score": bet.get("pulse_score"),
            "official_bet": bet.get("official_bet"),
            "bet_type": bet.get("bet_type"),
            "odds_available": (
                bet.get("best_odds_decimal")
                is not None
            ),
        })

    return history


def get_each_way_bankroll_history(
    start_bank=100.0,
    min_score=None,
    bet_group="all",
):
    bankroll = start_bank
    history = []

    def history_sort_key(row):
        race_date = str(
            row.get("date") or ""
        )[:10]

        race_time = str(
            row.get("race_time") or ""
        ).strip()

        try:
            parts = race_time.split(":")

            hour = int(parts[0])
            minute = int(parts[1])

            if 1 <= hour <= 9:
                hour += 12

            sortable_time = f"{hour:02d}:{minute:02d}"

        except Exception:
            sortable_time = "99:99"

        return (
            race_date,
            sortable_time,
            row.get("settled_at") or "",
            row.get("bet_id") or "",
        )

    filtered_bets = filter_performance_bets(
        load_settled_bets(),
        min_score=min_score,
        bet_group=bet_group,
    )

    eligible_bets = [
        bet
        for bet in filtered_bets
        if bet.get("ew_available") is True
        and bet.get("ew_profit") is not None
        and bet.get("ew_total_stake") is not None
        and bet.get("placed") in {True, False}
    ]

    settled = sorted(
        eligible_bets,
        key=history_sort_key,
    )

    for index, bet in enumerate(settled, start=1):
        profit = bet.get("ew_profit")

        if profit is not None:
            bankroll += float(profit)

        race_date = str(
            bet.get("date") or ""
        )[:10]

        race_time = str(
            bet.get("race_time") or ""
        ).strip()

        race_datetime = None

        if race_date and race_time:
            try:
                parts = race_time.split(":")

                hour = int(parts[0])
                minute = int(parts[1])

                if 1 <= hour <= 9:
                    hour += 12

                race_datetime = (
                    f"{race_date}T"
                    f"{hour:02d}:{minute:02d}:00"
                )

            except Exception:
                race_datetime = None

        history.append({
            "x": index,
            "bankroll": round(bankroll, 2),
            "profit": (
                round(float(profit), 2)
                if profit is not None
                else None
            ),
            "horse": bet.get("horse"),
            "course": bet.get("course"),
            "date": race_date,
            "race_time": race_time,
            "race_datetime": race_datetime,
            "settled_at": bet.get("settled_at"),
            "won": bet.get("won"),
            "placed": bet.get("placed"),
            "ew_places_paid": bet.get("ew_places_paid"),
            "ew_fraction": bet.get("ew_fraction"),
            "pulse_score": bet.get("pulse_score"),
            "official_bet": bet.get("official_bet"),
            "bet_type": bet.get("bet_type"),
            "odds_available": (
                bet.get("ew_available") is True
            ),
        })

    return history


def get_performance_insights(
    min_score=None,
    bet_group="all",
):
    settled = filter_performance_bets(
        load_settled_bets(),
        min_score=min_score,
        bet_group=bet_group,
    )
    stats = get_all_settled_stats(
        min_score=min_score,
        bet_group=bet_group,
    )

    if not settled:
        return {
            "health": "WAITING",
            "form": "No settled bets yet.",
            "best_run": 0,
            "worst_run": 0,
            "summary": (
                "Pulse needs settled results before it can "
                "generate intelligence."
            ),
        }

    latest = settled[-8:]

    latest_wins = len([
        bet
        for bet in latest
        if bet.get("won") is True
    ])

    latest_profit = round(
        sum(
            float(bet.get("profit") or 0)
            for bet in latest
            if bet.get("profit") is not None
        ),
        2,
    )

    win_streak = 0
    best_streak = 0
    loss_streak = 0
    worst_streak = 0

    for bet in settled:
        if bet.get("won") is True:
            win_streak += 1
            loss_streak = 0
        else:
            loss_streak += 1
            win_streak = 0

        best_streak = max(best_streak, win_streak)
        worst_streak = max(worst_streak, loss_streak)

    if stats["profit"] > 0 and stats["strike_rate"] >= 50:
        health = "EXCELLENT"
    elif stats["profit"] > 0:
        health = "POSITIVE"
    elif stats["profit"] == 0:
        health = "FLAT"
    else:
        health = "NEGATIVE"

    return {
        "health": health,
        "form": (
            f"{latest_wins} wins from last "
            f"{len(latest)} selections "
            f"({latest_profit:+.2f} pts)"
        ),
        "best_run": best_streak,
        "worst_run": worst_streak,
        "summary": (
            f"Pulse is currently {health.lower()} with "
            f"{stats['profit']:+.2f} pts profit, "
            f"{stats['strike_rate']}% strike rate and "
            f"{stats['roi']}% ROI."
        ),
    }


def load_existing_ledger():
    rows = load_jsonl(LEDGER_FILE)

    return {
        row.get("bet_id"): row
        for row in rows
        if row.get("bet_id")
    }


def load_odds_snapshots():
    rows = []

    if not ODDS_DIR.exists():
        return rows

    for file_path in sorted(ODDS_DIR.glob("*.jsonl")):
        snapshot_date = file_path.stem

        for row in load_jsonl(file_path):
            row["snapshot_date"] = (
                row.get("snapshot_date")
                or snapshot_date
            )

            rows.append(row)

    return rows


def clean_decimal_odds(value):
    """
    Validate captured decimal horse-racing odds.

    Valid decimal odds must be greater than 1.0. The upper guard
    protects the ledger from obviously corrupted provider values
    without rejecting legitimate outsiders.
    """

    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if value <= 1.0:
        return None

    if value > 1000:
        return None

    return round(value, 4)


def rebuild_ledger_from_snapshots():
    ledger_rows = load_jsonl(LEDGER_FILE)
    snapshots = load_odds_snapshots()

    rows_by_id = {
        row.get("bet_id"): row
        for row in ledger_rows
        if row.get("bet_id")
    }

    added = 0
    updated = 0
    skipped = 0

    for row in snapshots:
        bet_id = make_bet_id(row)

        if not bet_id.strip("|"):
            skipped += 1
            continue

        decimal_odds = clean_decimal_odds(
            row.get("best_odds_decimal")
        )

        existing = rows_by_id.get(bet_id)

        # If the pick already exists, attach odds later when
        # a successful price becomes available.
        if existing:
            changed = False

            if (
                existing.get("status") == "OPEN"
                and existing.get("best_odds_decimal") is None
                and decimal_odds is not None
            ):
                existing["odds_source"] = row.get("odds_source")
                existing["odds_url"] = row.get("odds_url")
                existing["snapshot_time"] = row.get("snapshot_time")
                existing["best_odds"] = row.get("best_odds")
                existing["best_odds_decimal"] = decimal_odds
                existing["bookmaker"] = row.get("bookmaker")
                existing["odds_available"] = True

                qualification = qualifies_as_official_bet(row)

                existing["bet_type"] = qualification["bet_type"]
                existing["official_bet"] = qualification["qualifies"]
                existing["qualification_reasons"] = qualification["reasons"]
                existing["qualification_warnings"] = qualification["warnings"]

                changed = True

            if changed:
                updated += 1
            else:
                skipped += 1

            continue

        qualification_row = dict(row)
        qualification_row["best_odds_decimal"] = decimal_odds

        qualification = qualifies_as_official_bet(
            qualification_row
        )

        record = {
            "bet_id": bet_id,
            "status": "OPEN",

            "bet_type": qualification["bet_type"],
            "official_bet": qualification["qualifies"],
            "qualification_reasons": qualification["reasons"],
            "qualification_warnings": qualification["warnings"],

            "created_at": datetime.now().isoformat(
                timespec="seconds"
            ),

            "date": row.get("snapshot_date"),
            "course": row.get("course"),
            "race_time": row.get("race_time"),
            "race_name": row.get("race_name"),
            "race_id": row.get("race_id"),

            "horse": row.get("horse"),
            "horse_id": row.get("horse_id"),

            "strategy": (
                row.get("strategy")
                or "Pulse Top Pick"
            ),

            "pulse_score": row.get("pulse_score"),

            "odds_source": row.get("odds_source"),
            "odds_url": row.get("odds_url"),
            "snapshot_time": row.get("snapshot_time"),
            "best_odds": row.get("best_odds"),
            "best_odds_decimal": decimal_odds,
            "bookmaker": row.get("bookmaker"),
            "odds_available": decimal_odds is not None,

            "result_position": None,
            "sp": None,
            "won": None,

            "stake": 1.0,
            "returned": None,
            "profit": None,
            "roi": None,
        }

        ledger_rows.append(record)
        rows_by_id[bet_id] = record
        added += 1

    # Rewrite once so existing records can receive later odds.
    with LEDGER_FILE.open("w", encoding="utf-8") as f:
        for row in ledger_rows:
            f.write(
                json.dumps(row, ensure_ascii=False)
                + "\n"
            )

    return {
        "snapshots": len(snapshots),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "ledger_file": str(LEDGER_FILE),
    }


if __name__ == "__main__":
    report = rebuild_ledger_from_snapshots()

    print("Bet Ledger Updated")
    print("-" * 40)
    print(f"Snapshots checked: {report['snapshots']}")
    print(f"Added: {report['added']}")
    print(f"Updated with odds: {report['updated']}")
    print(f"Skipped: {report['skipped']}")
    print(f"File: {report['ledger_file']}")
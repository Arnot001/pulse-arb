import json
import re
from pathlib import Path
from typing import Any, Optional


RACECARD_DIR = Path(
    "data/horses/racecards"
)


CONFIRMED_UNPLACED_RESULTS = {
    "unplaced",
    "unpl",
    "pu",
    "pulled up",
    "f",
    "fell",
    "ur",
    "unseated rider",
    "bd",
    "brought down",
    "ro",
    "ran out",
    "ref",
    "refused",
    "rr",
    "refused to race",
    "co",
    "carried out",
    "su",
    "slipped up",
    "dsq",
    "disqualified",
    "disq",
    "last",
}


VOID_OR_UNKNOWN_RESULTS = {
    "",
    "none",
    "unknown",
    "void",
    "abandoned",
    "cancelled",
    "canceled",
    "nr",
    "non runner",
    "non-runner",
    "withdrawn",
}


def normalise(value: Any) -> str:
    value = str(
        value or ""
    ).lower().strip()

    value = value.replace(
        "&",
        "and",
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def parse_int(
    value: Any,
) -> Optional[int]:
    try:
        parsed = int(
            str(value).strip()
        )
    except Exception:
        return None

    return (
        parsed
        if parsed >= 0
        else None
    )


def parse_position(
    value: Any,
) -> Optional[int]:
    if value is None:
        return None

    match = re.match(
        r"^\s*(\d+)",
        str(value),
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def classify_result_position(
    value: Any,
) -> dict:
    """
    Classify a stored result as:

    - numeric: a confirmed finishing position;
    - unplaced: a confirmed losing/non-finishing result;
    - unknown: insufficient information or a void/non-runner result.
    """

    numeric_position = parse_position(
        value
    )

    if numeric_position is not None:
        return {
            "status": "numeric",
            "position": numeric_position,
        }

    normalised = normalise(
        value
    )

    if normalised in CONFIRMED_UNPLACED_RESULTS:
        return {
            "status": "unplaced",
            "position": None,
        }

    if normalised in VOID_OR_UNKNOWN_RESULTS:
        return {
            "status": "unknown",
            "position": None,
        }

    # Handle verbose source descriptions.
    confirmed_phrases = (
        "pulled up",
        "unseated rider",
        "brought down",
        "ran out",
        "refused",
        "carried out",
        "slipped up",
        "disqualified",
        "did not finish",
        "failed to finish",
        "unplaced",
    )

    if any(
        phrase in normalised
        for phrase in confirmed_phrases
    ):
        return {
            "status": "unplaced",
            "position": None,
        }

    return {
        "status": "unknown",
        "position": None,
    }


def parse_time_minutes(
    value: Any,
) -> Optional[int]:
    text = str(
        value or ""
    ).strip()

    if (
        not text
        or ":" not in text
    ):
        return None

    try:
        hour_text, minute_text = (
            text.split(
                ":",
                1,
            )
        )

        hour = int(
            hour_text
        )

        minute = int(
            minute_text[:2]
        )

    except Exception:
        return None

    if not 0 <= minute <= 59:
        return None

    if hour == 0:
        hour = 12

    if 1 <= hour <= 9:
        hour += 12

    return (
        hour * 60
    ) + minute


def times_match(
    left: Any,
    right: Any,
) -> bool:
    left_minutes = (
        parse_time_minutes(
            left
        )
    )

    right_minutes = (
        parse_time_minutes(
            right
        )
    )

    if (
        left_minutes is None
        or right_minutes is None
    ):
        return False

    return abs(
        left_minutes
        - right_minutes
    ) in {
        0,
        60,
    }


def load_jsonl(
    file_path: Path,
) -> list[dict]:
    rows = []

    if not file_path.exists():
        return rows

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file_handle:
        for line in file_handle:
            if not line.strip():
                continue

            try:
                row = json.loads(
                    line
                )
            except Exception:
                continue

            if isinstance(
                row,
                dict,
            ):
                rows.append(
                    row
                )

    return rows


def infer_handicap(
    race: dict,
) -> bool:
    race_name = normalise(
        race.get("race_name")
    )

    rating_band = str(
        race.get("rating_band")
        or ""
    ).strip()

    return (
        "handicap" in race_name
        or bool(rating_band)
    )


def standard_each_way_terms(
    field_size: Optional[int],
    is_handicap: bool,
) -> dict:
    """
    Return conservative standard UK/IRE each-way terms.

    These are estimates based on common standard terms. Individual
    bookmakers may offer enhanced places or different fractions.
    """

    if (
        field_size is None
        or field_size < 5
    ):
        return {
            "available": False,
            "places": None,
            "fraction": None,
            "source": (
                "standard_terms_unavailable"
            ),
        }

    if 5 <= field_size <= 7:
        places = 2
        fraction = 0.25

    elif (
        is_handicap
        and field_size >= 16
    ):
        places = 4
        fraction = 0.25

    elif (
        is_handicap
        and 12 <= field_size <= 15
    ):
        places = 3
        fraction = 0.25

    else:
        places = 3
        fraction = 0.20

    return {
        "available": True,
        "places": places,
        "fraction": fraction,
        "source": (
            "standard_uk_ire_estimate"
        ),
    }


def build_racecard_index() -> dict:
    by_race_id = {}
    rows = []

    if not RACECARD_DIR.exists():
        return {
            "by_race_id": by_race_id,
            "rows": rows,
        }

    for file_path in sorted(
        RACECARD_DIR.glob(
            "*.jsonl"
        )
    ):
        for stored in load_jsonl(
            file_path
        ):
            raw = stored.get(
                "raw"
            )

            if not isinstance(
                raw,
                dict,
            ):
                continue

            race = {
                "race_id": raw.get(
                    "race_id"
                ),
                "date": (
                    raw.get("date")
                    or stored.get(
                        "collection_date"
                    )
                ),
                "course": raw.get(
                    "course"
                ),
                "race_time": raw.get(
                    "off_time"
                ),
                "race_name": raw.get(
                    "race_name"
                ),
                "field_size": (
                    parse_int(
                        raw.get(
                            "field_size"
                        )
                    )
                    or len(
                        raw.get(
                            "runners"
                        )
                        or []
                    )
                    or None
                ),
                "is_handicap": (
                    infer_handicap(
                        raw
                    )
                ),
                "race_class": raw.get(
                    "race_class"
                ),
                "race_type": raw.get(
                    "type"
                ),
                "rating_band": raw.get(
                    "rating_band"
                ),
                "source": stored.get(
                    "source"
                ),
            }

            rows.append(
                race
            )

            race_id = str(
                race.get(
                    "race_id"
                )
                or ""
            ).strip()

            if race_id:
                by_race_id[
                    race_id
                ] = race

    return {
        "by_race_id": by_race_id,
        "rows": rows,
    }


def find_racecard_for_bet(
    bet: dict,
    racecard_index: Optional[
        dict
    ] = None,
) -> Optional[dict]:
    racecard_index = (
        racecard_index
        or build_racecard_index()
    )

    race_id = str(
        bet.get("race_id")
        or ""
    ).strip()

    if race_id:
        exact = racecard_index[
            "by_race_id"
        ].get(
            race_id
        )

        if exact:
            return exact

    target_date = normalise(
        str(
            bet.get("date")
            or ""
        )[:10]
    )

    target_course = normalise(
        bet.get("course")
    )

    target_time = bet.get(
        "race_time"
    )

    matches = []

    for race in racecard_index[
        "rows"
    ]:
        race_date = normalise(
            str(
                race.get("date")
                or ""
            )[:10]
        )

        if race_date != target_date:
            continue

        if normalise(
            race.get("course")
        ) != target_course:
            continue

        if times_match(
            target_time,
            race.get("race_time"),
        ):
            matches.append(
                race
            )

    if len(matches) == 1:
        return matches[0]

    return None


def calculate_each_way_result(
    *,
    decimal_odds: Any,
    result_position: Any,
    field_size: Optional[int],
    is_handicap: bool,
    unit_stake: float = 1.0,
    places: Optional[int] = None,
    fraction: Optional[float] = None,
    terms_source: Optional[str] = None,
) -> dict:
    try:
        decimal_odds = float(
            decimal_odds
        )
    except Exception:
        decimal_odds = None

    try:
        unit_stake = float(
            unit_stake
        )
    except Exception:
        unit_stake = 1.0

    if unit_stake <= 0:
        unit_stake = 1.0

    if (
        places is None
        or fraction is None
    ):
        terms = standard_each_way_terms(
            field_size=field_size,
            is_handicap=is_handicap,
        )

        places = terms[
            "places"
        ]

        fraction = terms[
            "fraction"
        ]

        terms_source = (
            terms_source
            or terms["source"]
        )

        available = terms[
            "available"
        ]

    else:
        available = True

        terms_source = (
            terms_source
            or "captured_terms"
        )

    total_stake = round(
        unit_stake * 2,
        2,
    )

    base = {
        "ew_available": bool(
            available
            and decimal_odds
            is not None
        ),
        "ew_terms_source": (
            terms_source
        ),
        "ew_field_size": field_size,
        "ew_is_handicap": bool(
            is_handicap
        ),
        "ew_places_paid": places,
        "ew_fraction": fraction,
        "ew_win_stake": round(
            unit_stake,
            2,
        ),
        "ew_place_stake": round(
            unit_stake,
            2,
        ),
        "ew_total_stake": (
            total_stake
        ),
        "placed": None,
        "ew_place_decimal": None,
        "ew_win_returned": None,
        "ew_place_returned": None,
        "ew_returned": None,
        "ew_profit": None,
        "ew_roi": None,
    }

    if (
        not available
        or decimal_odds is None
    ):
        return base

    result = classify_result_position(
        result_position
    )

    if result["status"] == "unknown":
        return base

    place_decimal = 1 + (
        (
            decimal_odds - 1
        )
        * float(fraction)
    )

    if result["status"] == "unplaced":
        base.update(
            {
                "placed": False,
                "ew_place_decimal": round(
                    place_decimal,
                    4,
                ),
                "ew_win_returned": 0.0,
                "ew_place_returned": 0.0,
                "ew_returned": 0.0,
                "ew_profit": round(
                    -total_stake,
                    2,
                ),
                "ew_roi": -100.0,
            }
        )

        return base

    numeric_position = result[
        "position"
    ]

    won = (
        numeric_position == 1
    )

    placed = (
        numeric_position
        <= int(places)
    )

    win_returned = (
        unit_stake
        * decimal_odds
        if won
        else 0.0
    )

    place_returned = (
        unit_stake
        * place_decimal
        if placed
        else 0.0
    )

    total_returned = (
        win_returned
        + place_returned
    )

    profit = (
        total_returned
        - total_stake
    )

    roi = (
        (
            profit
            / total_stake
        )
        * 100
        if total_stake
        else 0.0
    )

    base.update(
        {
            "placed": placed,
            "ew_place_decimal": round(
                place_decimal,
                4,
            ),
            "ew_win_returned": round(
                win_returned,
                2,
            ),
            "ew_place_returned": round(
                place_returned,
                2,
            ),
            "ew_returned": round(
                total_returned,
                2,
            ),
            "ew_profit": round(
                profit,
                2,
            ),
            "ew_roi": round(
                roi,
                2,
            ),
        }
    )

    return base


def enrich_bet_with_each_way(
    bet: dict,
    racecard_index: Optional[
        dict
    ] = None,
    unit_stake: float = 1.0,
) -> dict:
    enriched = dict(
        bet
    )

    racecard = find_racecard_for_bet(
        bet,
        racecard_index=(
            racecard_index
        ),
    )

    field_size = (
        racecard.get(
            "field_size"
        )
        if racecard
        else None
    )

    is_handicap = (
        racecard.get(
            "is_handicap"
        )
        if racecard
        else (
            "handicap"
            in normalise(
                bet.get(
                    "race_name"
                )
            )
        )
    )

    ew_result = (
        calculate_each_way_result(
            decimal_odds=bet.get(
                "best_odds_decimal"
            ),
            result_position=bet.get(
                "result_position"
            ),
            field_size=field_size,
            is_handicap=bool(
                is_handicap
            ),
            unit_stake=unit_stake,
        )
    )

    ew_result[
        "ew_racecard_matched"
    ] = bool(
        racecard
    )

    ew_result[
        "ew_racecard_source"
    ] = (
        racecard.get(
            "source"
        )
        if racecard
        else None
    )

    enriched.update(
        ew_result
    )

    return enriched
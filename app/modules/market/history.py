"""
Pulse IQ market history engine.

Builds runner-level market histories from Oddschecker live-market snapshots.

Input:
    data/horses/live_market/*.jsonl

Output:
    data/horses/market_history/*.jsonl

Each output record represents one horse in one race and contains:
- first, latest, highest and lowest available prices
- opening-to-latest movement
- largest single shortening and drifting moves
- price volatility
- snapshot count
- bookmaker history
- full timestamped price history

Run directly with:

    py -m app.modules.market.history
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlparse


LIVE_MARKET_DIR = Path("data/horses/live_market")
MARKET_HISTORY_DIR = Path("data/horses/market_history")

SOURCE_NAME = "pulse_market_history"
HISTORY_VERSION = "market_history_v1"


def clean(value: Any) -> str:
    """Return a safely stripped string."""
    return str(value or "").strip()


def safe_float(value: Any) -> Optional[float]:
    """Convert a value to float, returning None when conversion fails."""
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def parse_datetime(value: Any) -> Optional[datetime]:
    """
    Parse an ISO-8601 datetime and normalise it to UTC.

    Naive datetimes are treated as UTC because Pulse snapshot timestamps are
    generated in UTC.
    """
    text = clean(value)

    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Return a UTC ISO timestamp."""
    return value.astimezone(timezone.utc).isoformat()


def percentage_change(
    old_value: Optional[float],
    new_value: Optional[float],
) -> Optional[float]:
    """Calculate percentage movement from old_value to new_value."""
    if (
        old_value is None
        or new_value is None
        or old_value <= 0
    ):
        return None

    return round(
        ((new_value - old_value) / old_value) * 100,
        4,
    )


def implied_probability(decimal_odds: Optional[float]) -> Optional[float]:
    """Convert decimal odds to implied probability."""
    if decimal_odds is None or decimal_odds <= 1:
        return None

    return round(1 / decimal_odds, 6)


def race_identity_from_url(url: str) -> dict[str, Optional[str]]:
    """
    Extract course and race time from an Oddschecker horse-racing URL.

    Example:
        /horse-racing/curragh/17:00/winner
    """
    parsed = urlparse(clean(url))
    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    course = None
    race_time = None

    try:
        horse_racing_index = parts.index("horse-racing")
    except ValueError:
        horse_racing_index = -1

    if horse_racing_index >= 0:
        if len(parts) > horse_racing_index + 1:
            course = parts[horse_racing_index + 1]

        if len(parts) > horse_racing_index + 2:
            race_time = parts[horse_racing_index + 2]

    course_display = (
        course.replace("-", " ").title()
        if course
        else None
    )

    return {
        "course": course_display,
        "course_slug": course,
        "race_time": race_time,
    }


def normalise_horse_key(value: Any) -> str:
    """Create a stable case-insensitive horse key."""
    return " ".join(
        clean(value).lower().split()
    )


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield valid JSON object records from a JSONL file."""
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file_handle:
            for line_number, line in enumerate(
                file_handle,
                start=1,
            ):
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        "Skipping invalid JSONL line | "
                        f"{path} | line {line_number} | {exc}"
                    )
                    continue

                if isinstance(record, dict):
                    yield record

    except OSError as exc:
        print(
            f"Unable to read market snapshot file {path}: {exc}"
        )


def iter_live_market_snapshots(
    directory: Path = LIVE_MARKET_DIR,
) -> Iterator[dict[str, Any]]:
    """Yield live-market snapshots in chronological file order."""
    if not directory.exists():
        return

    for path in sorted(
        directory.glob("*.jsonl")
    ):
        yield from iter_jsonl_records(path)


def extract_runner_observation(
    snapshot: dict[str, Any],
    runner: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Convert a snapshot runner into one normalised history observation."""
    collected_at = parse_datetime(
        snapshot.get("collected_at")
    )

    horse = clean(
        runner.get("horse")
    )

    decimal_price = safe_float(
        runner.get("best_odds_decimal")
    )

    if (
        collected_at is None
        or not horse
        or decimal_price is None
        or decimal_price <= 1
    ):
        return None

    prices = []

    for price in runner.get(
        "prices",
        [],
    ):
        if not isinstance(price, dict):
            continue

        price_decimal = safe_float(
            price.get("decimal")
        )

        bookmaker = clean(
            price.get("bookmaker")
        )

        if (
            not bookmaker
            or price_decimal is None
            or price_decimal <= 1
        ):
            continue

        prices.append(
            {
                "bookmaker": bookmaker,
                "bookmaker_code": clean(
                    price.get("bookmaker_code")
                ) or None,
                "odds": clean(
                    price.get("odds")
                ) or None,
                "decimal": round(
                    price_decimal,
                    4,
                ),
            }
        )

    prices.sort(
        key=lambda item: (
            -item["decimal"],
            item["bookmaker"].lower(),
        )
    )

    return {
        "collected_at": iso_utc(
            collected_at
        ),
        "collected_at_dt": collected_at,
        "horse": horse,
        "horse_key": normalise_horse_key(
            horse
        ),
        "card_number": clean(
            runner.get("card_number")
        ) or None,
        "draw": clean(
            runner.get("draw")
        ) or None,
        "jockey": clean(
            runner.get("jockey")
        ) or None,
        "market_rank": runner.get(
            "market_rank"
        ),
        "best_odds": clean(
            runner.get("best_odds")
        ) or None,
        "best_odds_decimal": round(
            decimal_price,
            4,
        ),
        "best_bookmaker": clean(
            runner.get("best_bookmaker")
        ) or None,
        "bookmaker_count": int(
            runner.get("bookmaker_count")
            or len(prices)
            or 0
        ),
        "prices": prices,
    }


def collect_runner_observations(
    snapshots: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """
    Group observations by race URL and horse.

    Duplicate observations with the same race, horse and collected_at timestamp
    are ignored.
    """
    grouped: dict[
        tuple[str, str],
        list[dict[str, Any]],
    ] = defaultdict(list)

    seen: set[
        tuple[str, str, str]
    ] = set()

    for snapshot in snapshots:
        url = clean(
            snapshot.get("url")
        )

        if not url:
            continue

        for runner in snapshot.get(
            "runners",
            [],
        ):
            if not isinstance(runner, dict):
                continue

            observation = extract_runner_observation(
                snapshot,
                runner,
            )

            if not observation:
                continue

            dedupe_key = (
                url,
                observation["horse_key"],
                observation["collected_at"],
            )

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)

            grouped[
                (
                    url,
                    observation["horse_key"],
                )
            ].append(
                observation
            )

    for observations in grouped.values():
        observations.sort(
            key=lambda item: item[
                "collected_at_dt"
            ]
        )

    return grouped


def calculate_step_movements(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Calculate movement between consecutive runner observations."""
    movements = []

    for previous, current in zip(
        observations,
        observations[1:],
    ):
        previous_price = safe_float(
            previous.get("best_odds_decimal")
        )

        current_price = safe_float(
            current.get("best_odds_decimal")
        )

        movement_pct = percentage_change(
            previous_price,
            current_price,
        )

        if movement_pct is None:
            continue

        movements.append(
            {
                "from_time": previous[
                    "collected_at"
                ],
                "to_time": current[
                    "collected_at"
                ],
                "from_decimal": previous_price,
                "to_decimal": current_price,
                "movement_pct": movement_pct,
                "direction": (
                    "shortening"
                    if movement_pct < 0
                    else "drifting"
                    if movement_pct > 0
                    else "stable"
                ),
            }
        )

    return movements


def calculate_volatility(
    decimal_prices: list[float],
) -> Optional[float]:
    """
    Calculate population standard deviation of decimal prices.

    A lower value means the runner's best available price was more stable.
    """
    if not decimal_prices:
        return None

    if len(decimal_prices) == 1:
        return 0.0

    return round(
        statistics.pstdev(
            decimal_prices
        ),
        4,
    )


def build_runner_history_record(
    url: str,
    observations: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Build one complete runner-level market history record."""
    if not observations:
        return None

    observations = sorted(
        observations,
        key=lambda item: item[
            "collected_at_dt"
        ],
    )

    first = observations[0]
    latest = observations[-1]

    decimal_prices = [
        safe_float(
            observation.get(
                "best_odds_decimal"
            )
        )
        for observation in observations
    ]

    decimal_prices = [
        value
        for value in decimal_prices
        if value is not None
    ]

    if not decimal_prices:
        return None

    highest_observation = max(
        observations,
        key=lambda item: (
            safe_float(
                item.get(
                    "best_odds_decimal"
                )
            )
            or 0
        ),
    )

    lowest_observation = min(
        observations,
        key=lambda item: (
            safe_float(
                item.get(
                    "best_odds_decimal"
                )
            )
            or float("inf")
        ),
    )

    step_movements = calculate_step_movements(
        observations
    )

    shortening_moves = [
        movement
        for movement in step_movements
        if movement["movement_pct"] < 0
    ]

    drifting_moves = [
        movement
        for movement in step_movements
        if movement["movement_pct"] > 0
    ]

    largest_shortening = (
        min(
            shortening_moves,
            key=lambda item: item[
                "movement_pct"
            ],
        )
        if shortening_moves
        else None
    )

    largest_drift = (
        max(
            drifting_moves,
            key=lambda item: item[
                "movement_pct"
            ],
        )
        if drifting_moves
        else None
    )

    bookmaker_counter = Counter(
        observation.get(
            "best_bookmaker"
        )
        for observation in observations
        if observation.get(
            "best_bookmaker"
        )
    )

    most_frequent_best_bookmaker = (
        bookmaker_counter.most_common(1)[0][0]
        if bookmaker_counter
        else None
    )

    race_identity = race_identity_from_url(
        url
    )

    first_price = safe_float(
        first.get(
            "best_odds_decimal"
        )
    )

    latest_price = safe_float(
        latest.get(
            "best_odds_decimal"
        )
    )

    highest_price = safe_float(
        highest_observation.get(
            "best_odds_decimal"
        )
    )

    lowest_price = safe_float(
        lowest_observation.get(
            "best_odds_decimal"
        )
    )

    first_time = first[
        "collected_at_dt"
    ]

    latest_time = latest[
        "collected_at_dt"
    ]

    history = []

    for observation in observations:
        history.append(
            {
                key: value
                for key, value in observation.items()
                if key != "collected_at_dt"
            }
        )

    return {
        "source": SOURCE_NAME,
        "history_version": HISTORY_VERSION,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "url": url,
        "race_key": (
            f"{race_identity['course_slug']}|"
            f"{race_identity['race_time']}"
            if (
                race_identity["course_slug"]
                and race_identity["race_time"]
            )
            else url
        ),
        "course": race_identity[
            "course"
        ],
        "course_slug": race_identity[
            "course_slug"
        ],
        "race_time": race_identity[
            "race_time"
        ],
        "horse": first[
            "horse"
        ],
        "horse_key": first[
            "horse_key"
        ],
        "card_number": latest.get(
            "card_number"
        ) or first.get(
            "card_number"
        ),
        "draw": latest.get(
            "draw"
        ) or first.get(
            "draw"
        ),
        "jockey": latest.get(
            "jockey"
        ) or first.get(
            "jockey"
        ),
        "snapshot_count": len(
            observations
        ),
        "first_seen_at": first[
            "collected_at"
        ],
        "latest_seen_at": latest[
            "collected_at"
        ],
        "tracking_minutes": round(
            (
                latest_time
                - first_time
            ).total_seconds()
            / 60,
            2,
        ),
        "first_price": first.get(
            "best_odds"
        ),
        "first_price_decimal": first_price,
        "first_bookmaker": first.get(
            "best_bookmaker"
        ),
        "latest_price": latest.get(
            "best_odds"
        ),
        "latest_price_decimal": latest_price,
        "latest_bookmaker": latest.get(
            "best_bookmaker"
        ),
        "highest_price": highest_observation.get(
            "best_odds"
        ),
        "highest_price_decimal": highest_price,
        "highest_price_bookmaker": (
            highest_observation.get(
                "best_bookmaker"
            )
        ),
        "highest_price_seen_at": (
            highest_observation[
                "collected_at"
            ]
        ),
        "lowest_price": lowest_observation.get(
            "best_odds"
        ),
        "lowest_price_decimal": lowest_price,
        "lowest_price_bookmaker": (
            lowest_observation.get(
                "best_bookmaker"
            )
        ),
        "lowest_price_seen_at": (
            lowest_observation[
                "collected_at"
            ]
        ),
        "opening_to_latest_pct": percentage_change(
            first_price,
            latest_price,
        ),
        "highest_to_latest_pct": percentage_change(
            highest_price,
            latest_price,
        ),
        "price_range_decimal": round(
            highest_price - lowest_price,
            4,
        )
        if (
            highest_price is not None
            and lowest_price is not None
        )
        else None,
        "volatility": calculate_volatility(
            decimal_prices
        ),
        "latest_implied_probability": implied_probability(
            latest_price
        ),
        "largest_shortening_pct": (
            largest_shortening[
                "movement_pct"
            ]
            if largest_shortening
            else None
        ),
        "largest_shortening": (
            largest_shortening
        ),
        "largest_drift_pct": (
            largest_drift[
                "movement_pct"
            ]
            if largest_drift
            else None
        ),
        "largest_drift": (
            largest_drift
        ),
        "shortening_move_count": len(
            shortening_moves
        ),
        "drifting_move_count": len(
            drifting_moves
        ),
        "stable_move_count": sum(
            1
            for movement in step_movements
            if movement["direction"] == "stable"
        ),
        "most_frequent_best_bookmaker": (
            most_frequent_best_bookmaker
        ),
        "best_bookmaker_counts": dict(
            bookmaker_counter
        ),
        "history": history,
        "step_movements": step_movements,
    }


def build_market_histories(
    snapshots: Optional[
        Iterable[dict[str, Any]]
    ] = None,
) -> list[dict[str, Any]]:
    """Build all runner histories from supplied or stored snapshots."""
    if snapshots is None:
        snapshots = iter_live_market_snapshots()

    grouped = collect_runner_observations(
        snapshots
    )

    records = []

    for (
        url,
        _horse_key,
    ), observations in grouped.items():
        record = build_runner_history_record(
            url,
            observations,
        )

        if record:
            records.append(
                record
            )

    records.sort(
        key=lambda item: (
            clean(
                item.get("course")
            ).lower(),
            clean(
                item.get("race_time")
            ),
            clean(
                item.get("horse")
            ).lower(),
        )
    )

    return records


def record_week_key(
    record: dict[str, Any],
) -> str:
    """Return the ISO week key used for weekly output files."""
    timestamp = parse_datetime(
        record.get("first_seen_at")
    )

    if timestamp is None:
        timestamp = datetime.now(
            timezone.utc
        )

    iso_year, iso_week, _ = timestamp.isocalendar()

    return f"{iso_year}-W{iso_week:02d}"


def write_jsonl(
    path: Path,
    records: Iterable[dict[str, Any]],
) -> int:
    """Write records to a JSONL file atomically."""
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    count = 0

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file_handle:
        for record in records:
            file_handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            file_handle.write("\n")
            count += 1

    temporary_path.replace(
        path
    )

    return count


def save_market_histories(
    records: Iterable[dict[str, Any]],
    output_directory: Path = MARKET_HISTORY_DIR,
) -> dict[str, int]:
    """
    Save histories into replaceable weekly JSONL files.

    Files are rewritten rather than appended, making repeated rebuilds safe.
    """
    grouped_by_week: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for record in records:
        grouped_by_week[
            record_week_key(
                record
            )
        ].append(
            record
        )

    saved_counts = {}

    for week_key, week_records in sorted(
        grouped_by_week.items()
    ):
        output_path = (
            output_directory
            / f"{week_key}.jsonl"
        )

        saved_counts[
            week_key
        ] = write_jsonl(
            output_path,
            week_records,
        )

    return saved_counts


def get_runner_history(
    horse: str,
    race_url: Optional[str] = None,
    records: Optional[
        Iterable[dict[str, Any]]
    ] = None,
) -> Optional[dict[str, Any]]:
    """Find one runner history by horse name and optionally race URL."""
    target_horse_key = normalise_horse_key(
        horse
    )

    if not target_horse_key:
        return None

    if records is None:
        records = build_market_histories()

    for record in records:
        if (
            record.get("horse_key")
            != target_horse_key
        ):
            continue

        if (
            race_url
            and clean(
                record.get("url")
            )
            != clean(
                race_url
            )
        ):
            continue

        return record

    return None


def rebuild_market_history() -> dict[str, Any]:
    """Rebuild and save the complete market-history dataset."""
    print("=" * 70)
    print("PULSE MARKET HISTORY REBUILD")
    print("=" * 70)
    print(
        f"Reading snapshots from: {LIVE_MARKET_DIR}"
    )

    records = build_market_histories()

    saved_counts = save_market_histories(
        records
    )

    total_saved = sum(
        saved_counts.values()
    )

    print(
        f"Runner histories built: {len(records)}"
    )

    for week_key, count in saved_counts.items():
        print(
            f"{week_key} | Saved: {count}"
        )

    print(
        f"Total runner histories saved: {total_saved}"
    )
    print("=" * 70)

    return {
        "history_version": HISTORY_VERSION,
        "runner_histories": len(
            records
        ),
        "saved": total_saved,
        "weeks": saved_counts,
        "output_directory": str(
            MARKET_HISTORY_DIR
        ),
    }


if __name__ == "__main__":
    rebuild_market_history()

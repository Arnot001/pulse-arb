"""
Pulse IQ race-level market intelligence signals.

Consumes runner-level market-history records produced by:

    app.modules.market.history

and identifies race-level signals such as:

- biggest steamer
- biggest drifter
- most volatile runner
- stable market leader
- strongest late move
- suspicious price spike
- market favourite

The original build_signal() and signal_summary() helpers remain compatible
with existing callers.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


MARKET_HISTORY_DIR = Path(
    "data/horses/market_history"
)

RACE_INTELLIGENCE_DIR = Path(
    "data/horses/race_market_intelligence"
)

SIGNAL_VERSION = "race_market_signals_v2_no_arb"


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_float(value: Any) -> Optional[float]:
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
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def build_signal(
    source,
    signal_type,
    course=None,
    race_time=None,
    horse=None,
    impact=0,
    severity="INFO",
    confidence="MEDIUM",
    reason="",
    **extra,
):
    signal = {
        "source": source,
        "type": signal_type,
        "course": course,
        "race_time": race_time,
        "horse": horse,
        "impact": impact,
        "severity": severity,
        "confidence": confidence,
        "reason": reason,
    }

    signal.update(extra)

    return signal


def signal_summary(signals):
    return {
        "total": len(signals),
        "positive": len(
            [
                signal
                for signal in signals
                if signal.get(
                    "impact",
                    0,
                )
                > 0
            ]
        ),
        "negative": len(
            [
                signal
                for signal in signals
                if signal.get(
                    "impact",
                    0,
                )
                < 0
            ]
        ),
        "neutral": len(
            [
                signal
                for signal in signals
                if signal.get(
                    "impact",
                    0,
                )
                == 0
            ]
        ),
        "warnings": len(
            [
                signal
                for signal in signals
                if signal.get(
                    "severity"
                )
                in (
                    "WARNING",
                    "HIGH",
                    "CRITICAL",
                )
            ]
        ),
    }


def iter_jsonl_records(
    path: Path,
):
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
                    record = json.loads(
                        line
                    )
                except json.JSONDecodeError as exc:
                    print(
                        "Skipping invalid JSONL line | "
                        f"{path} | "
                        f"line {line_number} | "
                        f"{exc}"
                    )
                    continue

                if isinstance(
                    record,
                    dict,
                ):
                    yield record

    except OSError as exc:
        print(
            "Unable to read market-history "
            f"file {path}: {exc}"
        )


def iter_market_histories(
    directory: Path = MARKET_HISTORY_DIR,
):
    if not directory.exists():
        return

    for path in sorted(
        directory.glob(
            "*.jsonl"
        )
    ):
        yield from iter_jsonl_records(
            path
        )


def group_histories_by_race(
    histories: Iterable[
        dict[str, Any]
    ],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    grouped = defaultdict(list)

    for history in histories:
        race_key = clean(
            history.get(
                "race_key"
            )
        )

        if not race_key:
            race_key = clean(
                history.get(
                    "url"
                )
            )

        if not race_key:
            continue

        grouped[
            race_key
        ].append(
            history
        )

    return dict(
        grouped
    )


def movement_confidence(
    snapshot_count: int,
) -> str:
    if snapshot_count >= 8:
        return "HIGH"

    if snapshot_count >= 4:
        return "MEDIUM"

    return "LOW"


def latest_history_point(
    runner: dict[str, Any],
) -> Optional[dict[str, Any]]:
    history = runner.get(
        "history",
        [],
    )

    if not history:
        return None

    return history[-1]


def previous_history_point(
    runner: dict[str, Any],
) -> Optional[dict[str, Any]]:
    history = runner.get(
        "history",
        [],
    )

    if len(history) < 2:
        return None

    return history[-2]


def latest_step_movement(
    runner: dict[str, Any],
) -> Optional[dict[str, Any]]:
    movements = runner.get(
        "step_movements",
        [],
    )

    if not movements:
        return None

    return movements[-1]


def detect_market_favourite(
    runners: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    valid = [
        runner
        for runner in runners
        if (
            safe_float(
                runner.get(
                    "latest_price_decimal"
                )
            )
            is not None
        )
    ]

    if not valid:
        return None

    favourite = min(
        valid,
        key=lambda runner: safe_float(
            runner.get(
                "latest_price_decimal"
            )
        )
        or float("inf"),
    )

    latest_price = safe_float(
        favourite.get(
            "latest_price_decimal"
        )
    )

    return build_signal(
        source="market_history",
        signal_type="market_favourite",
        course=favourite.get(
            "course"
        ),
        race_time=favourite.get(
            "race_time"
        ),
        horse=favourite.get(
            "horse"
        ),
        impact=1,
        severity="INFO",
        confidence=movement_confidence(
            int(
                favourite.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            f"Latest best price "
            f"{favourite.get('latest_price')} "
            f"({latest_price:.2f} decimal)."
            if latest_price is not None
            else "Lowest latest price in the race."
        ),
        latest_price=favourite.get(
            "latest_price"
        ),
        latest_price_decimal=latest_price,
        latest_bookmaker=favourite.get(
            "latest_bookmaker"
        ),
    )


def detect_biggest_steamer(
    runners: list[dict[str, Any]],
    threshold_pct: float = -5.0,
) -> Optional[dict[str, Any]]:
    candidates = []

    for runner in runners:
        movement = safe_float(
            runner.get(
                "opening_to_latest_pct"
            )
        )

        if (
            movement is not None
            and movement < 0
        ):
            candidates.append(
                runner
            )

    if not candidates:
        return None

    steamer = min(
        candidates,
        key=lambda runner: safe_float(
            runner.get(
                "opening_to_latest_pct"
            )
        )
        or 0,
    )

    movement = safe_float(
        steamer.get(
            "opening_to_latest_pct"
        )
    )

    if (
        movement is None
        or movement > threshold_pct
    ):
        return None

    severity = (
        "HIGH"
        if movement <= -20
        else "WARNING"
        if movement <= -10
        else "INFO"
    )

    return build_signal(
        source="market_history",
        signal_type="biggest_steamer",
        course=steamer.get(
            "course"
        ),
        race_time=steamer.get(
            "race_time"
        ),
        horse=steamer.get(
            "horse"
        ),
        impact=2,
        severity=severity,
        confidence=movement_confidence(
            int(
                steamer.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            f"Price shortened from "
            f"{steamer.get('first_price')} to "
            f"{steamer.get('latest_price')} "
            f"({movement:.2f}%)."
        ),
        movement_pct=round(
            movement,
            4,
        ),
        first_price=steamer.get(
            "first_price"
        ),
        latest_price=steamer.get(
            "latest_price"
        ),
        snapshot_count=steamer.get(
            "snapshot_count"
        ),
    )


def detect_biggest_drifter(
    runners: list[dict[str, Any]],
    threshold_pct: float = 5.0,
) -> Optional[dict[str, Any]]:
    candidates = []

    for runner in runners:
        movement = safe_float(
            runner.get(
                "opening_to_latest_pct"
            )
        )

        if (
            movement is not None
            and movement > 0
        ):
            candidates.append(
                runner
            )

    if not candidates:
        return None

    drifter = max(
        candidates,
        key=lambda runner: safe_float(
            runner.get(
                "opening_to_latest_pct"
            )
        )
        or 0,
    )

    movement = safe_float(
        drifter.get(
            "opening_to_latest_pct"
        )
    )

    if (
        movement is None
        or movement < threshold_pct
    ):
        return None

    severity = (
        "HIGH"
        if movement >= 25
        else "WARNING"
        if movement >= 12
        else "INFO"
    )

    return build_signal(
        source="market_history",
        signal_type="biggest_drifter",
        course=drifter.get(
            "course"
        ),
        race_time=drifter.get(
            "race_time"
        ),
        horse=drifter.get(
            "horse"
        ),
        impact=-2,
        severity=severity,
        confidence=movement_confidence(
            int(
                drifter.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            f"Price drifted from "
            f"{drifter.get('first_price')} to "
            f"{drifter.get('latest_price')} "
            f"(+{movement:.2f}%)."
        ),
        movement_pct=round(
            movement,
            4,
        ),
        first_price=drifter.get(
            "first_price"
        ),
        latest_price=drifter.get(
            "latest_price"
        ),
        snapshot_count=drifter.get(
            "snapshot_count"
        ),
    )


def detect_most_volatile(
    runners: list[dict[str, Any]],
    minimum_volatility: float = 0.25,
) -> Optional[dict[str, Any]]:
    candidates = [
        runner
        for runner in runners
        if safe_float(
            runner.get(
                "volatility"
            )
        )
        is not None
    ]

    if not candidates:
        return None

    volatile = max(
        candidates,
        key=lambda runner: safe_float(
            runner.get(
                "volatility"
            )
        )
        or 0,
    )

    volatility = safe_float(
        volatile.get(
            "volatility"
        )
    )

    if (
        volatility is None
        or volatility
        < minimum_volatility
    ):
        return None

    severity = (
        "HIGH"
        if volatility >= 1.5
        else "WARNING"
        if volatility >= 0.75
        else "INFO"
    )

    return build_signal(
        source="market_history",
        signal_type="most_volatile_runner",
        course=volatile.get(
            "course"
        ),
        race_time=volatile.get(
            "race_time"
        ),
        horse=volatile.get(
            "horse"
        ),
        impact=-1,
        severity=severity,
        confidence=movement_confidence(
            int(
                volatile.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            "Highest price volatility in "
            f"the race: {volatility:.4f}."
        ),
        volatility=round(
            volatility,
            4,
        ),
        highest_price=volatile.get(
            "highest_price"
        ),
        lowest_price=volatile.get(
            "lowest_price"
        ),
        snapshot_count=volatile.get(
            "snapshot_count"
        ),
    )


def detect_strongest_late_move(
    runners: list[dict[str, Any]],
    threshold_pct: float = 4.0,
) -> Optional[dict[str, Any]]:
    candidates = []

    for runner in runners:
        movement = latest_step_movement(
            runner
        )

        if not movement:
            continue

        movement_pct = safe_float(
            movement.get(
                "movement_pct"
            )
        )

        if movement_pct is None:
            continue

        candidates.append(
            (
                abs(
                    movement_pct
                ),
                runner,
                movement,
            )
        )

    if not candidates:
        return None

    magnitude, runner, movement = max(
        candidates,
        key=lambda item: item[0],
    )

    if magnitude < threshold_pct:
        return None

    movement_pct = safe_float(
        movement.get(
            "movement_pct"
        )
    )

    direction = movement.get(
        "direction"
    )

    positive = direction == "shortening"

    return build_signal(
        source="market_history",
        signal_type="strongest_late_move",
        course=runner.get(
            "course"
        ),
        race_time=runner.get(
            "race_time"
        ),
        horse=runner.get(
            "horse"
        ),
        impact=2 if positive else -2,
        severity=(
            "HIGH"
            if magnitude >= 20
            else "WARNING"
            if magnitude >= 10
            else "INFO"
        ),
        confidence=movement_confidence(
            int(
                runner.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            f"Latest observed move was "
            f"{direction}: "
            f"{movement.get('from_decimal')} -> "
            f"{movement.get('to_decimal')} "
            f"({movement_pct:.2f}%)."
        ),
        direction=direction,
        movement_pct=movement_pct,
        from_time=movement.get(
            "from_time"
        ),
        to_time=movement.get(
            "to_time"
        ),
        from_decimal=movement.get(
            "from_decimal"
        ),
        to_decimal=movement.get(
            "to_decimal"
        ),
    )


def detect_stable_market_leader(
    runners: list[dict[str, Any]],
    max_volatility: float = 0.15,
    max_absolute_movement_pct: float = 5.0,
) -> Optional[dict[str, Any]]:
    favourite_signal = detect_market_favourite(
        runners
    )

    if not favourite_signal:
        return None

    favourite_horse = favourite_signal.get(
        "horse"
    )

    favourite = next(
        (
            runner
            for runner in runners
            if runner.get(
                "horse"
            )
            == favourite_horse
        ),
        None,
    )

    if not favourite:
        return None

    volatility = safe_float(
        favourite.get(
            "volatility"
        )
    )

    movement = safe_float(
        favourite.get(
            "opening_to_latest_pct"
        )
    )

    snapshot_count = int(
        favourite.get(
            "snapshot_count"
        )
        or 0
    )

    if (
        volatility is None
        or volatility
        > max_volatility
        or movement is None
        or abs(
            movement
        )
        > max_absolute_movement_pct
        or snapshot_count < 3
    ):
        return None

    return build_signal(
        source="market_history",
        signal_type="stable_market_leader",
        course=favourite.get(
            "course"
        ),
        race_time=favourite.get(
            "race_time"
        ),
        horse=favourite.get(
            "horse"
        ),
        impact=1,
        severity="INFO",
        confidence=movement_confidence(
            snapshot_count
        ),
        reason=(
            "Current favourite remained stable "
            f"across {snapshot_count} snapshots "
            f"(volatility {volatility:.4f}, "
            f"movement {movement:.2f}%)."
        ),
        volatility=volatility,
        movement_pct=movement,
        snapshot_count=snapshot_count,
        latest_price=favourite.get(
            "latest_price"
        ),
    )


def detect_suspicious_price_spike(
    runners: list[dict[str, Any]],
    threshold_pct: float = 30.0,
) -> Optional[dict[str, Any]]:
    candidates = []

    for runner in runners:
        for movement in runner.get(
            "step_movements",
            [],
        ):
            movement_pct = safe_float(
                movement.get(
                    "movement_pct"
                )
            )

            if movement_pct is None:
                continue

            candidates.append(
                (
                    abs(
                        movement_pct
                    ),
                    runner,
                    movement,
                )
            )

    if not candidates:
        return None

    magnitude, runner, movement = max(
        candidates,
        key=lambda item: item[0],
    )

    if magnitude < threshold_pct:
        return None

    movement_pct = safe_float(
        movement.get(
            "movement_pct"
        )
    )

    return build_signal(
        source="market_history",
        signal_type="suspicious_price_spike",
        course=runner.get(
            "course"
        ),
        race_time=runner.get(
            "race_time"
        ),
        horse=runner.get(
            "horse"
        ),
        impact=-3,
        severity="HIGH",
        confidence=movement_confidence(
            int(
                runner.get(
                    "snapshot_count"
                )
                or 0
            )
        ),
        reason=(
            "Single-step price movement exceeded "
            f"{threshold_pct:.0f}%: "
            f"{movement.get('from_decimal')} -> "
            f"{movement.get('to_decimal')} "
            f"({movement_pct:.2f}%)."
        ),
        direction=movement.get(
            "direction"
        ),
        movement_pct=movement_pct,
        from_time=movement.get(
            "from_time"
        ),
        to_time=movement.get(
            "to_time"
        ),
    )



def build_race_signals(
    runners: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    detectors = (
        detect_market_favourite,
        detect_biggest_steamer,
        detect_biggest_drifter,
        detect_most_volatile,
        detect_strongest_late_move,
        detect_stable_market_leader,
        detect_suspicious_price_spike,
    )

    signals = []

    for detector in detectors:
        try:
            signal = detector(
                runners
            )
        except Exception as exc:
            print(
                "Race signal detector failed | "
                f"{detector.__name__} | {exc}"
            )
            continue

        if signal:
            signals.append(
                signal
            )

    return signals


def build_race_intelligence_record(
    race_key: str,
    runners: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if not runners:
        return None

    first_runner = runners[0]

    signals = build_race_signals(
        runners
    )

    latest_seen_values = [
        parse_datetime(
            runner.get(
                "latest_seen_at"
            )
        )
        for runner in runners
    ]

    latest_seen_values = [
        value
        for value in latest_seen_values
        if value is not None
    ]

    latest_seen_at = (
        max(
            latest_seen_values
        ).isoformat()
        if latest_seen_values
        else None
    )

    return {
        "source": "market_history",
        "signal_version": SIGNAL_VERSION,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "race_key": race_key,
        "url": first_runner.get(
            "url"
        ),
        "course": first_runner.get(
            "course"
        ),
        "course_slug": first_runner.get(
            "course_slug"
        ),
        "race_time": first_runner.get(
            "race_time"
        ),
        "latest_seen_at": latest_seen_at,
        "runner_count": len(
            runners
        ),
        "signals": signals,
        "summary": signal_summary(
            signals
        ),
    }


def build_all_race_intelligence(
    histories: Optional[
        Iterable[dict[str, Any]]
    ] = None,
) -> list[dict[str, Any]]:
    if histories is None:
        histories = iter_market_histories()

    grouped = group_histories_by_race(
        histories
    )

    records = []

    for race_key, runners in grouped.items():
        record = build_race_intelligence_record(
            race_key,
            runners,
        )

        if record:
            records.append(
                record
            )

    records.sort(
        key=lambda record: (
            clean(
                record.get(
                    "course"
                )
            ).lower(),
            clean(
                record.get(
                    "race_time"
                )
            ),
        )
    )

    return records


def record_week_key(
    record: dict[str, Any],
) -> str:
    timestamp = parse_datetime(
        record.get(
            "latest_seen_at"
        )
    )

    if timestamp is None:
        timestamp = datetime.now(
            timezone.utc
        )

    iso_year, iso_week, _ = (
        timestamp.isocalendar()
    )

    return (
        f"{iso_year}-W{iso_week:02d}"
    )


def write_jsonl(
    path: Path,
    records: Iterable[
        dict[str, Any]
    ],
) -> int:
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
                    separators=(
                        ",",
                        ":",
                    ),
                )
            )

            file_handle.write(
                "\n"
            )

            count += 1

    temporary_path.replace(
        path
    )

    return count


def save_race_intelligence(
    records: Iterable[
        dict[str, Any]
    ],
    output_directory: Path = (
        RACE_INTELLIGENCE_DIR
    ),
) -> dict[str, int]:
    grouped_by_week = defaultdict(
        list
    )

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


def rebuild_race_market_intelligence():
    print("=" * 70)
    print(
        "PULSE RACE MARKET INTELLIGENCE REBUILD"
    )
    print("=" * 70)
    print(
        "Reading runner histories from: "
        f"{MARKET_HISTORY_DIR}"
    )

    records = (
        build_all_race_intelligence()
    )

    saved_counts = (
        save_race_intelligence(
            records
        )
    )

    total_signals = sum(
        record.get(
            "summary",
            {},
        ).get(
            "total",
            0,
        )
        for record in records
    )

    total_saved = sum(
        saved_counts.values()
    )

    print(
        f"Race intelligence records built: "
        f"{len(records)}"
    )

    print(
        f"Signals generated: {total_signals}"
    )

    for week_key, count in saved_counts.items():
        print(
            f"{week_key} | Saved: {count}"
        )

    print(
        "Total race intelligence records "
        f"saved: {total_saved}"
    )
    print("=" * 70)

    return {
        "signal_version": SIGNAL_VERSION,
        "race_records": len(
            records
        ),
        "signals": total_signals,
        "saved": total_saved,
        "weeks": saved_counts,
        "output_directory": str(
            RACE_INTELLIGENCE_DIR
        ),
    }


if __name__ == "__main__":
    rebuild_race_market_intelligence()
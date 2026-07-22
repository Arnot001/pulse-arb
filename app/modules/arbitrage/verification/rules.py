from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from app.modules.arbitrage.calculator import valid_decimal
from app.modules.arbitrage.verification.models import (
    VerificationCheck,
)


# ---------------------------------------------------------
# Defaults
# ---------------------------------------------------------

DEFAULT_MAX_SNAPSHOT_AGE_SECONDS = 30.0
DEFAULT_MINIMUM_SEEN_COUNT = 3
DEFAULT_STRONG_SEEN_COUNT = 8
DEFAULT_MINIMUM_STABLE_SECONDS = 10.0
DEFAULT_STRONG_STABLE_SECONDS = 30.0

MINIMUM_REALISTIC_MARKET_PERCENTAGE = 50.0
MAXIMUM_REALISTIC_MARKET_PERCENTAGE = 115.0


# ---------------------------------------------------------
# Generic Helpers
# ---------------------------------------------------------

def _first_present(
    record: Mapping[str, Any],
    names: Sequence[str],
    default: Any = None,
) -> Any:
    for name in names:
        value = record.get(name)

        if value is not None:
            return value

    return default


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if not isfinite(result):
        return default

    return result


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_text(
    value: Any,
) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .casefold()
        .split()
    )


def _parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(
                float(value),
                tz=timezone.utc,
            )
        except (
            OverflowError,
            OSError,
            TypeError,
            ValueError,
        ):
            return None

    elif isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return None

        if cleaned.endswith("Z"):
            cleaned = (
                cleaned[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                cleaned
            )
        except ValueError:
            return None

    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _normalise_legs(
    legs: Iterable[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    if legs is None:
        return []

    return [
        leg
        for leg in legs
        if isinstance(leg, Mapping)
    ]


def _leg_selection(
    leg: Mapping[str, Any],
) -> str:
    return str(
        _first_present(
            leg,
            (
                "selection",
                "horse",
                "runner",
                "name",
            ),
            "",
        )
    ).strip()


def _leg_bookmaker(
    leg: Mapping[str, Any],
) -> str:
    return str(
        _first_present(
            leg,
            (
                "bookmaker",
                "source",
                "sportsbook",
                "book",
            ),
            "",
        )
    ).strip()


def _leg_odds(
    leg: Mapping[str, Any],
) -> float:
    return _safe_float(
        _first_present(
            leg,
            (
                "odds",
                "decimal",
                "decimal_odds",
                "price",
            ),
        ),
        default=0.0,
    )


def _check(
    name: str,
    passed: bool,
    score: int,
    max_score: int,
    message: str,
) -> VerificationCheck:
    bounded_score = max(
        0,
        min(
            int(score),
            int(max_score),
        ),
    )

    return VerificationCheck(
        name=name,
        passed=passed,
        score=bounded_score,
        max_score=max_score,
        message=message,
    )


# ---------------------------------------------------------
# Market Completeness
# ---------------------------------------------------------

def check_market_complete(
    legs: Iterable[Mapping[str, Any]] | None,
    expected_runner_count: int | None = None,
    max_score: int = 20,
) -> VerificationCheck:
    normalised = _normalise_legs(
        legs
    )

    leg_count = len(normalised)

    if leg_count < 2:
        return _check(
            name="Market completeness",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Fewer than two priced runners "
                "were supplied."
            ),
        )

    valid_legs = 0

    for leg in normalised:
        selection = _leg_selection(
            leg
        )
        bookmaker = _leg_bookmaker(
            leg
        )
        odds = _leg_odds(
            leg
        )

        if (
            selection
            and bookmaker
            and valid_decimal(odds)
        ):
            valid_legs += 1

    if valid_legs != leg_count:
        return _check(
            name="Market completeness",
            passed=False,
            score=round(
                max_score
                * (
                    valid_legs
                    / max(
                        leg_count,
                        1,
                    )
                )
            ),
            max_score=max_score,
            message=(
                f"{valid_legs} of {leg_count} legs "
                "contain a selection, bookmaker "
                "and valid price."
            ),
        )

    if (
        expected_runner_count is not None
        and expected_runner_count > 0
        and leg_count < expected_runner_count
    ):
        coverage = (
            leg_count
            / expected_runner_count
        )

        return _check(
            name="Market completeness",
            passed=False,
            score=round(
                max_score
                * min(
                    coverage,
                    1.0,
                )
            ),
            max_score=max_score,
            message=(
                f"Only {leg_count} of "
                f"{expected_runner_count} expected "
                "runners are represented."
            ),
        )

    return _check(
        name="Market completeness",
        passed=True,
        score=max_score,
        max_score=max_score,
        message=(
            f"All {leg_count} supplied legs "
            "contain complete price data."
        ),
    )


# ---------------------------------------------------------
# Market Percentage
# ---------------------------------------------------------

def check_market_percentage(
    market_percentage: float,
    max_score: int = 15,
) -> VerificationCheck:
    percentage = _safe_float(
        market_percentage,
        default=-1.0,
    )

    if percentage <= 0:
        return _check(
            name="Market integrity",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Market percentage is missing "
                "or invalid."
            ),
        )

    if (
        percentage
        < MINIMUM_REALISTIC_MARKET_PERCENTAGE
    ):
        return _check(
            name="Market integrity",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                f"Market percentage {percentage:.3f}% "
                "is unrealistically low."
            ),
        )

    if (
        percentage
        > MAXIMUM_REALISTIC_MARKET_PERCENTAGE
    ):
        return _check(
            name="Market integrity",
            passed=False,
            score=2,
            max_score=max_score,
            message=(
                f"Market percentage {percentage:.3f}% "
                "is outside the accepted range."
            ),
        )

    if percentage >= 100.0:
        return _check(
            name="Market integrity",
            passed=False,
            score=round(
                max_score * 0.35
            ),
            max_score=max_score,
            message=(
                f"Market percentage {percentage:.3f}% "
                "does not currently represent "
                "an arbitrage."
            ),
        )

    if percentage >= 98.0:
        score = round(
            max_score * 0.85
        )

    elif percentage >= 90.0:
        score = max_score

    else:
        score = round(
            max_score * 0.80
        )

    return _check(
        name="Market integrity",
        passed=True,
        score=score,
        max_score=max_score,
        message=(
            f"Market percentage {percentage:.3f}% "
            "is plausible and below 100%."
        ),
    )


# ---------------------------------------------------------
# Price Validity
# ---------------------------------------------------------

def check_price_validity(
    legs: Iterable[Mapping[str, Any]] | None,
    max_score: int = 10,
) -> VerificationCheck:
    normalised = _normalise_legs(
        legs
    )

    if not normalised:
        return _check(
            name="Price validity",
            passed=False,
            score=0,
            max_score=max_score,
            message="No prices were supplied.",
        )

    invalid: list[str] = []

    for index, leg in enumerate(
        normalised,
        start=1,
    ):
        selection = (
            _leg_selection(leg)
            or f"Leg {index}"
        )

        odds = _leg_odds(
            leg
        )

        if not valid_decimal(odds):
            invalid.append(
                selection
            )

    if invalid:
        return _check(
            name="Price validity",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Invalid prices found for: "
                + ", ".join(invalid)
            ),
        )

    return _check(
        name="Price validity",
        passed=True,
        score=max_score,
        max_score=max_score,
        message=(
            f"All {len(normalised)} prices "
            "are valid decimal odds."
        ),
    )


# ---------------------------------------------------------
# Duplicate Detection
# ---------------------------------------------------------

def check_duplicate_runners(
    legs: Iterable[Mapping[str, Any]] | None,
    max_score: int = 10,
) -> VerificationCheck:
    normalised = _normalise_legs(
        legs
    )

    seen: set[str] = set()
    duplicates: set[str] = set()

    for leg in normalised:
        selection = _normalise_text(
            _leg_selection(leg)
        )

        if not selection:
            continue

        if selection in seen:
            duplicates.add(
                selection
            )

        seen.add(
            selection
        )

    if duplicates:
        return _check(
            name="Duplicate runners",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Duplicate runner records detected: "
                + ", ".join(
                    sorted(duplicates)
                )
            ),
        )

    return _check(
        name="Duplicate runners",
        passed=True,
        score=max_score,
        max_score=max_score,
        message=(
            "No duplicate runner records detected."
        ),
    )


def check_duplicate_bookmakers(
    legs: Iterable[Mapping[str, Any]] | None,
    max_score: int = 5,
) -> VerificationCheck:
    """
    A bookmaker should normally appear only once in a
    complete back/back arb, because one bookmaker cannot
    provide the best price for multiple mutually exclusive
    runners without increasing execution concentration.

    Duplicate bookmakers are treated as a warning rather
    than an automatic rejection.
    """

    normalised = _normalise_legs(
        legs
    )

    counts: dict[str, int] = {}

    for leg in normalised:
        bookmaker = _normalise_text(
            _leg_bookmaker(leg)
        )

        if not bookmaker:
            continue

        counts[bookmaker] = (
            counts.get(bookmaker, 0)
            + 1
        )

    duplicates = sorted(
        bookmaker
        for bookmaker, count in counts.items()
        if count > 1
    )

    if duplicates:
        return _check(
            name="Bookmaker concentration",
            passed=False,
            score=round(
                max_score * 0.40
            ),
            max_score=max_score,
            message=(
                "More than one leg uses the same "
                "bookmaker: "
                + ", ".join(duplicates)
            ),
        )

    return _check(
        name="Bookmaker concentration",
        passed=True,
        score=max_score,
        max_score=max_score,
        message=(
            "Every leg uses a distinct bookmaker."
        ),
    )


# ---------------------------------------------------------
# Observation Count
# ---------------------------------------------------------

def check_seen_count(
    seen_count: int,
    minimum_seen_count: int = (
        DEFAULT_MINIMUM_SEEN_COUNT
    ),
    strong_seen_count: int = (
        DEFAULT_STRONG_SEEN_COUNT
    ),
    max_score: int = 15,
) -> VerificationCheck:
    count = max(
        0,
        _safe_int(seen_count),
    )

    minimum = max(
        1,
        int(minimum_seen_count),
    )

    strong = max(
        minimum,
        int(strong_seen_count),
    )

    if count <= 0:
        return _check(
            name="Price consistency",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Opportunity has not been observed "
                "in a completed scan."
            ),
        )

    if count < minimum:
        score = round(
            max_score
            * (
                count
                / minimum
            )
            * 0.50
        )

        return _check(
            name="Price consistency",
            passed=False,
            score=score,
            max_score=max_score,
            message=(
                f"Observed {count} time(s); "
                f"at least {minimum} are required."
            ),
        )

    if count >= strong:
        return _check(
            name="Price consistency",
            passed=True,
            score=max_score,
            max_score=max_score,
            message=(
                f"Observed consistently across "
                f"{count} scans."
            ),
        )

    progress = (
        count - minimum
    ) / max(
        strong - minimum,
        1,
    )

    score = round(
        (
            max_score * 0.70
        )
        + (
            max_score
            * 0.30
            * progress
        )
    )

    return _check(
        name="Price consistency",
        passed=True,
        score=score,
        max_score=max_score,
        message=(
            f"Observed across {count} scans."
        ),
    )


# ---------------------------------------------------------
# Stable Window
# ---------------------------------------------------------

def check_stable_window(
    stable_seconds: float,
    minimum_stable_seconds: float = (
        DEFAULT_MINIMUM_STABLE_SECONDS
    ),
    strong_stable_seconds: float = (
        DEFAULT_STRONG_STABLE_SECONDS
    ),
    max_score: int = 15,
) -> VerificationCheck:
    seconds = max(
        0.0,
        _safe_float(stable_seconds),
    )

    minimum = max(
        0.0,
        float(minimum_stable_seconds),
    )

    strong = max(
        minimum,
        float(strong_stable_seconds),
    )

    if seconds < minimum:
        fraction = (
            seconds / minimum
            if minimum > 0
            else 0.0
        )

        return _check(
            name="Stable window",
            passed=False,
            score=round(
                max_score
                * fraction
                * 0.50
            ),
            max_score=max_score,
            message=(
                f"Stable for {seconds:.1f}s; "
                f"minimum is {minimum:.1f}s."
            ),
        )

    if seconds >= strong:
        return _check(
            name="Stable window",
            passed=True,
            score=max_score,
            max_score=max_score,
            message=(
                f"Opportunity remained stable "
                f"for {seconds:.1f}s."
            ),
        )

    progress = (
        seconds - minimum
    ) / max(
        strong - minimum,
        0.001,
    )

    score = round(
        (
            max_score * 0.70
        )
        + (
            max_score
            * 0.30
            * progress
        )
    )

    return _check(
        name="Stable window",
        passed=True,
        score=score,
        max_score=max_score,
        message=(
            f"Opportunity remained stable "
            f"for {seconds:.1f}s."
        ),
    )


# ---------------------------------------------------------
# Snapshot Freshness
# ---------------------------------------------------------

def check_snapshot_age(
    snapshot_time: Any,
    now: datetime | None = None,
    maximum_age_seconds: float = (
        DEFAULT_MAX_SNAPSHOT_AGE_SECONDS
    ),
    max_score: int = 10,
) -> VerificationCheck:
    parsed = _parse_datetime(
        snapshot_time
    )

    if parsed is None:
        return _check(
            name="Snapshot freshness",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Snapshot timestamp is missing "
                "or invalid."
            ),
        )

    current = now or datetime.now(
        timezone.utc
    )

    if current.tzinfo is None:
        current = current.replace(
            tzinfo=timezone.utc
        )

    current = current.astimezone(
        timezone.utc
    )

    age_seconds = (
        current - parsed
    ).total_seconds()

    if age_seconds < -5:
        return _check(
            name="Snapshot freshness",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                "Snapshot timestamp is in the future."
            ),
        )

    age_seconds = max(
        0.0,
        age_seconds,
    )

    maximum = max(
        1.0,
        float(maximum_age_seconds),
    )

    if age_seconds > maximum:
        return _check(
            name="Snapshot freshness",
            passed=False,
            score=0,
            max_score=max_score,
            message=(
                f"Snapshot is {age_seconds:.1f}s old; "
                f"maximum accepted age is "
                f"{maximum:.1f}s."
            ),
        )

    freshness = 1.0 - (
        age_seconds / maximum
    )

    score = max(
        1,
        round(
            max_score
            * (
                0.70
                + (0.30 * freshness)
            )
        ),
    )

    return _check(
        name="Snapshot freshness",
        passed=True,
        score=score,
        max_score=max_score,
        message=(
            f"Snapshot is {age_seconds:.1f}s old."
        ),
    )


# ---------------------------------------------------------
# Collector / Bookmaker Health
# ---------------------------------------------------------

def check_collector_health(
    collector_healthy: bool = True,
    security_verification_detected: bool = False,
    stale_page_detected: bool = False,
    max_score: int = 10,
) -> VerificationCheck:
    problems: list[str] = []

    if not collector_healthy:
        problems.append(
            "collector reported unhealthy"
        )

    if security_verification_detected:
        problems.append(
            "security verification detected"
        )

    if stale_page_detected:
        problems.append(
            "stale page detected"
        )

    if problems:
        score = max(
            0,
            max_score
            - (
                len(problems) * 4
            ),
        )

        return _check(
            name="Collector health",
            passed=False,
            score=score,
            max_score=max_score,
            message=(
                "Collector issues: "
                + "; ".join(problems)
                + "."
            ),
        )

    return _check(
        name="Collector health",
        passed=True,
        score=max_score,
        max_score=max_score,
        message=(
            "Collector reported healthy with "
            "no security or stale-page warnings."
        ),
    )
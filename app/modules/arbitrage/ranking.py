from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.modules.arbitrage.models import (
    ArbOpportunity,
    StabilityStatus,
    ValidationStatus,
)


DEFAULT_MAX_PRICE_AGE_SECONDS = 300
DEFAULT_TARGET_STABLE_SECONDS = 120


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_datetime(
    value: Optional[str],
) -> Optional[datetime]:
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def unique_bookmaker_count(
    opportunity: ArbOpportunity,
) -> int:
    return len(
        {
            leg.source.strip().lower()
            for leg in opportunity.legs
            if leg.source
        }
    )


def newest_leg_timestamp(
    opportunity: ArbOpportunity,
) -> Optional[datetime]:
    timestamps = []

    for leg in opportunity.legs:
        metadata = (
            leg.metadata
            if isinstance(
                leg.metadata,
                dict,
            )
            else {}
        )

        for key in (
            "captured_at",
            "price_captured_at",
            "snapshot_at",
        ):
            parsed = parse_iso_datetime(
                metadata.get(key)
            )

            if parsed is not None:
                timestamps.append(
                    parsed
                )
                break

    if timestamps:
        return max(
            timestamps
        )

    for fallback in (
        opportunity.last_seen_at,
        opportunity.detected_at,
        opportunity.first_seen_at,
    ):
        parsed = parse_iso_datetime(
            fallback
        )

        if parsed is not None:
            return parsed

    return None


def price_age_seconds(
    opportunity: ArbOpportunity,
    *,
    now: Optional[datetime] = None,
) -> Optional[int]:
    newest = newest_leg_timestamp(
        opportunity
    )

    if newest is None:
        return None

    current = now or utc_now()

    if current.tzinfo is None:
        current = current.replace(
            tzinfo=timezone.utc
        )

    age = (
        current.astimezone(timezone.utc)
        - newest
    ).total_seconds()

    return max(
        0,
        int(age),
    )


def roi_score(
    opportunity: ArbOpportunity,
) -> float:
    roi = max(
        0.0,
        opportunity.roi_percent,
    )

    return clamp(
        roi * 12.5,
    )


def profit_score(
    opportunity: ArbOpportunity,
) -> float:
    profit = max(
        0.0,
        opportunity.guaranteed_profit,
    )

    stake = max(
        opportunity.total_stake,
        1.0,
    )

    relative_profit = (
        profit / stake
    ) * 100.0

    absolute_component = min(
        profit / 10.0,
        1.0,
    ) * 20.0

    relative_component = min(
        relative_profit / 8.0,
        1.0,
    ) * 80.0

    return clamp(
        absolute_component
        + relative_component
    )


def bookmaker_score(
    opportunity: ArbOpportunity,
) -> float:
    count = unique_bookmaker_count(
        opportunity
    )

    if count <= 1:
        return 20.0

    if count == 2:
        return 55.0

    if count == 3:
        return 75.0

    if count == 4:
        return 90.0

    return 100.0


def stability_score(
    opportunity: ArbOpportunity,
    *,
    target_stable_seconds: int = (
        DEFAULT_TARGET_STABLE_SECONDS
    ),
) -> float:
    status = (
        opportunity.stability_status
    )

    if status == StabilityStatus.EXPIRED:
        return 0.0

    if status == StabilityStatus.VOLATILE:
        return 20.0

    if status == StabilityStatus.UNKNOWN:
        base = 35.0
    elif status == StabilityStatus.NEW:
        base = 45.0
    elif status == StabilityStatus.STABLE:
        base = 75.0
    else:
        base = 35.0

    stable_seconds = max(
        0,
        opportunity.stable_seconds,
    )

    if target_stable_seconds <= 0:
        duration_component = 25.0
    else:
        duration_component = min(
            stable_seconds
            / target_stable_seconds,
            1.0,
        ) * 25.0

    seen_component = min(
        max(
            opportunity.seen_count,
            0,
        )
        / 5.0,
        1.0,
    ) * 10.0

    return clamp(
        base
        + duration_component
        + seen_component
    )


def freshness_score(
    opportunity: ArbOpportunity,
    *,
    now: Optional[datetime] = None,
    max_price_age_seconds: int = (
        DEFAULT_MAX_PRICE_AGE_SECONDS
    ),
) -> float:
    age = price_age_seconds(
        opportunity,
        now=now,
    )

    if age is None:
        return 35.0

    if max_price_age_seconds <= 0:
        return 0.0

    ratio = (
        age / max_price_age_seconds
    )

    return clamp(
        100.0 * (
            1.0 - ratio
        )
    )


def pulse_score_component(
    opportunity: ArbOpportunity,
) -> float:
    if opportunity.pulse_score is None:
        return 50.0

    return clamp(
        float(
            opportunity.pulse_score
        )
    )


def validation_score(
    opportunity: ArbOpportunity,
) -> float:
    if (
        opportunity.validation_status
        == ValidationStatus.VALID
    ):
        return 100.0

    if (
        opportunity.validation_status
        == ValidationStatus.REVIEW
    ):
        return 45.0

    return 0.0


@dataclass(slots=True)
class RankedOpportunity:
    opportunity: ArbOpportunity

    discovery_score: float
    confidence_percent: float
    execution_label: str

    roi_score: float
    profit_score: float
    bookmaker_score: float
    stability_score: float
    freshness_score: float
    pulse_score: float
    validation_score: float

    bookmaker_count: int
    price_age_seconds: Optional[int]

    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "discovery_score": round(
                self.discovery_score,
                2,
            ),
            "confidence_percent": round(
                self.confidence_percent,
                2,
            ),
            "execution_label": (
                self.execution_label
            ),
            "components": {
                "roi": round(
                    self.roi_score,
                    2,
                ),
                "profit": round(
                    self.profit_score,
                    2,
                ),
                "bookmakers": round(
                    self.bookmaker_score,
                    2,
                ),
                "stability": round(
                    self.stability_score,
                    2,
                ),
                "freshness": round(
                    self.freshness_score,
                    2,
                ),
                "pulse": round(
                    self.pulse_score,
                    2,
                ),
                "validation": round(
                    self.validation_score,
                    2,
                ),
            },
            "bookmaker_count": (
                self.bookmaker_count
            ),
            "price_age_seconds": (
                self.price_age_seconds
            ),
            "warnings": self.warnings,
            "opportunity": (
                self.opportunity.to_dict()
            ),
        }


def execution_label(
    score: float,
    opportunity: ArbOpportunity,
) -> str:
    if not opportunity.is_profitable:
        return "REJECT"

    if (
        opportunity.validation_status
        == ValidationStatus.INVALID
    ):
        return "REJECT"

    if (
        opportunity.stability_status
        == StabilityStatus.EXPIRED
    ):
        return "EXPIRED"

    if score >= 85:
        return "EXECUTE"

    if score >= 70:
        return "STRONG"

    if score >= 55:
        return "REVIEW"

    return "WATCH"


def rank_opportunity(
    opportunity: ArbOpportunity,
    *,
    now: Optional[datetime] = None,
    max_price_age_seconds: int = (
        DEFAULT_MAX_PRICE_AGE_SECONDS
    ),
    target_stable_seconds: int = (
        DEFAULT_TARGET_STABLE_SECONDS
    ),
) -> RankedOpportunity:
    roi_component = roi_score(
        opportunity
    )

    profit_component = profit_score(
        opportunity
    )

    bookmakers_component = bookmaker_score(
        opportunity
    )

    stability_component = stability_score(
        opportunity,
        target_stable_seconds=(
            target_stable_seconds
        ),
    )

    freshness_component = freshness_score(
        opportunity,
        now=now,
        max_price_age_seconds=(
            max_price_age_seconds
        ),
    )

    pulse_component = pulse_score_component(
        opportunity
    )

    validation_component = validation_score(
        opportunity
    )

    weighted_score = (
        roi_component * 0.25
        + profit_component * 0.15
        + bookmakers_component * 0.10
        + stability_component * 0.20
        + freshness_component * 0.15
        + pulse_component * 0.05
        + validation_component * 0.10
    )

    confidence = (
        stability_component * 0.35
        + freshness_component * 0.30
        + validation_component * 0.25
        + bookmakers_component * 0.10
    )

    warnings = list(
        opportunity.warnings
    )

    age = price_age_seconds(
        opportunity,
        now=now,
    )

    if (
        age is not None
        and age > max_price_age_seconds
    ):
        warnings.append(
            "Prices are older than the "
            "configured freshness limit."
        )

    if (
        opportunity.stability_status
        == StabilityStatus.VOLATILE
    ):
        warnings.append(
            "Opportunity is volatile."
        )

    if (
        opportunity.validation_status
        != ValidationStatus.VALID
    ):
        warnings.append(
            "Opportunity requires validation."
        )

    label = execution_label(
        weighted_score,
        opportunity,
    )

    return RankedOpportunity(
        opportunity=opportunity,
        discovery_score=clamp(
            weighted_score
        ),
        confidence_percent=clamp(
            confidence
        ),
        execution_label=label,
        roi_score=roi_component,
        profit_score=profit_component,
        bookmaker_score=(
            bookmakers_component
        ),
        stability_score=(
            stability_component
        ),
        freshness_score=(
            freshness_component
        ),
        pulse_score=pulse_component,
        validation_score=(
            validation_component
        ),
        bookmaker_count=(
            unique_bookmaker_count(
                opportunity
            )
        ),
        price_age_seconds=age,
        warnings=warnings,
    )


def rank_opportunities(
    opportunities: Iterable[
        ArbOpportunity
    ],
    *,
    now: Optional[datetime] = None,
    max_price_age_seconds: int = (
        DEFAULT_MAX_PRICE_AGE_SECONDS
    ),
    target_stable_seconds: int = (
        DEFAULT_TARGET_STABLE_SECONDS
    ),
    minimum_score: float = 0.0,
) -> list[RankedOpportunity]:
    ranked = [
        rank_opportunity(
            opportunity,
            now=now,
            max_price_age_seconds=(
                max_price_age_seconds
            ),
            target_stable_seconds=(
                target_stable_seconds
            ),
        )
        for opportunity in opportunities
    ]

    ranked = [
        result
        for result in ranked
        if result.discovery_score
        >= minimum_score
    ]

    ranked.sort(
        key=lambda result: (
            result.discovery_score,
            result.confidence_percent,
            result.opportunity.roi_percent,
            result.opportunity.guaranteed_profit,
        ),
        reverse=True,
    )

    return ranked


def ranked_opportunities_to_dicts(
    opportunities: Iterable[
        ArbOpportunity
    ],
    *,
    now: Optional[datetime] = None,
    max_price_age_seconds: int = (
        DEFAULT_MAX_PRICE_AGE_SECONDS
    ),
    target_stable_seconds: int = (
        DEFAULT_TARGET_STABLE_SECONDS
    ),
    minimum_score: float = 0.0,
) -> list[dict]:
    return [
        result.to_dict()
        for result in rank_opportunities(
            opportunities,
            now=now,
            max_price_age_seconds=(
                max_price_age_seconds
            ),
            target_stable_seconds=(
                target_stable_seconds
            ),
            minimum_score=(
                minimum_score
            ),
        )
    ]
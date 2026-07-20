"""
Pulse IQ race-intelligence models and adaptive signal classification.

Signal tiers are assigned relative to the complete signal population:

- top 5%: ELITE
- next 15%: STRONG
- next 30%: WATCH
- remaining 50%: LOW_VALUE

This keeps the dashboard selective as the volume and score distribution change.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional


class SignalSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SignalCategory(str, Enum):
    MARKET = "MARKET"
    MOVEMENT = "MOVEMENT"
    VOLATILITY = "VOLATILITY"
    ARBITRAGE = "ARBITRAGE"
    WARNING = "WARNING"
    CONSENSUS = "CONSENSUS"
    OTHER = "OTHER"


class SignalTier(str, Enum):
    ELITE = "ELITE"
    STRONG = "STRONG"
    WATCH = "WATCH"
    LOW_VALUE = "LOW_VALUE"


ELITE_PERCENT = 0.05
STRONG_PERCENT = 0.15
WATCH_PERCENT = 0.30


SEVERITY_WEIGHT = {
    SignalSeverity.INFO.value: 1,
    SignalSeverity.WARNING.value: 2,
    SignalSeverity.HIGH.value: 3,
    SignalSeverity.CRITICAL.value: 4,
}

CONFIDENCE_WEIGHT = {
    SignalConfidence.LOW.value: 1,
    SignalConfidence.MEDIUM.value: 2,
    SignalConfidence.HIGH.value: 3,
}

SIGNAL_CATEGORY_BY_TYPE = {
    "market_favourite": SignalCategory.MARKET.value,
    "stable_market_leader": SignalCategory.CONSENSUS.value,
    "biggest_steamer": SignalCategory.MOVEMENT.value,
    "biggest_drifter": SignalCategory.MOVEMENT.value,
    "strongest_late_move": SignalCategory.MOVEMENT.value,
    "most_volatile_runner": SignalCategory.VOLATILITY.value,
    "suspicious_price_spike": SignalCategory.WARNING.value,
    "potential_arb_window": SignalCategory.ARBITRAGE.value,
}

BASE_TYPE_WEIGHT = {
    "potential_arb_window": 7,
    "suspicious_price_spike": 6,
    "strongest_late_move": 5,
    "biggest_steamer": 5,
    "biggest_drifter": 4,
    "stable_market_leader": 3,
    "most_volatile_runner": 3,
    "market_favourite": 1,
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_severity(value: Any) -> str:
    severity = clean(value).upper()

    if severity in SEVERITY_WEIGHT:
        return severity

    return SignalSeverity.INFO.value


def normalise_confidence(value: Any) -> str:
    confidence = clean(value).upper()

    if confidence in CONFIDENCE_WEIGHT:
        return confidence

    return SignalConfidence.MEDIUM.value


def signal_category(signal_type: Any) -> str:
    return SIGNAL_CATEGORY_BY_TYPE.get(
        clean(signal_type),
        SignalCategory.OTHER.value,
    )


def signal_priority_score(
    signal: dict[str, Any],
) -> float:
    signal_type = clean(signal.get("type"))
    severity = normalise_severity(signal.get("severity"))
    confidence = normalise_confidence(signal.get("confidence"))

    impact = abs(safe_float(signal.get("impact")))
    movement = abs(safe_float(signal.get("movement_pct")))
    margin = abs(safe_float(signal.get("margin_pct")))
    volatility = abs(safe_float(signal.get("volatility")))

    score = 0.0
    score += BASE_TYPE_WEIGHT.get(signal_type, 1) * 10
    score += SEVERITY_WEIGHT[severity] * 8
    score += CONFIDENCE_WEIGHT[confidence] * 5
    score += impact * 4
    score += min(movement, 50.0) * 0.6
    score += min(margin, 20.0) * 1.5
    score += min(volatility, 5.0) * 4

    return round(score, 2)


def base_enrich_signal(
    signal: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(signal)

    enriched["severity"] = normalise_severity(
        enriched.get("severity")
    )
    enriched["confidence"] = normalise_confidence(
        enriched.get("confidence")
    )
    enriched["category"] = signal_category(
        enriched.get("type")
    )
    enriched["priority_score"] = signal_priority_score(
        enriched
    )

    return enriched


def percentile_boundaries(
    total: int,
) -> tuple[int, int, int]:
    if total <= 0:
        return 0, 0, 0

    elite_end = max(
        1,
        math.ceil(total * ELITE_PERCENT),
    )

    strong_end = min(
        total,
        elite_end
        + math.ceil(total * STRONG_PERCENT),
    )

    watch_end = min(
        total,
        strong_end
        + math.ceil(total * WATCH_PERCENT),
    )

    return elite_end, strong_end, watch_end


def assign_percentile_tiers(
    signals: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked = [
        base_enrich_signal(signal)
        for signal in signals
        if isinstance(signal, dict)
    ]

    ranked.sort(
        key=lambda signal: (
            safe_float(signal.get("priority_score")),
            abs(safe_float(signal.get("impact"))),
            abs(safe_float(signal.get("movement_pct"))),
        ),
        reverse=True,
    )

    total = len(ranked)
    elite_end, strong_end, watch_end = percentile_boundaries(
        total
    )

    for index, signal in enumerate(ranked):
        rank = index + 1

        if index < elite_end:
            tier = SignalTier.ELITE.value
        elif index < strong_end:
            tier = SignalTier.STRONG.value
        elif index < watch_end:
            tier = SignalTier.WATCH.value
        else:
            tier = SignalTier.LOW_VALUE.value

        percentile = (
            ((total - index) / total) * 100
            if total
            else 0.0
        )

        signal["tier"] = tier
        signal["tier_rank"] = rank
        signal["population_size"] = total
        signal["percentile"] = round(percentile, 2)
        signal["actionable"] = tier != SignalTier.LOW_VALUE.value
        signal["high_priority"] = tier in {
            SignalTier.ELITE.value,
            SignalTier.STRONG.value,
        }

    return ranked


def enrich_signal(
    signal: dict[str, Any],
) -> dict[str, Any]:
    """
    Enrich one signal.

    A single signal cannot be classified meaningfully by population percentile,
    so an existing tier is preserved. Otherwise it defaults to WATCH.
    """
    enriched = base_enrich_signal(signal)

    tier = clean(enriched.get("tier")).upper()

    if tier not in {
        SignalTier.ELITE.value,
        SignalTier.STRONG.value,
        SignalTier.WATCH.value,
        SignalTier.LOW_VALUE.value,
    }:
        tier = SignalTier.WATCH.value

    enriched["tier"] = tier
    enriched["actionable"] = tier != SignalTier.LOW_VALUE.value
    enriched["high_priority"] = tier in {
        SignalTier.ELITE.value,
        SignalTier.STRONG.value,
    }

    return enriched


def enrich_signals(
    signals: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return assign_percentile_tiers(signals)


def classify_signal_tier(
    signal: dict[str, Any],
) -> str:
    return enrich_signal(signal)["tier"]


def signal_is_actionable(
    signal: dict[str, Any],
) -> bool:
    return bool(enrich_signal(signal)["actionable"])


def signal_is_high_priority(
    signal: dict[str, Any],
) -> bool:
    return bool(enrich_signal(signal)["high_priority"])


def filter_actionable_signals(
    signals: Iterable[dict[str, Any]],
    include_watch: bool = True,
) -> list[dict[str, Any]]:
    enriched = enrich_signals(signals)

    allowed = {
        SignalTier.ELITE.value,
        SignalTier.STRONG.value,
    }

    if include_watch:
        allowed.add(SignalTier.WATCH.value)

    return [
        signal
        for signal in enriched
        if signal.get("tier") in allowed
    ]


def signal_tier_summary(
    signals: Iterable[dict[str, Any]],
    *,
    preserve_existing_tiers: bool = False,
) -> dict[str, int]:
    summary = {
        SignalTier.ELITE.value: 0,
        SignalTier.STRONG.value: 0,
        SignalTier.WATCH.value: 0,
        SignalTier.LOW_VALUE.value: 0,
    }

    signal_list = [
        signal
        for signal in signals
        if isinstance(signal, dict)
    ]

    if preserve_existing_tiers:
        enriched = [
            enrich_signal(signal)
            for signal in signal_list
        ]
    else:
        enriched = enrich_signals(signal_list)

    for signal in enriched:
        tier = signal.get(
            "tier",
            SignalTier.LOW_VALUE.value,
        )
        summary[tier] = summary.get(tier, 0) + 1

    return summary


@dataclass(slots=True)
class RaceSignal:
    source: str
    type: str
    course: Optional[str] = None
    race_time: Optional[str] = None
    horse: Optional[str] = None
    impact: float = 0.0
    severity: str = SignalSeverity.INFO.value
    confidence: str = SignalConfidence.MEDIUM.value
    reason: str = ""
    category: Optional[str] = None
    tier: Optional[str] = None
    priority_score: Optional[float] = None
    tier_rank: Optional[int] = None
    population_size: Optional[int] = None
    percentile: Optional[float] = None
    actionable: Optional[bool] = None
    high_priority: Optional[bool] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "RaceSignal":
        known_fields = {
            "source",
            "type",
            "course",
            "race_time",
            "horse",
            "impact",
            "severity",
            "confidence",
            "reason",
            "category",
            "tier",
            "priority_score",
            "tier_rank",
            "population_size",
            "percentile",
            "actionable",
            "high_priority",
        }

        enriched = enrich_signal(data)

        extra = {
            key: value
            for key, value in enriched.items()
            if key not in known_fields
        }

        return cls(
            source=clean(enriched.get("source")),
            type=clean(enriched.get("type")),
            course=enriched.get("course"),
            race_time=enriched.get("race_time"),
            horse=enriched.get("horse"),
            impact=safe_float(enriched.get("impact")),
            severity=normalise_severity(
                enriched.get("severity")
            ),
            confidence=normalise_confidence(
                enriched.get("confidence")
            ),
            reason=clean(enriched.get("reason")),
            category=enriched.get("category"),
            tier=enriched.get("tier"),
            priority_score=safe_float(
                enriched.get("priority_score")
            ),
            tier_rank=(
                int(enriched["tier_rank"])
                if enriched.get("tier_rank") is not None
                else None
            ),
            population_size=(
                int(enriched["population_size"])
                if enriched.get("population_size") is not None
                else None
            ),
            percentile=(
                safe_float(enriched.get("percentile"))
                if enriched.get("percentile") is not None
                else None
            ),
            actionable=bool(enriched.get("actionable")),
            high_priority=bool(enriched.get("high_priority")),
            extra=extra,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {})
        data.update(extra)
        return data


@dataclass(slots=True)
class RaceIntelligenceRecord:
    race_key: str
    course: Optional[str]
    race_time: Optional[str]
    runner_count: int
    signals: list[RaceSignal]
    url: Optional[str] = None
    generated_at: Optional[str] = None
    latest_seen_at: Optional[str] = None
    source: str = "market_history"
    signal_version: Optional[str] = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "RaceIntelligenceRecord":
        signals = [
            RaceSignal.from_dict(signal)
            for signal in data.get("signals", [])
            if isinstance(signal, dict)
        ]

        return cls(
            race_key=clean(data.get("race_key")),
            course=data.get("course"),
            race_time=data.get("race_time"),
            runner_count=int(data.get("runner_count") or 0),
            signals=signals,
            url=data.get("url"),
            generated_at=data.get("generated_at"),
            latest_seen_at=data.get("latest_seen_at"),
            source=clean(data.get("source")) or "market_history",
            signal_version=data.get("signal_version"),
        )

    def to_dict(self) -> dict[str, Any]:
        signal_dicts = [
            signal.to_dict()
            for signal in self.signals
        ]

        return {
            "race_key": self.race_key,
            "course": self.course,
            "race_time": self.race_time,
            "runner_count": self.runner_count,
            "signals": signal_dicts,
            "url": self.url,
            "generated_at": self.generated_at,
            "latest_seen_at": self.latest_seen_at,
            "source": self.source,
            "signal_version": self.signal_version,
            "tier_summary": signal_tier_summary(
                signal_dicts,
                preserve_existing_tiers=True,
            ),
        }
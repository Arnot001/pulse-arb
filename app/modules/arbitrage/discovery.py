from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.modules.arbitrage.scanner import (
    MarketScanResult,
)


NEAR_ARB_MAX_PERCENTAGE = 101.0
VALUE_MAX_PERCENTAGE = 103.0
REVIEW_MAX_PERCENTAGE = 105.0


def clean(value) -> str:
    return str(
        value or ""
    ).strip()


def safe_float(
    value,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def market_label(
    result: MarketScanResult,
) -> str:
    if not result.complete:
        return "INCOMPLETE"

    percentage = (
        result.market_percentage
    )

    if percentage < 100.0:
        return "GUARANTEED ARB"

    if percentage <= (
        NEAR_ARB_MAX_PERCENTAGE
    ):
        return "ALMOST THERE"

    if percentage <= (
        VALUE_MAX_PERCENTAGE
    ):
        return "BEST VALUE"

    if percentage <= (
        REVIEW_MAX_PERCENTAGE
    ):
        return "WORTH WATCHING"

    return "IGNORE"


def market_score(
    result: MarketScanResult,
) -> float:
    if not result.complete:
        return 0.0

    percentage = max(
        result.market_percentage,
        0.0,
    )

    if percentage < 100.0:
        return 100.0

    distance_from_arb = (
        percentage - 100.0
    )

    return clamp(
        100.0
        - distance_from_arb
        * 15.0
    )


@dataclass(slots=True)
class MarketDiscovery:
    race_id: str
    course: str
    race_date: str
    race_time: str

    label: str
    score: float

    complete: bool
    runner_count: int
    priced_runner_count: int

    market_percentage: float
    arb_margin_percent: float
    distance_from_arb: float

    is_guaranteed_arb: bool
    warnings: list[str]

    opportunity: Optional[dict]

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "course": self.course,
            "race_date": self.race_date,
            "race_time": self.race_time,
            "label": self.label,
            "score": round(
                self.score,
                2,
            ),
            "complete": self.complete,
            "runner_count": (
                self.runner_count
            ),
            "priced_runner_count": (
                self.priced_runner_count
            ),
            "market_percentage": round(
                self.market_percentage,
                2,
            ),
            "arb_margin_percent": round(
                self.arb_margin_percent,
                2,
            ),
            "distance_from_arb": round(
                self.distance_from_arb,
                2,
            ),
            "is_guaranteed_arb": (
                self.is_guaranteed_arb
            ),
            "warnings": self.warnings,
            "opportunity": (
                self.opportunity
            ),
        }


def discover_market(
    result: MarketScanResult,
) -> MarketDiscovery:
    percentage = safe_float(
        result.market_percentage
    )

    distance_from_arb = max(
        0.0,
        percentage - 100.0,
    )

    return MarketDiscovery(
        race_id=result.race_id,
        course=result.course,
        race_date=result.race_date,
        race_time=result.race_time,
        label=market_label(
            result
        ),
        score=market_score(
            result
        ),
        complete=result.complete,
        runner_count=(
            result.runner_count
        ),
        priced_runner_count=(
            result.priced_runner_count
        ),
        market_percentage=percentage,
        arb_margin_percent=(
            result.arb_margin_percent
        ),
        distance_from_arb=(
            distance_from_arb
        ),
        is_guaranteed_arb=(
            result.is_arbitrage
        ),
        warnings=list(
            result.warnings
        ),
        opportunity=(
            result.opportunity.to_dict()
            if result.opportunity
            else None
        ),
    )


def discover_markets(
    results: Iterable[
        MarketScanResult
    ],
    *,
    include_ignored: bool = False,
    include_incomplete: bool = False,
) -> list[MarketDiscovery]:
    discoveries = [
        discover_market(
            result
        )
        for result in results
    ]

    if not include_ignored:
        discoveries = [
            result
            for result in discoveries
            if result.label != "IGNORE"
        ]

    if not include_incomplete:
        discoveries = [
            result
            for result in discoveries
            if result.complete
        ]

    discoveries.sort(
        key=lambda result: (
            result.score,
            -result.market_percentage,
            result.course,
            result.race_time,
        ),
        reverse=True,
    )

    return discoveries


def discovery_summary(
    discoveries: Iterable[
        MarketDiscovery
    ],
) -> dict:
    items = list(
        discoveries
    )

    labels = {}

    for item in items:
        labels[item.label] = (
            labels.get(
                item.label,
                0,
            )
            + 1
        )

    complete = [
        item
        for item in items
        if item.complete
    ]

    best_market = (
        min(
            complete,
            key=lambda item: (
                item.market_percentage
            ),
        )
        if complete
        else None
    )

    return {
        "markets": len(
            items
        ),
        "guaranteed_arbs": labels.get(
            "GUARANTEED ARB",
            0,
        ),
        "almost_there": labels.get(
            "ALMOST THERE",
            0,
        ),
        "best_value": labels.get(
            "BEST VALUE",
            0,
        ),
        "worth_watching": labels.get(
            "WORTH WATCHING",
            0,
        ),
        "incomplete": labels.get(
            "INCOMPLETE",
            0,
        ),
        "ignored": labels.get(
            "IGNORE",
            0,
        ),
        "best_market": (
            best_market.to_dict()
            if best_market
            else None
        ),
        "labels": labels,
    }


def discoveries_to_dicts(
    discoveries: Iterable[
        MarketDiscovery
    ],
) -> list[dict]:
    return [
        discovery.to_dict()
        for discovery in discoveries
    ]
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Optional

from app.modules.arbitrage.engine import ArbitrageEngine
from app.modules.arbitrage.models import (
    ArbLeg,
    ArbOpportunity,
    MarketType,
    OpportunityType,
    PriceSide,
    PriceSourceType,
    RaceMarket,
    StabilityStatus,
    ValidationStatus,
)


DEFAULT_TOTAL_STAKE = 100.0
MINIMUM_RUNNERS = 2
ROUNDING_TOLERANCE = 0.02


@dataclass(slots=True)
class MarketScanResult:
    race_id: str
    course: str
    race_date: str
    race_time: str

    complete: bool
    runner_count: int
    priced_runner_count: int

    implied_probability: float
    market_percentage: float
    arb_margin_percent: float

    opportunity: Optional[ArbOpportunity]
    warnings: list[str]

    @property
    def is_arbitrage(self) -> bool:
        return self.opportunity is not None

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "course": self.course,
            "race_date": self.race_date,
            "race_time": self.race_time,
            "complete": self.complete,
            "runner_count": self.runner_count,
            "priced_runner_count": self.priced_runner_count,
            "implied_probability": round(
                self.implied_probability,
                8,
            ),
            "market_percentage": round(
                self.market_percentage,
                4,
            ),
            "arb_margin_percent": round(
                self.arb_margin_percent,
                4,
            ),
            "is_arbitrage": self.is_arbitrage,
            "warnings": self.warnings,
            "opportunity": (
                self.opportunity.to_dict()
                if self.opportunity
                else None
            ),
        }


def safe_total_stake(
    value: float,
) -> float:
    try:
        stake = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "total_stake must be a number"
        )

    if stake <= 0:
        raise ValueError(
            "total_stake must be greater than zero"
        )

    return stake


def opportunity_id(
    race: RaceMarket,
    legs: list[ArbLeg],
) -> str:
    price_signature = "|".join(
        sorted(
            (
                f"{leg.runner_key}:"
                f"{leg.source}:"
                f"{leg.decimal_odds:.8f}"
            )
            for leg in legs
        )
    )

    raw = (
        f"{race.race_id}|"
        f"{race.market_type.value}|"
        f"{price_signature}"
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]

    return (
        f"horse-back-back-"
        f"{digest}"
    )


def best_bookmaker_prices(
    race: RaceMarket,
) -> list[tuple]:
    selections = []

    for runner in race.active_runners():
        prices = runner.get_prices(
            side=PriceSide.BACK,
            source_type=(
                PriceSourceType.BOOKMAKER
            ),
            market_type=race.market_type,
            active_only=True,
        )

        if not prices:
            continue

        best_price = max(
            prices,
            key=lambda price: (
                price.net_decimal_odds,
                price.decimal_odds,
            ),
        )

        selections.append(
            (
                runner,
                best_price,
            )
        )

    return selections


def market_probability(
    selections: Iterable[tuple],
) -> float:
    return sum(
        1.0 / price.net_decimal_odds
        for _, price in selections
    )


def allocate_equal_return_stakes(
    selections: list[tuple],
    total_stake: float,
) -> list[ArbLeg]:
    implied = market_probability(
        selections
    )

    if implied <= 0:
        return []

    legs = []

    for runner, price in selections:
        probability = (
            1.0 / price.net_decimal_odds
        )

        stake = total_stake * (
            probability / implied
        )

        rounded_stake = round(
            stake,
            2,
        )

        legs.append(
            ArbLeg(
                runner_name=(
                    runner.runner_name
                ),
                runner_key=(
                    runner.runner_key
                ),
                source=price.source,
                source_type=(
                    price.source_type
                ),
                side=PriceSide.BACK,
                decimal_odds=(
                    price.net_decimal_odds
                ),
                stake=rounded_stake,
                market_type=(
                    price.market_type
                ),
                commission_rate=(
                    price.commission_rate
                ),
                liability=None,
                potential_return=round(
                    rounded_stake
                    * price.net_decimal_odds,
                    2,
                ),
                source_url=(
                    price.source_url
                ),
                market_id=(
                    price.market_id
                ),
                selection_id=(
                    price.selection_id
                ),
                metadata={
                    "raw_decimal_odds": (
                        price.decimal_odds
                    ),
                    "raw_odds": (
                        price.raw_odds
                    ),
                    "implied_probability": (
                        price.implied_probability
                    ),
                },
            )
        )

    return legs


def rebalance_rounding(
    legs: list[ArbLeg],
    target_total_stake: float,
) -> None:
    if not legs:
        return

    current_total = round(
        sum(
            leg.stake
            for leg in legs
        ),
        2,
    )

    difference = round(
        target_total_stake
        - current_total,
        2,
    )

    if abs(difference) < 0.005:
        return

    target_leg = max(
        legs,
        key=lambda leg: (
            leg.decimal_odds
        ),
    )

    new_stake = round(
        target_leg.stake
        + difference,
        2,
    )

    if new_stake < 0:
        raise ValueError(
            "Rounding adjustment produced "
            "a negative stake."
        )

    target_leg.stake = new_stake
    target_leg.potential_return = round(
        new_stake
        * target_leg.decimal_odds,
        2,
    )


def scan_market(
    race: RaceMarket,
    total_stake: float = (
        DEFAULT_TOTAL_STAKE
    ),
) -> MarketScanResult:
    total_stake = safe_total_stake(
        total_stake
    )

    warnings = []
    active_runners = (
        race.active_runners()
    )

    selections = (
        best_bookmaker_prices(
            race
        )
    )

    runner_count = len(
        active_runners
    )

    priced_runner_count = len(
        selections
    )

    complete = (
        runner_count >= MINIMUM_RUNNERS
        and priced_runner_count
        == runner_count
    )

    if runner_count < MINIMUM_RUNNERS:
        warnings.append(
            "Race has fewer than two "
            "active runners."
        )

    if (
        race.expected_runner_count
        is not None
        and runner_count
        != race.expected_runner_count
    ):
        complete = False
        warnings.append(
            "Active runner count does not "
            "match expected runner count."
        )

    if priced_runner_count != runner_count:
        warnings.append(
            "At least one active runner "
            "has no bookmaker back price."
        )

    implied_probability = (
        market_probability(
            selections
        )
        if selections
        else 0.0
    )

    market_percentage = (
        implied_probability * 100.0
    )

    arb_margin_percent = (
        (1.0 - implied_probability)
        * 100.0
    )

    if not complete:
        return MarketScanResult(
            race_id=race.race_id,
            course=race.course,
            race_date=race.race_date,
            race_time=race.race_time,
            complete=False,
            runner_count=runner_count,
            priced_runner_count=(
                priced_runner_count
            ),
            implied_probability=(
                implied_probability
            ),
            market_percentage=(
                market_percentage
            ),
            arb_margin_percent=(
                arb_margin_percent
            ),
            opportunity=None,
            warnings=warnings,
        )

    if implied_probability >= 1.0:
        return MarketScanResult(
            race_id=race.race_id,
            course=race.course,
            race_date=race.race_date,
            race_time=race.race_time,
            complete=True,
            runner_count=runner_count,
            priced_runner_count=(
                priced_runner_count
            ),
            implied_probability=(
                implied_probability
            ),
            market_percentage=(
                market_percentage
            ),
            arb_margin_percent=(
                arb_margin_percent
            ),
            opportunity=None,
            warnings=warnings,
        )

    legs = allocate_equal_return_stakes(
        selections=selections,
        total_stake=total_stake,
    )

    rebalance_rounding(
        legs,
        total_stake,
    )

    actual_total_stake = round(
        sum(
            leg.stake
            for leg in legs
        ),
        2,
    )

    returns = [
        float(
            leg.potential_return or 0.0
        )
        for leg in legs
    ]

    guaranteed_return = round(
        min(returns),
        2,
    )

    guaranteed_profit = round(
        guaranteed_return
        - actual_total_stake,
        2,
    )

    roi = (
        (
            guaranteed_profit
            / actual_total_stake
        )
        * 100.0
        if actual_total_stake > 0
        else 0.0
    )

    return_spread = round(
        max(returns)
        - min(returns),
        2,
    )

    validation_status = (
        ValidationStatus.VALID
    )

    if return_spread > ROUNDING_TOLERANCE:
        validation_status = (
            ValidationStatus.REVIEW
        )

        warnings.append(
            "Rounded stakes produce a "
            f"£{return_spread:.2f} return spread."
        )

    if guaranteed_profit <= 0:
        validation_status = (
            ValidationStatus.INVALID
        )

        warnings.append(
            "Rounded stakes removed the "
            "guaranteed profit."
        )

    opportunity = ArbOpportunity(
        opportunity_id=opportunity_id(
            race,
            legs,
        ),
        race_id=race.race_id,
        course=race.course,
        race_date=race.race_date,
        race_time=race.race_time,
        opportunity_type=(
            OpportunityType.BACK_BACK
        ),
        legs=legs,
        total_stake=actual_total_stake,
        guaranteed_return=(
            guaranteed_return
        ),
        guaranteed_profit=(
            guaranteed_profit
        ),
        roi_percent=round(
            roi,
            4,
        ),
        validation_status=(
            validation_status
        ),
        stability_status=(
            StabilityStatus.NEW
        ),
        warnings=warnings,
        metadata={
            "market_type": (
                race.market_type.value
            ),
            "race_name": race.race_name,
            "source_url": (
                race.source_url
            ),
            "runner_count": (
                runner_count
            ),
            "priced_runner_count": (
                priced_runner_count
            ),
            "implied_probability": round(
                implied_probability,
                8,
            ),
            "market_percentage": round(
                market_percentage,
                4,
            ),
            "arb_margin_percent": round(
                arb_margin_percent,
                4,
            ),
            "return_spread": (
                return_spread
            ),
        },
    )

    return MarketScanResult(
        race_id=race.race_id,
        course=race.course,
        race_date=race.race_date,
        race_time=race.race_time,
        complete=True,
        runner_count=runner_count,
        priced_runner_count=(
            priced_runner_count
        ),
        implied_probability=(
            implied_probability
        ),
        market_percentage=(
            market_percentage
        ),
        arb_margin_percent=(
            arb_margin_percent
        ),
        opportunity=opportunity,
        warnings=warnings,
    )


def scan_markets(
    races: Iterable[RaceMarket],
    total_stake: float = (
        DEFAULT_TOTAL_STAKE
    ),
    include_non_arbs: bool = False,
) -> list[MarketScanResult]:
    results = [
        scan_market(
            race,
            total_stake=total_stake,
        )
        for race in races
    ]

    if not include_non_arbs:
        results = [
            result
            for result in results
            if result.is_arbitrage
        ]

    results.sort(
        key=lambda result: (
            (
                result.opportunity.roi_percent
                if result.opportunity
                else -999.0
            ),
            result.arb_margin_percent,
            result.course,
            result.race_time,
        ),
        reverse=True,
    )

    return results


def scan_snapshots(
    snapshots: Iterable[dict],
    total_stake: float = (
        DEFAULT_TOTAL_STAKE
    ),
    include_non_arbs: bool = False,
) -> list[MarketScanResult]:
    engine = ArbitrageEngine()

    markets = engine.load_many(
        snapshots
    )

    return scan_markets(
        markets,
        total_stake=total_stake,
        include_non_arbs=(
            include_non_arbs
        ),
    )


def opportunities_from_markets(
    races: Iterable[RaceMarket],
    total_stake: float = (
        DEFAULT_TOTAL_STAKE
    ),
) -> list[ArbOpportunity]:
    return [
        result.opportunity
        for result in scan_markets(
            races,
            total_stake=total_stake,
            include_non_arbs=False,
        )
        if result.opportunity is not None
    ]


def opportunities_from_snapshots(
    snapshots: Iterable[dict],
    total_stake: float = (
        DEFAULT_TOTAL_STAKE
    ),
) -> list[ArbOpportunity]:
    return [
        result.opportunity
        for result in scan_snapshots(
            snapshots,
            total_stake=total_stake,
            include_non_arbs=False,
        )
        if result.opportunity is not None
    ]
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


class MarketType(str, Enum):
    WIN = "WIN"
    PLACE = "PLACE"
    EACH_WAY = "EACH_WAY"
    FORECAST = "FORECAST"
    TRICAST = "TRICAST"


class PriceSide(str, Enum):
    BACK = "BACK"
    LAY = "LAY"


class PriceSourceType(str, Enum):
    BOOKMAKER = "BOOKMAKER"
    EXCHANGE = "EXCHANGE"


class MarketStatus(str, Enum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    REVIEW = "REVIEW"
    INVALID = "INVALID"


class StabilityStatus(str, Enum):
    NEW = "NEW"
    STABLE = "STABLE"
    VOLATILE = "VOLATILE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class OpportunityType(str, Enum):
    BACK_BACK = "BACK_BACK"
    BACK_LAY = "BACK_LAY"
    RACE_BOOK = "RACE_BOOK"


@dataclass
class MarketPrice:
    source: str
    source_type: PriceSourceType
    side: PriceSide
    decimal_odds: float

    market_type: MarketType = MarketType.WIN

    raw_odds: Optional[str] = None
    commission_rate: float = 0.0
    available_liquidity: Optional[float] = None

    captured_at: str = field(
        default_factory=utc_now_iso
    )

    source_url: Optional[str] = None
    market_id: Optional[str] = None
    selection_id: Optional[str] = None

    is_active: bool = True
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.source = str(
            self.source or ""
        ).strip()

        self.decimal_odds = float(
            self.decimal_odds
        )

        self.commission_rate = float(
            self.commission_rate or 0.0
        )

        if self.available_liquidity is not None:
            self.available_liquidity = float(
                self.available_liquidity
            )

        if self.decimal_odds <= 1.0:
            raise ValueError(
                "decimal_odds must be greater than 1.0"
            )

        if not 0.0 <= self.commission_rate <= 1.0:
            raise ValueError(
                "commission_rate must be between 0.0 and 1.0"
            )

        if (
            self.available_liquidity is not None
            and self.available_liquidity < 0
        ):
            raise ValueError(
                "available_liquidity cannot be negative"
            )

    @property
    def implied_probability(self) -> float:
        return round(
            1.0 / self.decimal_odds,
            8,
        )

    @property
    def net_decimal_odds(self) -> float:
        """
        Approximate net decimal odds after commission.

        For bookmaker prices, commission is normally zero.

        For exchange back prices, commission applies to winnings.

        Lay commission is handled by the arb calculator because the
        calculation depends on liability and opposing outcomes.
        """

        if self.commission_rate <= 0:
            return self.decimal_odds

        winnings_component = (
            self.decimal_odds - 1.0
        )

        net_winnings = winnings_component * (
            1.0 - self.commission_rate
        )

        return round(
            net_winnings + 1.0,
            8,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type.value,
            "side": self.side.value,
            "decimal_odds": self.decimal_odds,
            "raw_odds": self.raw_odds,
            "market_type": self.market_type.value,
            "commission_rate": self.commission_rate,
            "available_liquidity": self.available_liquidity,
            "captured_at": self.captured_at,
            "source_url": self.source_url,
            "market_id": self.market_id,
            "selection_id": self.selection_id,
            "is_active": self.is_active,
            "implied_probability": (
                self.implied_probability
            ),
            "net_decimal_odds": (
                self.net_decimal_odds
            ),
            "metadata": self.metadata,
        }


@dataclass
class RunnerMarket:
    runner_name: str
    runner_key: str

    card_number: Optional[str] = None
    draw: Optional[str] = None
    horse_id: Optional[str] = None

    prices: list[MarketPrice] = field(
        default_factory=list
    )

    is_non_runner: bool = False
    market_rank: Optional[int] = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.runner_name = str(
            self.runner_name or ""
        ).strip()

        self.runner_key = str(
            self.runner_key or ""
        ).strip().lower()

        if not self.runner_name:
            raise ValueError(
                "runner_name is required"
            )

        if not self.runner_key:
            raise ValueError(
                "runner_key is required"
            )

    def add_price(
        self,
        price: MarketPrice,
    ) -> None:
        self.prices.append(
            price
        )

    def get_prices(
        self,
        side: Optional[PriceSide] = None,
        source_type: Optional[
            PriceSourceType
        ] = None,
        market_type: Optional[
            MarketType
        ] = None,
        active_only: bool = True,
    ) -> list[MarketPrice]:
        results = []

        for price in self.prices:
            if (
                active_only
                and not price.is_active
            ):
                continue

            if (
                side is not None
                and price.side != side
            ):
                continue

            if (
                source_type is not None
                and price.source_type
                != source_type
            ):
                continue

            if (
                market_type is not None
                and price.market_type
                != market_type
            ):
                continue

            results.append(
                price
            )

        return results

    def best_back_price(
        self,
        market_type: MarketType = (
            MarketType.WIN
        ),
    ) -> Optional[MarketPrice]:
        prices = self.get_prices(
            side=PriceSide.BACK,
            market_type=market_type,
        )

        if not prices:
            return None

        return max(
            prices,
            key=lambda price: (
                price.net_decimal_odds
            ),
        )

    def best_lay_price(
        self,
        market_type: MarketType = (
            MarketType.WIN
        ),
    ) -> Optional[MarketPrice]:
        prices = self.get_prices(
            side=PriceSide.LAY,
            source_type=(
                PriceSourceType.EXCHANGE
            ),
            market_type=market_type,
        )

        if not prices:
            return None

        return min(
            prices,
            key=lambda price: (
                price.decimal_odds
            ),
        )

    def bookmaker_prices(
        self,
        market_type: MarketType = (
            MarketType.WIN
        ),
    ) -> list[MarketPrice]:
        return self.get_prices(
            source_type=(
                PriceSourceType.BOOKMAKER
            ),
            market_type=market_type,
        )

    def exchange_prices(
        self,
        market_type: MarketType = (
            MarketType.WIN
        ),
    ) -> list[MarketPrice]:
        return self.get_prices(
            source_type=(
                PriceSourceType.EXCHANGE
            ),
            market_type=market_type,
        )

    def to_dict(self) -> dict[str, Any]:
        best_back = self.best_back_price()
        best_lay = self.best_lay_price()

        return {
            "runner_name": self.runner_name,
            "runner_key": self.runner_key,
            "card_number": self.card_number,
            "draw": self.draw,
            "horse_id": self.horse_id,
            "is_non_runner": self.is_non_runner,
            "market_rank": self.market_rank,
            "price_count": len(
                self.prices
            ),
            "best_back_price": (
                best_back.to_dict()
                if best_back
                else None
            ),
            "best_lay_price": (
                best_lay.to_dict()
                if best_lay
                else None
            ),
            "prices": [
                price.to_dict()
                for price in self.prices
            ],
            "metadata": self.metadata,
        }


@dataclass
class RaceMarket:
    race_id: str
    course: str
    race_time: str
    race_date: str

    runners: list[RunnerMarket] = field(
        default_factory=list
    )

    race_name: Optional[str] = None
    source_url: Optional[str] = None

    market_type: MarketType = (
        MarketType.WIN
    )

    status: MarketStatus = (
        MarketStatus.UNKNOWN
    )

    collected_at: str = field(
        default_factory=utc_now_iso
    )

    expected_runner_count: Optional[int] = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.race_id = str(
            self.race_id or ""
        ).strip()

        self.course = str(
            self.course or ""
        ).strip()

        self.race_time = str(
            self.race_time or ""
        ).strip()

        self.race_date = str(
            self.race_date or ""
        ).strip()

        if not self.race_id:
            raise ValueError(
                "race_id is required"
            )

        if not self.course:
            raise ValueError(
                "course is required"
            )

        if not self.race_time:
            raise ValueError(
                "race_time is required"
            )

        if not self.race_date:
            raise ValueError(
                "race_date is required"
            )

    def add_runner(
        self,
        runner: RunnerMarket,
    ) -> None:
        self.runners.append(
            runner
        )

    def active_runners(
        self,
    ) -> list[RunnerMarket]:
        return [
            runner
            for runner in self.runners
            if not runner.is_non_runner
        ]

    def get_runner(
        self,
        runner_key: str,
    ) -> Optional[RunnerMarket]:
        normalized_key = str(
            runner_key or ""
        ).strip().lower()

        for runner in self.runners:
            if (
                runner.runner_key
                == normalized_key
            ):
                return runner

        return None

    @property
    def runner_count(self) -> int:
        return len(
            self.active_runners()
        )

    @property
    def is_complete(self) -> bool:
        if self.runner_count == 0:
            return False

        if (
            self.expected_runner_count
            is not None
            and self.runner_count
            != self.expected_runner_count
        ):
            return False

        return all(
            bool(
                runner.get_prices(
                    market_type=(
                        self.market_type
                    )
                )
            )
            for runner in self.active_runners()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "race_id": self.race_id,
            "course": self.course,
            "race_time": self.race_time,
            "race_date": self.race_date,
            "race_name": self.race_name,
            "source_url": self.source_url,
            "market_type": (
                self.market_type.value
            ),
            "status": self.status.value,
            "collected_at": self.collected_at,
            "expected_runner_count": (
                self.expected_runner_count
            ),
            "runner_count": (
                self.runner_count
            ),
            "is_complete": (
                self.is_complete
            ),
            "runners": [
                runner.to_dict()
                for runner in self.runners
            ],
            "metadata": self.metadata,
        }


@dataclass
class ArbLeg:
    runner_name: str
    runner_key: str

    source: str
    source_type: PriceSourceType
    side: PriceSide

    decimal_odds: float
    stake: float

    market_type: MarketType = (
        MarketType.WIN
    )

    commission_rate: float = 0.0
    liability: Optional[float] = None
    potential_return: Optional[float] = None

    source_url: Optional[str] = None
    market_id: Optional[str] = None
    selection_id: Optional[str] = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.decimal_odds = float(
            self.decimal_odds
        )

        self.stake = float(
            self.stake
        )

        self.commission_rate = float(
            self.commission_rate or 0.0
        )

        if self.liability is not None:
            self.liability = float(
                self.liability
            )

        if self.potential_return is not None:
            self.potential_return = float(
                self.potential_return
            )

        if self.decimal_odds <= 1.0:
            raise ValueError(
                "decimal_odds must be greater than 1.0"
            )

        if self.stake < 0:
            raise ValueError(
                "stake cannot be negative"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner_name": self.runner_name,
            "runner_key": self.runner_key,
            "source": self.source,
            "source_type": (
                self.source_type.value
            ),
            "side": self.side.value,
            "market_type": (
                self.market_type.value
            ),
            "decimal_odds": (
                self.decimal_odds
            ),
            "stake": round(
                self.stake,
                2,
            ),
            "commission_rate": (
                self.commission_rate
            ),
            "liability": (
                round(
                    self.liability,
                    2,
                )
                if self.liability
                is not None
                else None
            ),
            "potential_return": (
                round(
                    self.potential_return,
                    2,
                )
                if self.potential_return
                is not None
                else None
            ),
            "source_url": self.source_url,
            "market_id": self.market_id,
            "selection_id": (
                self.selection_id
            ),
            "metadata": self.metadata,
        }


@dataclass
class ArbOpportunity:
    opportunity_id: str
    race_id: str

    course: str
    race_date: str
    race_time: str

    opportunity_type: OpportunityType

    legs: list[ArbLeg] = field(
        default_factory=list
    )

    total_stake: float = 0.0
    guaranteed_return: float = 0.0
    guaranteed_profit: float = 0.0
    roi_percent: float = 0.0

    validation_status: ValidationStatus = (
        ValidationStatus.REVIEW
    )

    stability_status: StabilityStatus = (
        StabilityStatus.NEW
    )

    pulse_score: Optional[int] = None

    detected_at: str = field(
        default_factory=utc_now_iso
    )

    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    stable_seconds: int = 0
    seen_count: int = 1

    warnings: list[str] = field(
        default_factory=list
    )

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        self.total_stake = float(
            self.total_stake or 0.0
        )

        self.guaranteed_return = float(
            self.guaranteed_return or 0.0
        )

        self.guaranteed_profit = float(
            self.guaranteed_profit or 0.0
        )

        self.roi_percent = float(
            self.roi_percent or 0.0
        )

        self.stable_seconds = int(
            self.stable_seconds or 0
        )

        self.seen_count = int(
            self.seen_count or 0
        )

        if self.pulse_score is not None:
            self.pulse_score = int(
                self.pulse_score
            )

    @property
    def is_profitable(self) -> bool:
        return (
            self.guaranteed_profit > 0
            and self.roi_percent > 0
        )

    @property
    def is_verified(self) -> bool:
        return (
            self.validation_status
            == ValidationStatus.VALID
            and self.is_profitable
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": (
                self.opportunity_id
            ),
            "race_id": self.race_id,
            "course": self.course,
            "race_date": self.race_date,
            "race_time": self.race_time,
            "opportunity_type": (
                self.opportunity_type.value
            ),
            "legs": [
                leg.to_dict()
                for leg in self.legs
            ],
            "total_stake": round(
                self.total_stake,
                2,
            ),
            "guaranteed_return": round(
                self.guaranteed_return,
                2,
            ),
            "guaranteed_profit": round(
                self.guaranteed_profit,
                2,
            ),
            "roi_percent": round(
                self.roi_percent,
                4,
            ),
            "is_profitable": (
                self.is_profitable
            ),
            "is_verified": (
                self.is_verified
            ),
            "validation_status": (
                self.validation_status.value
            ),
            "stability_status": (
                self.stability_status.value
            ),
            "pulse_score": self.pulse_score,
            "detected_at": self.detected_at,
            "first_seen_at": (
                self.first_seen_at
            ),
            "last_seen_at": (
                self.last_seen_at
            ),
            "stable_seconds": (
                self.stable_seconds
            ),
            "seen_count": self.seen_count,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
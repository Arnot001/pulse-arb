from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from itertools import product
from math import ceil, floor
from typing import Any, Iterable, Mapping, Sequence

from app.modules.arbitrage.calculator import (
    EPSILON,
    decimal_to_probability,
    roi_percent,
    valid_decimal,
    valid_stake,
)


MAX_EXHAUSTIVE_COMBINATIONS = 250_000
DEFAULT_SEARCH_STEPS = 4
DEFAULT_BANKROLL_TOLERANCE = 2.0


# ---------------------------------------------------------
# Optimisation Modes
# ---------------------------------------------------------

class RoundingStrategy(str, Enum):
    EXACT = "EXACT"
    ROUND_10P = "ROUND_10P"
    ROUND_50P = "ROUND_50P"
    ROUND_1 = "ROUND_1"
    ROUND_2 = "ROUND_2"
    ROUND_5 = "ROUND_5"

    @property
    def increment(self) -> float:
        return {
            RoundingStrategy.EXACT: 0.01,
            RoundingStrategy.ROUND_10P: 0.10,
            RoundingStrategy.ROUND_50P: 0.50,
            RoundingStrategy.ROUND_1: 1.00,
            RoundingStrategy.ROUND_2: 2.00,
            RoundingStrategy.ROUND_5: 5.00,
        }[self]


class BankrollMode(str, Enum):
    """
    STAY_WITHIN:
        Only considers plans inside the requested bankroll tolerance.

    MAXIMISE_PROFIT:
        Allows the total stake to move outside the tolerance.

    EXACT_TOTAL:
        Requires the rounded stakes to total the requested bankroll.
    """

    STAY_WITHIN = "STAY_WITHIN"
    MAXIMISE_PROFIT = "MAXIMISE_PROFIT"
    EXACT_TOTAL = "EXACT_TOTAL"


DEFAULT_ROUNDING_STRATEGY = RoundingStrategy.ROUND_2
DEFAULT_BANKROLL_MODE = BankrollMode.STAY_WITHIN


# ---------------------------------------------------------
# Result Objects
# ---------------------------------------------------------

@dataclass(slots=True)
class OptimizedStake:
    selection: str
    bookmaker: str
    odds: float

    exact_stake: float
    recommended_stake: float

    outcome_return: float
    outcome_profit: float

    stake_difference: float
    natural_score: float

    event_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OptimizedStakePlan:
    profitable: bool

    strategy: str
    bankroll_mode: str

    increment: float
    bankroll_tolerance: float

    requested_total_stake: float
    minimum_total_stake: float
    maximum_total_stake: float

    total_stake: float
    guaranteed_return: float
    guaranteed_profit: float
    roi: float

    exact_guaranteed_return: float
    exact_guaranteed_profit: float
    exact_roi: float

    total_stake_difference: float
    profit_sacrifice: float
    market_percentage: float

    natural_stake_score: float
    optimization_method: str

    stakes: list[OptimizedStake]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profitable": self.profitable,
            "strategy": self.strategy,
            "bankroll_mode": self.bankroll_mode,
            "increment": self.increment,
            "bankroll_tolerance": self.bankroll_tolerance,
            "requested_total_stake": self.requested_total_stake,
            "minimum_total_stake": self.minimum_total_stake,
            "maximum_total_stake": self.maximum_total_stake,
            "total_stake": self.total_stake,
            "guaranteed_return": self.guaranteed_return,
            "guaranteed_profit": self.guaranteed_profit,
            "roi": self.roi,
            "exact_guaranteed_return": self.exact_guaranteed_return,
            "exact_guaranteed_profit": self.exact_guaranteed_profit,
            "exact_roi": self.exact_roi,
            "total_stake_difference": self.total_stake_difference,
            "profit_sacrifice": self.profit_sacrifice,
            "market_percentage": self.market_percentage,
            "natural_stake_score": self.natural_stake_score,
            "optimization_method": self.optimization_method,
            "stakes": [
                stake.to_dict()
                for stake in self.stakes
            ],
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class _NormalizedLeg:
    selection: str
    bookmaker: str
    odds: float
    event_url: str | None = None


@dataclass(slots=True)
class _EvaluatedCombination:
    stakes: tuple[float, ...]

    total_stake: float
    guaranteed_return: float
    guaranteed_profit: float
    roi: float

    stake_difference: float
    exact_stake_deviation: float
    natural_stake_score: float


# ---------------------------------------------------------
# Input Normalisation
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


def _normalise_leg(
    leg: Mapping[str, Any],
    index: int,
) -> _NormalizedLeg:
    selection = str(
        _first_present(
            leg,
            (
                "selection",
                "horse",
                "runner",
                "name",
            ),
            f"Selection {index + 1}",
        )
    ).strip()

    bookmaker = str(
        _first_present(
            leg,
            (
                "bookmaker",
                "source",
                "sportsbook",
                "book",
            ),
            "Unknown bookmaker",
        )
    ).strip()

    odds_value = _first_present(
        leg,
        (
            "odds",
            "decimal",
            "decimal_odds",
            "price",
        ),
    )

    if odds_value is None:
        raise ValueError(
            f"Missing odds for {selection}."
        )

    try:
        odds = float(odds_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid odds for {selection}: {odds_value!r}"
        ) from exc

    if not valid_decimal(odds):
        raise ValueError(
            f"Invalid decimal odds for {selection}: {odds}"
        )

    event_url_value = _first_present(
        leg,
        (
            "event_url",
            "url",
            "market_url",
        ),
    )

    event_url = (
        str(event_url_value).strip()
        if event_url_value
        else None
    )

    return _NormalizedLeg(
        selection=selection,
        bookmaker=bookmaker,
        odds=odds,
        event_url=event_url,
    )


def _normalise_legs(
    legs: Iterable[Mapping[str, Any]],
) -> list[_NormalizedLeg]:
    normalised = [
        _normalise_leg(
            leg,
            index,
        )
        for index, leg in enumerate(legs)
    ]

    if len(normalised) < 2:
        raise ValueError(
            "At least two arbitrage legs are required."
        )

    return normalised


# ---------------------------------------------------------
# Exact Stake Maths
# ---------------------------------------------------------

def calculate_exact_stakes(
    odds: Sequence[float],
    total_stake: float,
) -> list[float]:
    if not valid_stake(total_stake):
        raise ValueError(
            "Total stake must exceed zero."
        )

    if len(odds) < 2:
        raise ValueError(
            "At least two prices are required."
        )

    for price in odds:
        if not valid_decimal(price):
            raise ValueError(
                f"Invalid decimal odds: {price}"
            )

    implied_total = sum(
        decimal_to_probability(price)
        for price in odds
    )

    if implied_total <= EPSILON:
        raise ValueError(
            "Unable to calculate implied probability."
        )

    target_return = (
        total_stake / implied_total
    )

    return [
        target_return / price
        for price in odds
    ]


def calculate_market_percentage(
    odds: Sequence[float],
) -> float:
    return sum(
        decimal_to_probability(price)
        for price in odds
    ) * 100.0


# ---------------------------------------------------------
# Rounding Helpers
# ---------------------------------------------------------

def _round_to_increment(
    value: float,
    increment: float,
) -> float:
    return round(
        round(value / increment) * increment,
        2,
    )


def _floor_to_increment(
    value: float,
    increment: float,
) -> float:
    return round(
        floor(value / increment) * increment,
        2,
    )


def _ceil_to_increment(
    value: float,
    increment: float,
) -> float:
    return round(
        ceil(value / increment) * increment,
        2,
    )


def _valid_rounded_stake(
    stake: float,
    increment: float,
) -> bool:
    if stake <= 0:
        return False

    units = stake / increment

    return abs(
        units - round(units)
    ) < 1e-7


# ---------------------------------------------------------
# Natural-Looking Stake Scoring
# ---------------------------------------------------------

def _natural_stake_score(
    stake: float,
) -> float:
    """
    Scores how natural a stake amount looks.

    Higher is better.

    Examples:
        £50 / £40 / £30  -> strongest
        £58 / £32 / £18  -> strong
        £57.40           -> weaker
    """

    rounded = round(
        stake,
        2,
    )

    if abs(
        rounded - round(rounded)
    ) > EPSILON:
        return 0.0

    integer_stake = int(
        round(rounded)
    )

    if integer_stake % 10 == 0:
        return 1.0

    if integer_stake % 5 == 0:
        return 0.90

    if integer_stake % 2 == 0:
        return 0.75

    return 0.45


def _plan_natural_score(
    stakes: Sequence[float],
) -> float:
    if not stakes:
        return 0.0

    scores = [
        _natural_stake_score(stake)
        for stake in stakes
    ]

    return sum(scores) / len(scores)


# ---------------------------------------------------------
# Candidate Validation
# ---------------------------------------------------------

def _bankroll_bounds(
    requested_total_stake: float,
    tolerance: float,
    mode: BankrollMode,
) -> tuple[float, float]:
    if mode == BankrollMode.EXACT_TOTAL:
        return (
            requested_total_stake,
            requested_total_stake,
        )

    if mode == BankrollMode.MAXIMISE_PROFIT:
        return (
            0.0,
            float("inf"),
        )

    return (
        max(
            0.0,
            requested_total_stake - tolerance,
        ),
        requested_total_stake + tolerance,
    )


def _total_allowed(
    total_stake: float,
    requested_total_stake: float,
    tolerance: float,
    mode: BankrollMode,
) -> bool:
    minimum, maximum = _bankroll_bounds(
        requested_total_stake=(
            requested_total_stake
        ),
        tolerance=tolerance,
        mode=mode,
    )

    if mode == BankrollMode.EXACT_TOTAL:
        return (
            abs(
                total_stake
                - requested_total_stake
            )
            <= 0.001
        )

    return (
        minimum - EPSILON
        <= total_stake
        <= maximum + EPSILON
    )


# ---------------------------------------------------------
# Combination Evaluation
# ---------------------------------------------------------

def _evaluate_combination(
    odds: Sequence[float],
    stakes: Sequence[float],
    exact_stakes: Sequence[float],
    requested_total_stake: float,
) -> _EvaluatedCombination:
    total_stake = sum(stakes)

    outcome_returns = [
        odds[index] * stakes[index]
        for index in range(len(odds))
    ]

    guaranteed_return = min(
        outcome_returns
    )

    guaranteed_profit = (
        guaranteed_return
        - total_stake
    )

    roi = roi_percent(
        total_stake,
        guaranteed_profit,
    )

    stake_difference = abs(
        total_stake
        - requested_total_stake
    )

    exact_stake_deviation = sum(
        abs(
            stakes[index]
            - exact_stakes[index]
        )
        for index in range(len(stakes))
    )

    return _EvaluatedCombination(
        stakes=tuple(
            round(stake, 2)
            for stake in stakes
        ),
        total_stake=total_stake,
        guaranteed_return=guaranteed_return,
        guaranteed_profit=guaranteed_profit,
        roi=roi,
        stake_difference=stake_difference,
        exact_stake_deviation=(
            exact_stake_deviation
        ),
        natural_stake_score=(
            _plan_natural_score(stakes)
        ),
    )


def _combination_score(
    result: _EvaluatedCombination,
    bankroll_mode: BankrollMode,
) -> tuple:
    """
    STAY_WITHIN and EXACT_TOTAL priority:

    1. Profitable.
    2. Highest guaranteed profit.
    3. Closest total to requested bankroll.
    4. Most natural-looking stakes.
    5. Lowest deviation from exact maths.
    6. Highest ROI.

    MAXIMISE_PROFIT priority:

    1. Profitable.
    2. Highest guaranteed profit.
    3. Highest ROI.
    4. Most natural-looking stakes.
    """

    if bankroll_mode == BankrollMode.MAXIMISE_PROFIT:
        return (
            result.guaranteed_profit > EPSILON,
            result.guaranteed_profit,
            result.roi,
            result.natural_stake_score,
            -result.exact_stake_deviation,
        )

    return (
        result.guaranteed_profit > EPSILON,
        result.guaranteed_profit,
        -result.stake_difference,
        result.natural_stake_score,
        -result.exact_stake_deviation,
        result.roi,
    )


def _better_result(
    candidate: _EvaluatedCombination,
    current: _EvaluatedCombination | None,
    bankroll_mode: BankrollMode,
) -> bool:
    if current is None:
        return True

    return (
        _combination_score(
            candidate,
            bankroll_mode,
        )
        >
        _combination_score(
            current,
            bankroll_mode,
        )
    )


# ---------------------------------------------------------
# Candidate Generation
# ---------------------------------------------------------

def _stake_candidates(
    exact_stake: float,
    increment: float,
    search_steps: int,
) -> list[float]:
    nearest = _round_to_increment(
        exact_stake,
        increment,
    )

    values = {
        nearest,
        _floor_to_increment(
            exact_stake,
            increment,
        ),
        _ceil_to_increment(
            exact_stake,
            increment,
        ),
    }

    for step in range(
        1,
        search_steps + 1,
    ):
        values.add(
            round(
                nearest
                - (increment * step),
                2,
            )
        )

        values.add(
            round(
                nearest
                + (increment * step),
                2,
            )
        )

    return sorted(
        value
        for value in values
        if _valid_rounded_stake(
            value,
            increment,
        )
    )


def _estimated_combination_count(
    candidates: Sequence[Sequence[float]],
) -> int:
    count = 1

    for leg_candidates in candidates:
        count *= len(leg_candidates)

        if count > MAX_EXHAUSTIVE_COMBINATIONS:
            break

    return count


# ---------------------------------------------------------
# Exhaustive Optimisation
# ---------------------------------------------------------

def _exhaustive_optimise(
    odds: Sequence[float],
    exact_stakes: Sequence[float],
    requested_total_stake: float,
    candidates: Sequence[Sequence[float]],
    bankroll_tolerance: float,
    bankroll_mode: BankrollMode,
) -> _EvaluatedCombination | None:
    best: _EvaluatedCombination | None = None

    for combination in product(
        *candidates,
    ):
        total_stake = sum(combination)

        if not _total_allowed(
            total_stake=total_stake,
            requested_total_stake=(
                requested_total_stake
            ),
            tolerance=bankroll_tolerance,
            mode=bankroll_mode,
        ):
            continue

        evaluated = _evaluate_combination(
            odds=odds,
            stakes=combination,
            exact_stakes=exact_stakes,
            requested_total_stake=(
                requested_total_stake
            ),
        )

        if _better_result(
            candidate=evaluated,
            current=best,
            bankroll_mode=bankroll_mode,
        ):
            best = evaluated

    return best


# ---------------------------------------------------------
# Exact Strategy
# ---------------------------------------------------------

def _exact_evaluation(
    odds: Sequence[float],
    exact_stakes: Sequence[float],
    requested_total_stake: float,
) -> _EvaluatedCombination:
    return _evaluate_combination(
        odds=odds,
        stakes=exact_stakes,
        exact_stakes=exact_stakes,
        requested_total_stake=(
            requested_total_stake
        ),
    )


# ---------------------------------------------------------
# Plan Builder
# ---------------------------------------------------------

def _build_plan(
    legs: Sequence[_NormalizedLeg],
    exact_stakes: Sequence[float],
    optimized: _EvaluatedCombination,
    requested_total_stake: float,
    strategy: RoundingStrategy,
    bankroll_mode: BankrollMode,
    bankroll_tolerance: float,
    optimization_method: str,
) -> OptimizedStakePlan:
    odds = [
        leg.odds
        for leg in legs
    ]

    exact_returns = [
        odds[index] * exact_stakes[index]
        for index in range(len(odds))
    ]

    exact_total_stake = sum(
        exact_stakes
    )

    exact_guaranteed_return = min(
        exact_returns
    )

    exact_guaranteed_profit = (
        exact_guaranteed_return
        - exact_total_stake
    )

    exact_roi = roi_percent(
        exact_total_stake,
        exact_guaranteed_profit,
    )

    minimum_total_stake, maximum_total_stake = (
        _bankroll_bounds(
            requested_total_stake=(
                requested_total_stake
            ),
            tolerance=bankroll_tolerance,
            mode=bankroll_mode,
        )
    )

    if maximum_total_stake == float("inf"):
        maximum_total_stake_value = 0.0
    else:
        maximum_total_stake_value = (
            maximum_total_stake
        )

    stake_records: list[OptimizedStake] = []

    for index, leg in enumerate(legs):
        recommended_stake = (
            optimized.stakes[index]
        )

        outcome_return = (
            leg.odds
            * recommended_stake
        )

        outcome_profit = (
            outcome_return
            - optimized.total_stake
        )

        stake_records.append(
            OptimizedStake(
                selection=leg.selection,
                bookmaker=leg.bookmaker,
                odds=round(
                    leg.odds,
                    4,
                ),
                exact_stake=round(
                    exact_stakes[index],
                    2,
                ),
                recommended_stake=round(
                    recommended_stake,
                    2,
                ),
                outcome_return=round(
                    outcome_return,
                    2,
                ),
                outcome_profit=round(
                    outcome_profit,
                    2,
                ),
                stake_difference=round(
                    recommended_stake
                    - exact_stakes[index],
                    2,
                ),
                natural_score=round(
                    _natural_stake_score(
                        recommended_stake
                    ),
                    3,
                ),
                event_url=leg.event_url,
            )
        )

    profit_sacrifice = max(
        0.0,
        exact_guaranteed_profit
        - optimized.guaranteed_profit,
    )

    market_percentage = (
        calculate_market_percentage(
            odds
        )
    )

    notes: list[str] = []

    if optimized.guaranteed_profit > EPSILON:
        notes.append(
            "Rounded stakes retain guaranteed profit."
        )
    else:
        notes.append(
            "Rounded stakes do not retain guaranteed profit."
        )

    if strategy == RoundingStrategy.ROUND_2:
        notes.append(
            "Stakes use even-pound amounts."
        )

    if bankroll_mode == BankrollMode.STAY_WITHIN:
        notes.append(
            "Total stake remains inside the requested bankroll tolerance."
        )

    if bankroll_mode == BankrollMode.EXACT_TOTAL:
        notes.append(
            "Rounded stakes match the requested bankroll exactly."
        )

    if bankroll_mode == BankrollMode.MAXIMISE_PROFIT:
        notes.append(
            "Profit was prioritised over bankroll proximity."
        )

    if abs(
        optimized.total_stake
        - requested_total_stake
    ) <= EPSILON:
        notes.append(
            "Optimised stakes match the requested bankroll."
        )
    else:
        notes.append(
            "Optimised total differs from the requested bankroll "
            f"by £{abs(optimized.total_stake - requested_total_stake):.2f}."
        )

    return OptimizedStakePlan(
        profitable=(
            optimized.guaranteed_profit
            > EPSILON
        ),
        strategy=strategy.value,
        bankroll_mode=bankroll_mode.value,
        increment=round(
            strategy.increment,
            2,
        ),
        bankroll_tolerance=round(
            bankroll_tolerance,
            2,
        ),
        requested_total_stake=round(
            requested_total_stake,
            2,
        ),
        minimum_total_stake=round(
            minimum_total_stake,
            2,
        ),
        maximum_total_stake=round(
            maximum_total_stake_value,
            2,
        ),
        total_stake=round(
            optimized.total_stake,
            2,
        ),
        guaranteed_return=round(
            optimized.guaranteed_return,
            2,
        ),
        guaranteed_profit=round(
            optimized.guaranteed_profit,
            2,
        ),
        roi=round(
            optimized.roi,
            3,
        ),
        exact_guaranteed_return=round(
            exact_guaranteed_return,
            2,
        ),
        exact_guaranteed_profit=round(
            exact_guaranteed_profit,
            2,
        ),
        exact_roi=round(
            exact_roi,
            3,
        ),
        total_stake_difference=round(
            optimized.total_stake
            - requested_total_stake,
            2,
        ),
        profit_sacrifice=round(
            profit_sacrifice,
            2,
        ),
        market_percentage=round(
            market_percentage,
            3,
        ),
        natural_stake_score=round(
            optimized.natural_stake_score,
            3,
        ),
        optimization_method=(
            optimization_method
        ),
        stakes=stake_records,
        notes=notes,
    )


# ---------------------------------------------------------
# Public Optimiser
# ---------------------------------------------------------

def optimize_back_back_stakes(
    legs: Iterable[Mapping[str, Any]],
    total_stake: float = 100.0,
    strategy: (
        RoundingStrategy | str
    ) = DEFAULT_ROUNDING_STRATEGY,
    bankroll_mode: (
        BankrollMode | str
    ) = DEFAULT_BANKROLL_MODE,
    bankroll_tolerance: float = (
        DEFAULT_BANKROLL_TOLERANCE
    ),
    search_steps: int = DEFAULT_SEARCH_STEPS,
    require_profitable: bool = True,
) -> OptimizedStakePlan:
    """
    Optimise a multi-runner Back/Back arbitrage staking plan.

    Pulse default behaviour:

        Rounding: even-pound stakes
        Bankroll mode: stay within bankroll
        Tolerance: requested bankroll ± £2

    Accepted leg keys:

        selection / horse / runner / name
        bookmaker / source / sportsbook / book
        odds / decimal / decimal_odds / price
        event_url / url / market_url
    """

    if not valid_stake(total_stake):
        raise ValueError(
            "Total stake must exceed zero."
        )

    if bankroll_tolerance < 0:
        raise ValueError(
            "Bankroll tolerance cannot be negative."
        )

    if search_steps < 0:
        raise ValueError(
            "Search steps cannot be negative."
        )

    try:
        selected_strategy = (
            strategy
            if isinstance(
                strategy,
                RoundingStrategy,
            )
            else RoundingStrategy(
                str(strategy).upper()
            )
        )
    except ValueError as exc:
        available = ", ".join(
            item.value
            for item in RoundingStrategy
        )

        raise ValueError(
            f"Unknown rounding strategy: {strategy}. "
            f"Available strategies: {available}"
        ) from exc

    try:
        selected_bankroll_mode = (
            bankroll_mode
            if isinstance(
                bankroll_mode,
                BankrollMode,
            )
            else BankrollMode(
                str(bankroll_mode).upper()
            )
        )
    except ValueError as exc:
        available = ", ".join(
            item.value
            for item in BankrollMode
        )

        raise ValueError(
            f"Unknown bankroll mode: {bankroll_mode}. "
            f"Available modes: {available}"
        ) from exc

    normalised_legs = _normalise_legs(
        legs
    )

    odds = [
        leg.odds
        for leg in normalised_legs
    ]

    market_percentage = (
        calculate_market_percentage(
            odds
        )
    )

    if (
        require_profitable
        and market_percentage >= 100.0
    ):
        raise ValueError(
            "The supplied prices do not form a "
            "Back/Back arbitrage."
        )

    exact_stakes = calculate_exact_stakes(
        odds=odds,
        total_stake=total_stake,
    )

    if selected_strategy == RoundingStrategy.EXACT:
        optimized = _exact_evaluation(
            odds=odds,
            exact_stakes=exact_stakes,
            requested_total_stake=(
                total_stake
            ),
        )

        return _build_plan(
            legs=normalised_legs,
            exact_stakes=exact_stakes,
            optimized=optimized,
            requested_total_stake=(
                total_stake
            ),
            strategy=selected_strategy,
            bankroll_mode=(
                selected_bankroll_mode
            ),
            bankroll_tolerance=(
                bankroll_tolerance
            ),
            optimization_method="EXACT",
        )

    increment = selected_strategy.increment

    candidates = [
        _stake_candidates(
            exact_stake=stake,
            increment=increment,
            search_steps=search_steps,
        )
        for stake in exact_stakes
    ]

    combination_count = (
        _estimated_combination_count(
            candidates
        )
    )

    if (
        combination_count
        > MAX_EXHAUSTIVE_COMBINATIONS
    ):
        raise ValueError(
            "Rounded optimisation candidate space is too large. "
            "Reduce search_steps or use a finer integration strategy."
        )

    optimized = _exhaustive_optimise(
        odds=odds,
        exact_stakes=exact_stakes,
        requested_total_stake=(
            total_stake
        ),
        candidates=candidates,
        bankroll_tolerance=(
            bankroll_tolerance
        ),
        bankroll_mode=(
            selected_bankroll_mode
        ),
    )

    if optimized is None:
        minimum, maximum = _bankroll_bounds(
            requested_total_stake=(
                total_stake
            ),
            tolerance=bankroll_tolerance,
            mode=selected_bankroll_mode,
        )

        raise ValueError(
            "No rounded stake combination was found "
            f"between £{minimum:.2f} and £{maximum:.2f}. "
            "Increase the bankroll tolerance or use a finer "
            "rounding strategy."
        )

    plan = _build_plan(
        legs=normalised_legs,
        exact_stakes=exact_stakes,
        optimized=optimized,
        requested_total_stake=(
            total_stake
        ),
        strategy=selected_strategy,
        bankroll_mode=(
            selected_bankroll_mode
        ),
        bankroll_tolerance=(
            bankroll_tolerance
        ),
        optimization_method="EXHAUSTIVE",
    )

    if (
        require_profitable
        and not plan.profitable
    ):
        raise ValueError(
            "No profitable rounded stake plan was found "
            f"using {selected_strategy.value} inside "
            f"the £{bankroll_tolerance:.2f} bankroll tolerance."
        )

    return plan


# ---------------------------------------------------------
# Convenience Wrappers
# ---------------------------------------------------------

def optimize_even_stakes(
    legs: Iterable[Mapping[str, Any]],
    total_stake: float = 100.0,
    bankroll_tolerance: float = (
        DEFAULT_BANKROLL_TOLERANCE
    ),
) -> OptimizedStakePlan:
    """
    Pulse recommended default.

    Uses even-pound stakes and keeps the total inside
    the requested bankroll tolerance.
    """

    return optimize_back_back_stakes(
        legs=legs,
        total_stake=total_stake,
        strategy=RoundingStrategy.ROUND_2,
        bankroll_mode=BankrollMode.STAY_WITHIN,
        bankroll_tolerance=bankroll_tolerance,
    )


def optimize_exact_total_stakes(
    legs: Iterable[Mapping[str, Any]],
    total_stake: float = 100.0,
) -> OptimizedStakePlan:
    """
    Requires rounded stakes to total the requested bankroll exactly.
    """

    return optimize_back_back_stakes(
        legs=legs,
        total_stake=total_stake,
        strategy=RoundingStrategy.ROUND_2,
        bankroll_mode=BankrollMode.EXACT_TOTAL,
        bankroll_tolerance=0.0,
    )


def optimize_maximum_profit_stakes(
    legs: Iterable[Mapping[str, Any]],
    total_stake: float = 100.0,
) -> OptimizedStakePlan:
    """
    Allows bankroll drift and maximises guaranteed cash profit.
    """

    return optimize_back_back_stakes(
        legs=legs,
        total_stake=total_stake,
        strategy=RoundingStrategy.ROUND_2,
        bankroll_mode=BankrollMode.MAXIMISE_PROFIT,
    )


def optimize_exact_stakes(
    legs: Iterable[Mapping[str, Any]],
    total_stake: float = 100.0,
) -> OptimizedStakePlan:
    return optimize_back_back_stakes(
        legs=legs,
        total_stake=total_stake,
        strategy=RoundingStrategy.EXACT,
        bankroll_mode=BankrollMode.STAY_WITHIN,
    )
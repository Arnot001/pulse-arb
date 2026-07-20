from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

EPSILON = 1e-9


# ---------------------------------------------------------
# Basic Odds Maths
# ---------------------------------------------------------

def fractional_to_decimal(value: str) -> float:
    """
    Convert fractional odds to decimal.

    Examples:
        5/2  -> 3.5
        EVS  -> 2.0
        6.5  -> 6.5
    """

    value = str(value).strip().upper()

    if value in {
        "EVS",
        "EVENS",
        "EVEN",
    }:
        return 2.0

    if "/" in value:
        left, right = value.split("/", 1)

        return (
            float(left) / float(right)
        ) + 1.0

    return float(value)


def decimal_to_probability(
    decimal_odds: float,
) -> float:
    if decimal_odds <= 1:
        raise ValueError(
            "Decimal odds must exceed 1.0"
        )

    return 1.0 / decimal_odds


def probability_to_decimal(
    probability: float,
) -> float:
    if probability <= 0:
        raise ValueError(
            "Probability must exceed zero."
        )

    return 1.0 / probability


def overround(
    probabilities,
) -> float:
    return sum(probabilities)


def arb_percentage(
    probabilities,
) -> float:
    return overround(probabilities) * 100


def is_arbitrage(
    probabilities,
) -> bool:
    return overround(probabilities) < 1.0


# ---------------------------------------------------------
# Profit Maths
# ---------------------------------------------------------

def roi_percent(
    stake: float,
    profit: float,
) -> float:

    if abs(stake) < EPSILON:
        return 0.0

    return (
        profit / stake
    ) * 100.0


def profit(
    total_return: float,
    total_stake: float,
) -> float:
    return total_return - total_stake


def liability(
    lay_stake: float,
    lay_odds: float,
) -> float:

    return (
        lay_odds - 1
    ) * lay_stake


def commission(
    winnings: float,
    rate: float,
) -> float:

    if winnings <= 0:
        return 0.0

    return winnings * rate


# ---------------------------------------------------------
# Validation
# ---------------------------------------------------------

def valid_decimal(
    value: float,
) -> bool:

    if not isfinite(value):
        return False

    return (
        value > 1.0
        and value < 1000
    )


def valid_probability(
    value: float,
) -> bool:

    return (
        0 < value <= 1
    )


def valid_stake(
    value: float,
) -> bool:

    return value > 0


# ---------------------------------------------------------
# Stake Helpers
# ---------------------------------------------------------

def equal_return_back_stake(
    target_return: float,
    odds: float,
) -> float:

    return (
        target_return / odds
    )


def return_from_back(
    odds: float,
    stake: float,
) -> float:

    return odds * stake


def winnings_from_back(
    odds: float,
    stake: float,
) -> float:

    return (
        odds - 1
    ) * stake


def net_exchange_winnings(
    odds: float,
    stake: float,
    commission_rate: float,
) -> float:

    gross = winnings_from_back(
        odds,
        stake,
    )

    net = gross - commission(
        gross,
        commission_rate,
    )

    return net


# ---------------------------------------------------------
# Result Object
# ---------------------------------------------------------

@dataclass(slots=True)
class CalculationResult:

    profitable: bool

    total_stake: float

    guaranteed_return: float

    guaranteed_profit: float

    roi: float

    arb_percentage: float

    notes: list[str]
    
# ---------------------------------------------------------
# Back/Lay Arbitrage
# ---------------------------------------------------------

def calculate_back_lay(
    back_odds: float,
    lay_odds: float,
    back_stake: float,
    commission_rate: float = 0.02,
) -> CalculationResult:
    """
    Calculate a traditional Back/Lay arbitrage.

    Returns equalised profit regardless of outcome.
    """

    if not valid_decimal(back_odds):
        raise ValueError("Invalid back odds.")

    if not valid_decimal(lay_odds):
        raise ValueError("Invalid lay odds.")

    if lay_odds <= 1:
        raise ValueError("Invalid lay odds.")

    if not valid_stake(back_stake):
        raise ValueError("Invalid stake.")

    # Equal profit lay stake
    lay_stake = (
        (back_odds * back_stake)
        / (
            lay_odds
            - commission_rate
        )
    )

    lay_liability = liability(
        lay_stake,
        lay_odds,
    )

    # Horse wins

    back_return = return_from_back(
        back_odds,
        back_stake,
    )

    back_profit = (
        back_return
        - back_stake
    )

    exchange_loss = lay_liability

    profit_if_win = (
        back_profit
        - exchange_loss
    )

    # Horse loses

    exchange_profit = (
        lay_stake
        - commission(
            lay_stake,
            commission_rate,
        )
    )

    profit_if_lose = (
        exchange_profit
        - back_stake
    )

    guaranteed_profit = min(
        profit_if_win,
        profit_if_lose,
    )

    total_stake = (
        back_stake
        + lay_liability
    )

    guaranteed_return = (
        total_stake
        + guaranteed_profit
    )

    roi = roi_percent(
        total_stake,
        guaranteed_profit,
    )

    implied = (
        decimal_to_probability(back_odds)
        +
        decimal_to_probability(lay_odds)
    )

    notes = []

    if guaranteed_profit > 0:
        notes.append(
            "Guaranteed profit."
        )
    else:
        notes.append(
            "No profitable arb."
        )

    if commission_rate > 0:
        notes.append(
            f"Exchange commission {commission_rate:.1%}"
        )

    return CalculationResult(
        profitable=(
            guaranteed_profit > 0
        ),
        total_stake=round(
            total_stake,
            2,
        ),
        guaranteed_return=round(
            guaranteed_return,
            2,
        ),
        guaranteed_profit=round(
            guaranteed_profit,
            2,
        ),
        roi=round(
            roi,
            3,
        ),
        arb_percentage=round(
            implied * 100,
            3,
        ),
        notes=notes,
    )


# ---------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------

def calculate_back_lay_roi(
    back_odds: float,
    lay_odds: float,
    stake: float = 100.0,
):
    return calculate_back_lay(
        back_odds=back_odds,
        lay_odds=lay_odds,
        back_stake=stake,
    )
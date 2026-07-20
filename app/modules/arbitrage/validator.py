from __future__ import annotations

from app.modules.arbitrage.models import (
    RaceMarket,
)


MIN_BOOKMAKERS = 2
MIN_RUNNERS = 2


def validate_market(
    market: RaceMarket,
):
    """
    Validates a RaceMarket before
    arbitrage calculations.
    """

    errors = []

    if market.runner_count < MIN_RUNNERS:
        errors.append(
            "Too few runners."
        )

    for runner in market.runners:

        if len(runner.prices) < MIN_BOOKMAKERS:
            errors.append(
                f"{runner.runner_name}: insufficient bookmaker prices."
            )

        for price in runner.prices:

            if (
                price.decimal_odds <= 1
            ):
                errors.append(
                    f"{runner.runner_name}: invalid odds."
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def market_quality_score(
    market: RaceMarket,
):
    """
    Simple quality score (0–100).
    """

    score = 100

    if market.runner_count < 5:
        score -= 25

    for runner in market.runners:

        if len(runner.prices) < 5:
            score -= 2

    return max(
        score,
        0,
    )
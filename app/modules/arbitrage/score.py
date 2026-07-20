from __future__ import annotations

from app.modules.arbitrage.models import ArbOpportunity


def calculate_pulse_arb_score(
    opportunity: ArbOpportunity,
) -> int:
    """
    Returns a Pulse Arb score from 0-100.

    The scoring model is intentionally modular so
    additional factors (liquidity, stability,
    market age, etc.) can be added later.
    """

    score = 0

    # ------------------------
    # ROI
    # ------------------------

    if opportunity.roi >= 5:
        score += 35
    elif opportunity.roi >= 3:
        score += 28
    elif opportunity.roi >= 2:
        score += 22
    elif opportunity.roi >= 1:
        score += 15
    else:
        score += 5

    # ------------------------
    # Profit
    # ------------------------

    if opportunity.guaranteed_profit >= 100:
        score += 25
    elif opportunity.guaranteed_profit >= 50:
        score += 20
    elif opportunity.guaranteed_profit >= 20:
        score += 15
    elif opportunity.guaranteed_profit >= 10:
        score += 10
    else:
        score += 5

    # ------------------------
    # Stability
    # ------------------------

    if opportunity.stable_seconds >= 300:
        score += 20
    elif opportunity.stable_seconds >= 120:
        score += 15
    elif opportunity.stable_seconds >= 60:
        score += 10
    else:
        score += 3

    # ------------------------
    # Seen Count
    # ------------------------

    if opportunity.seen_count >= 10:
        score += 10
    elif opportunity.seen_count >= 5:
        score += 7
    elif opportunity.seen_count >= 2:
        score += 5

    # ------------------------
    # Validation
    # ------------------------

    if opportunity.is_verified:
        score += 10

    return min(
        int(score),
        100,
    )


def star_rating(
    score: int,
) -> int:

    if score >= 95:
        return 5

    if score >= 80:
        return 4

    if score >= 65:
        return 3

    if score >= 45:
        return 2

    return 1


def score_band(
    score: int,
) -> str:

    if score >= 95:
        return "ELITE"

    if score >= 80:
        return "EXCELLENT"

    if score >= 65:
        return "GOOD"

    if score >= 45:
        return "FAIR"

    return "LOW"
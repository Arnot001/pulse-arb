from typing import Dict, Any, Optional


MIN_ARB_PERCENTAGE = 0.5


def has_valid_odds(back_odds: float, lay_odds: float) -> bool:
    """
    Basic sanity check for odds.
    """
    if back_odds <= 1:
        return False

    if lay_odds <= 1:
        return False

    return True


def passes_arb_threshold(arb_percentage: float) -> bool:
    """
    Checks if the arb percentage meets Pulse minimum threshold.
    """
    return arb_percentage >= MIN_ARB_PERCENTAGE


def is_sportsbook(bookmaker_name: str) -> bool:
    """
    Simple sportsbook filter.
    Expand later with exchange detection.
    """
    if not bookmaker_name:
        return False

    exchange_keywords = [
        "matchbook",
        "smarkets",
        "betfair exchange",
    ]

    bookmaker_lower = bookmaker_name.lower()

    for keyword in exchange_keywords:
        if keyword in bookmaker_lower:
            return False

    return True


def is_valid_arb_opportunity(opportunity: Dict[str, Any]) -> bool:
    """
    Main Pulse arb validation logic.
    """

    back_odds = opportunity.get("back_odds", 0)
    lay_odds = opportunity.get("lay_odds", 0)
    arb_percentage = opportunity.get("arb_percentage", 0)

    if not has_valid_odds(back_odds, lay_odds):
        return False

    if not passes_arb_threshold(arb_percentage):
        return False

    return True


def filter_opportunities(opportunities: list) -> list:
    """
    Filters a list of arb opportunities.
    """
    valid_opportunities = []

    for opportunity in opportunities:
        if is_valid_arb_opportunity(opportunity):
            valid_opportunities.append(opportunity)

    return valid_opportunities
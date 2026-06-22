from typing import Dict, Any, Optional


def implied_probability(odds: float) -> float:
    """
    Converts decimal odds into implied probability.
    Example: 2.00 = 50%
    """
    if odds <= 1:
        return 0.0

    return 1 / odds


def calculate_arb_percentage(back_odds: float, lay_odds: float) -> float:
    """
    Simple arb percentage estimate.
    Higher back odds vs lower lay odds = better opportunity.
    """
    if back_odds <= 1 or lay_odds <= 1:
        return 0.0

    back_prob = implied_probability(back_odds)
    lay_prob = implied_probability(lay_odds)

    edge = lay_prob - back_prob

    return round(edge * 100, 2)


def is_profitable_price_gap(back_odds: float, lay_odds: float) -> bool:
    """
    Basic check: back odds must be higher than lay odds.
    """
    return back_odds > lay_odds


def calculate_simple_stakes(
    total_stake: float,
    back_odds: float,
    lay_odds: float,
) -> Optional[Dict[str, Any]]:
    """
    Splits a total stake across back and lay sides.
    This is a simple version for early Pulse pricing logic.
    """
    if total_stake <= 0:
        return None

    if back_odds <= 1 or lay_odds <= 1:
        return None

    if not is_profitable_price_gap(back_odds, lay_odds):
        return None

    back_implied = implied_probability(back_odds)
    lay_implied = implied_probability(lay_odds)

    total_probability = back_implied + lay_implied

    if total_probability <= 0:
        return None

    back_stake = total_stake * (back_implied / total_probability)
    lay_stake = total_stake * (lay_implied / total_probability)

    back_return = back_stake * back_odds
    lay_return = lay_stake * lay_odds

    profit_if_back_wins = back_return - total_stake
    profit_if_lay_wins = lay_return - total_stake

    return {
        "back_stake": round(back_stake, 2),
        "lay_stake": round(lay_stake, 2),
        "back_return": round(back_return, 2),
        "lay_return": round(lay_return, 2),
        "profit_if_back_wins": round(profit_if_back_wins, 2),
        "profit_if_lay_wins": round(profit_if_lay_wins, 2),
        "arb_percentage": calculate_arb_percentage(back_odds, lay_odds),
    }


def build_pricing_summary(
    back_bookmaker: str,
    lay_bookmaker: str,
    selection: str,
    back_odds: float,
    lay_odds: float,
    total_stake: float = 100.0,
) -> Optional[Dict[str, Any]]:
    """
    Builds a clean pricing object that main.py or the UI can use.
    """
    stakes = calculate_simple_stakes(
        total_stake=total_stake,
        back_odds=back_odds,
        lay_odds=lay_odds,
    )

    if stakes is None:
        return None

    return {
        "selection": selection,
        "back_bookmaker": back_bookmaker,
        "lay_bookmaker": lay_bookmaker,
        "back_odds": back_odds,
        "lay_odds": lay_odds,
        **stakes,
    }


def calculate_arb_percentage_from_inverse(inv_sum: float) -> float:
    """
    Converts inverse odds sum into arb profit percentage.
    """
    if inv_sum <= 0:
        return 0.0

    return (1 / inv_sum - 1) * 100


def calculate_price_gaps(all_prices: dict) -> list:
    """
    Finds major bookmaker pricing gaps for each selection.
    """

    price_gaps = []

    for selection, prices in all_prices.items():

        if len(prices) < 2:
            continue

        best = max(prices, key=lambda x: x["odds"])
        worst = min(prices, key=lambda x: x["odds"])

        gap_percent = round(
            ((best["odds"] - worst["odds"]) / worst["odds"]) * 100,
            2,
        )

        if gap_percent >= 5:
            price_gaps.append({
                "selection": selection,
                "best_bookmaker": best["bookmaker"],
                "best_odds": best["odds"],
                "worst_bookmaker": worst["bookmaker"],
                "worst_odds": worst["odds"],
                "gap_percent": gap_percent,
            })

    return price_gaps


def build_arb_legs(
    outcomes: dict,
    bankroll: float,
    inv_sum: float,
) -> list:
    """
    Builds arb stake distribution legs.
    """

    legs = []

    for name, data in outcomes.items():

        stake = bankroll * (1 / data["odds"]) / inv_sum

        legs.append({
            "selection": name,
            "bookmaker": data["bookmaker"],
            "odds": data["odds"],
            "stake": round(stake, 2),
        })

    return legs
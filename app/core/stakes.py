def round_stake_naturally(stake: float) -> float:
    """
    Turns precise arb stakes into more natural-looking stakes.
    Example: 21.58 -> 22
    """
    if stake <= 0:
        return 0

    return round(stake)


def calculate_two_way_profit(back_odds, back_stake, lay_odds, lay_stake, lay_commission=0.02):
    """
    Simple back/lay profit check after rounded stakes.
    """
    back_win_profit = (back_odds - 1) * back_stake
    lay_loss = (lay_odds - 1) * lay_stake

    profit_if_back_wins = back_win_profit - lay_loss

    lay_win_profit = lay_stake * (1 - lay_commission)
    back_loss = back_stake

    profit_if_lay_wins = lay_win_profit - back_loss

    return round(profit_if_back_wins, 2), round(profit_if_lay_wins, 2)


def apply_natural_stakes(back_odds, exact_back_stake, lay_odds, exact_lay_stake, lay_commission=0.02):
    """
    Rounds stakes, recalculates profit, and checks if the arb is still profitable.
    """

    natural_back_stake = round_stake_naturally(exact_back_stake)
    natural_lay_stake = round_stake_naturally(exact_lay_stake)

    profit_back_wins, profit_lay_wins = calculate_two_way_profit(
        back_odds,
        natural_back_stake,
        lay_odds,
        natural_lay_stake,
        lay_commission
    )

    still_profitable = profit_back_wins > 0 and profit_lay_wins > 0

    return {
        "exact_back_stake": round(exact_back_stake, 2),
        "exact_lay_stake": round(exact_lay_stake, 2),
        "natural_back_stake": natural_back_stake,
        "natural_lay_stake": natural_lay_stake,
        "profit_if_back_wins": profit_back_wins,
        "profit_if_lay_wins": profit_lay_wins,
        "still_profitable": still_profitable,
        "stake_mode": "Natural",
    }
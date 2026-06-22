def calculate_lay_arb(
    back_odds,
    back_stake,
    lay_odds,
    commission=0.02,
):
    if back_odds <= 1 or lay_odds <= 1 or back_stake <= 0:
        return None

    lay_stake = (back_odds * back_stake) / (lay_odds - commission)
    liability = (lay_odds - 1) * lay_stake

    profit_if_back_wins = ((back_odds - 1) * back_stake) - liability
    profit_if_lay_wins = (lay_stake * (1 - commission)) - back_stake

    return {
        "lay_stake": round(lay_stake, 2),
        "liability": round(liability, 2),
        "profit_if_back_wins": round(profit_if_back_wins, 2),
        "profit_if_lay_wins": round(profit_if_lay_wins, 2),
    }
def calculate_stakes(bankroll: float, odds: list[float]) -> dict:
    total_inverse = sum(1 / odd for odd in odds)
    stakes = [bankroll * ((1 / odd) / total_inverse) for odd in odds]
    payouts = [stakes[i] * odds[i] for i in range(len(odds))]
    guaranteed_return = min(payouts)
    guaranteed_profit = guaranteed_return - bankroll
    return {
        'stakes': [round(x, 2) for x in stakes],
        'payouts': [round(x, 2) for x in payouts],
        'guaranteed_return': round(guaranteed_return, 2),
        'guaranteed_profit': round(guaranteed_profit, 2),
    }

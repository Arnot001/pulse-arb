def calculate_value_score(
    tipster_support,
    market_support,
    odds,
):
    score = 0

    score += tipster_support * 10
    score += market_support * 10

    if odds >= 8:
        score += 10

    if odds >= 15:
        score += 10

    return min(score, 100)


def is_dark_horse(
    odds,
    tipster_support,
):
    return (
        odds >= 10
        and tipster_support >= 2
    )
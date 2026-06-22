from datetime import datetime, timezone


def confidence_score(legs: list[dict], profit_percent: float, commence_time) -> dict:
    score = 100

    # Very high profit is often stale/bad data.
    if profit_percent > 10:
        score -= 25
    elif profit_percent > 6:
        score -= 10

    now = datetime.now(timezone.utc)
    hours_to_start = (commence_time - now).total_seconds() / 3600
    if hours_to_start < 0.25:
        score -= 30
    elif hours_to_start < 2:
        score -= 10

    oldest_age = 0
    for leg in legs:
        lu = leg.get('last_update')
        if lu:
            oldest_age = max(oldest_age, (now - lu).total_seconds())
    if oldest_age > 180:
        score -= 25
    elif oldest_age > 90:
        score -= 10

    score = max(0, min(100, score))
    if score >= 80:
        label = 'High'
    elif score >= 55:
        label = 'Medium'
    else:
        label = 'Low'
    return {'score': score, 'label': label, 'odds_age_seconds': round(oldest_age)}


def execution_difficulty(profit_percent: float, confidence_label: str, leg_count: int) -> str:
    if confidence_label == 'Low' or profit_percent > 10 or leg_count >= 3:
        return 'Hard'
    if confidence_label == 'Medium' or leg_count == 3:
        return 'Medium'
    return 'Easy'

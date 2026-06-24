def calculate_tipster_score(tipster_count=0, total_tipsters=0):
    if total_tipsters <= 0:
        return {
            "tipster_score": 0,
            "tipster_consensus": "NO DATA",
            "tipster_ratio": 0,
        }

    ratio = tipster_count / total_tipsters

    if ratio >= 0.75:
        score = 25
        label = "STRONG"
    elif ratio >= 0.5:
        score = 18
        label = "GOOD"
    elif ratio >= 0.25:
        score = 10
        label = "LIGHT"
    elif tipster_count > 0:
        score = 5
        label = "LOW"
    else:
        score = 0
        label = "NONE"

    return {
        "tipster_score": score,
        "tipster_consensus": label,
        "tipster_ratio": round(ratio, 2),
    }


def is_dark_horse_candidate(pulse_score, tipster_score, market_rank=None):
    if market_rank is None:
        return False

    return (
        pulse_score >= 70
        and tipster_score >= 10
        and market_rank >= 5
    )
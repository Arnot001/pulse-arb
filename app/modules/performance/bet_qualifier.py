UK_IRE_COURSES = {
    "Ayr",
    "Market Rasen",
    "Southwell (AW)",
}


def qualifies_as_official_bet(bet):
    pulse_score = bet.get("pulse_score") or 0
    best_odds_decimal = bet.get("best_odds_decimal") or 0
    course = bet.get("course")

    reasons = []
    warnings = []

    if course in UK_IRE_COURSES:
        reasons.append("UK/IRE supported course")
    else:
        warnings.append("Unsupported course for official tracking")

    if pulse_score >= 85:
        reasons.append("Strong Pulse score")
    else:
        warnings.append("Pulse score below official bet threshold")

    if 2.0 <= best_odds_decimal <= 12.0:
        reasons.append("Playable price")
    else:
        warnings.append("Price outside official range")

    qualifies = (
        course in UK_IRE_COURSES
        and pulse_score >= 85
        and 2.0 <= best_odds_decimal <= 12.0
    )

    return {
        "qualifies": qualifies,
        "bet_type": "OFFICIAL_PULSE_BET" if qualifies else "PREDICTION_ONLY",
        "reasons": reasons,
        "warnings": warnings,
    }
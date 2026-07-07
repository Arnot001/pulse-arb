def qualifies_as_official_bet(bet):
    pulse_score = bet.get("pulse_score") or 0
    best_odds_decimal = bet.get("best_odds_decimal") or 0

    reasons = []
    warnings = []

    if pulse_score >= 85:
        reasons.append("Strong Pulse score")
    else:
        warnings.append("Pulse score below official bet threshold")

    if 2.0 <= best_odds_decimal <= 12.0:
        reasons.append("Playable price")
    else:
        warnings.append("Price outside official range")

    qualifies = (
        pulse_score >= 85
        and 2.0 <= best_odds_decimal <= 12.0
    )

    return {
        "qualifies": qualifies,
        "bet_type": "OFFICIAL_PULSE_BET" if qualifies else "PREDICTION_ONLY",
        "reasons": reasons,
        "warnings": warnings,
    }
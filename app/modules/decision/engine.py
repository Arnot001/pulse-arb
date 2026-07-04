def build_daily_decision(
    bet_horses,
    portfolio_quality=0,
    recommended_reports=None,
):
    recommended_reports = recommended_reports or []

    elite = [
        h for h in bet_horses
        if h.get("recommendation_score", 0) >= 92
    ]

    strong = [
        h for h in bet_horses
        if h.get("recommendation_score", 0) >= 85
    ]

    avoid = [
        h for h in bet_horses
        if h.get("recommendation_score", 0) < 75
    ]

    warnings = []

    if len(avoid) >= 8:
        warnings.append("Several high-risk runners detected.")

    if portfolio_quality < 70:
        warnings.append("Portfolio spread is weaker than preferred.")

    if portfolio_quality >= 90 and len(elite) >= 2:
        play = "Balanced"
        confidence = "HIGH"
        recommendation = "Best Single + Pulse Double"
        reason = (
            "Pulse found strong selections while keeping portfolio exposure balanced."
        )

    elif len(elite) >= 3:
        play = "Positive"
        confidence = "HIGH"
        recommendation = "Smart Singles + Treble"
        reason = "Multiple elite selections found across today's races."

    elif len(elite) >= 2:
        play = "Selective"
        confidence = "HIGH"
        recommendation = "Pulse Double"
        reason = "Two elite selections stand out from the field."

    elif len(strong) >= 2:
        play = "Cautious"
        confidence = "MEDIUM"
        recommendation = "Smart Singles"
        reason = "Some strong runners found, but multiples should be treated carefully."

    else:
        play = "Pass"
        confidence = "LOW"
        recommendation = "Small Singles / No Bet"
        reason = "Pulse has not found enough strong edges today."

    return {
        "play": play,
        "confidence": confidence,
        "recommendation": recommendation,
        "reason": reason,
        "warnings": warnings,
        "elite_count": len(elite),
        "strong_count": len(strong),
        "avoid_count": len(avoid),
        "portfolio_quality": portfolio_quality,
    }
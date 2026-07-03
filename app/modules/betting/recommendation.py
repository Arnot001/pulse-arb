def build_recommendation(horse):
    score = horse.get("score", 0)
    notes = list(horse.get("notes", []))
    rec_score = score
    reasons = []

    if score >= 95:
        rec_score += 6
        reasons.append("Elite IQ profile")
    elif score >= 90:
        rec_score += 4
        reasons.append("Very strong IQ profile")
    elif score >= 85:
        rec_score += 2
        reasons.append("Strong IQ profile")

    if score < 70:
        rec_score -= 8
        reasons.append("Below preferred betting threshold")

    if any("Strong recent form" in note for note in notes):
        rec_score += 4
        reasons.append("Strong recent form")

    if any("Trainer bonus" in note for note in notes):
        rec_score += 3
        reasons.append("Trainer positive")

    if any("Jockey bonus" in note for note in notes):
        rec_score += 3
        reasons.append("Jockey positive")

    if any("Weak recent form" in note for note in notes):
        rec_score -= 5
        reasons.append("Weak recent form concern")

    rec_score = max(0, min(100, round(rec_score)))

    if rec_score >= 92:
        risk = "LOW"
        stars = "★★★★★"
    elif rec_score >= 85:
        risk = "MEDIUM"
        stars = "★★★★☆"
    elif rec_score >= 75:
        risk = "MEDIUM-HIGH"
        stars = "★★★☆☆"
    else:
        risk = "HIGH"
        stars = "★★☆☆☆"

    return {
        **horse,
        "recommendation_score": rec_score,
        "recommendation_reasons": reasons,
        "risk": risk,
        "stars": stars,
    }
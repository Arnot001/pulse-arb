from app.modules.horses.output import get_top_horses, get_race_groups


def get_score_profile(score):
    if score >= 92:
        return {
            "confidence": "DOMINANT",
            "confidence_colour": "green",
            "score_class": "iq-elite",
        }

    if score >= 85:
        return {
            "confidence": "STRONG",
            "confidence_colour": "pink",
            "score_class": "iq-strong",
        }

    if score >= 75:
        return {
            "confidence": "GOOD VALUE",
            "confidence_colour": "blue",
            "score_class": "iq-good",
        }

    return {
        "confidence": "COMPETITIVE",
        "confidence_colour": "grey",
        "score_class": "iq-standard",
    }


def get_horse_dashboard():
    cards = []

    for index, horse in enumerate(get_top_horses(50), start=1):
        score = horse.get("pulse_score", 0)
        profile = get_score_profile(score)

        cards.append({
            "rank": index,
            "score": score,
            "score_class": profile["score_class"],
            "horse": horse.get("horse"),
            "course": horse.get("course"),
            "time": horse.get("off_time"),
            "form": horse.get("form"),
            "notes": horse.get("notes", []),
            "confidence": profile["confidence"],
            "confidence_colour": profile["confidence_colour"],
            "win_chance": (
                "Very High" if score >= 92 else
                "High" if score >= 85 else
                "Good" if score >= 75 else
                "Competitive"
            ),

            "place_chance": (
                "Excellent" if score >= 92 else
                "Strong" if score >= 85 else
                "Solid" if score >= 75 else
                "Average"
            ),

            "market_signal": (
                "Bullish" if score >= 92 else
                "Positive" if score >= 85 else
                "Stable" if score >= 75 else
                "Neutral"
            ),
            "strategy_flags": [],
            "warnings": [],
        })

    return cards


def get_horse_race_groups():
    return get_race_groups()
from app.modules.horses.output import get_top_horses
from app.modules.betting.recommendation import build_recommendation


def build_verdict(bet_horses):
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

    if len(elite) >= 3:
        confidence = "HIGH"
        strategy = "Pulse Treble"
        verdict = "Strong betting day. Multiple elite selections found."
    elif len(elite) >= 2:
        confidence = "HIGH"
        strategy = "Pulse Double"
        verdict = "Good betting day. A strong double is available."
    elif len(strong) >= 2:
        confidence = "MEDIUM"
        strategy = "Smart Singles"
        verdict = "Selective betting advised. Singles look safer than multiples."
    else:
        confidence = "LOW"
        strategy = "Pass / Small Singles"
        verdict = "Caution advised. No strong multiple detected."

    return {
        "confidence": confidence,
        "strategy": strategy,
        "verdict": verdict,
        "elite_count": len(elite),
        "strong_count": len(strong),
        "avoid_count": len(avoid),
    }


def build_bets():
    horses = list(get_top_horses(50))

    def to_bet_horse(horse):
        return {
            "horse": horse.get("horse"),
            "course": horse.get("course"),
            "time": horse.get("off_time"),
            "race_name": horse.get("race_name"),
            "race_id": horse.get("race_id"),
            "score": horse.get("pulse_score", 0),
            "form": horse.get("form"),
            "notes": horse.get("notes", []),
        }

    bet_horses = [
        build_recommendation(to_bet_horse(horse))
        for horse in horses
    ]

    bet_horses = sorted(
        bet_horses,
        key=lambda h: h.get("recommendation_score", 0),
        reverse=True,
    )

    return {
        "verdict": build_verdict(bet_horses),
        "smart_singles": bet_horses[:5],
        "pulse_double": bet_horses[:2],
        "pulse_treble": bet_horses[:3],
        "dominant_double": [
            h for h in bet_horses
            if h.get("recommendation_score", 0) >= 90
        ][:2],
        "dominant_treble": [
            h for h in bet_horses
            if h.get("recommendation_score", 0) >= 90
        ][:3],
        "avoid_bets": [
            h for h in bet_horses
            if h.get("recommendation_score", 0) < 75
        ][:8],
    }
from app.modules.performance.live_tracker import load_live_status
from app.modules.odds.url_builder import build_oddschecker_url
from app.modules.horses.output import get_top_horses
from app.modules.betting.recommendation import build_recommendation
from app.modules.betting.portfolio import PortfolioBuilder
from app.modules.decision.engine import build_daily_decision


SUPPORTED_COURSES = {
    "Ayr",
    "Market Rasen",
    "Southwell (AW)",
}


def risk_rank(risk):
    ranks = {
        "LOW": 1,
        "MEDIUM": 2,
        "MEDIUM-HIGH": 3,
        "HIGH": 4,
    }

    return ranks.get(risk, 4)


def build_bet_report(title, bet_type, horses):
    horses = list(horses)

    if not horses:
        return {
            "title": title,
            "type": bet_type,
            "horses": [],
            "confidence": 0,
            "ai_rating": "☆☆☆☆☆",
            "combined_iq": 0,
            "combined_recommendation": 0,
            "combined_risk": "NONE",
            "expected_strike_rate": 0,
            "strategy": "No Bet",
            "reasons": [],
            "verdict": "No qualifying selections found.",
            "tracker_status": "NO BET",
            "settled_count": 0,
            "selection_count": 0,
            "winners": 0,
            "profit": 0,
            "roi": 0,
        }

    combined_iq = sum(h.get("score", 0) for h in horses)
    avg_rec = round(
        sum(h.get("recommendation_score", 0) for h in horses) / len(horses)
    )

    worst_risk = max(
        horses,
        key=lambda h: risk_rank(h.get("risk")),
    ).get("risk", "HIGH")

    unique_races = len(set(h.get("race_id") for h in horses if h.get("race_id")))
    unique_courses = len(set(h.get("course") for h in horses if h.get("course")))

    reasons = []

    if avg_rec >= 92:
        reasons.append("Elite recommendation profile")
    elif avg_rec >= 85:
        reasons.append("Strong recommendation profile")

    if len(horses) == 1:
        reasons.append("Single selection")
    elif unique_races == len(horses):
        reasons.append("Selections are from different races")
    else:
        reasons.append("Warning: selections may share a race")

    if unique_courses > 1:
        reasons.append("Selections spread across different meetings")

    if all(h.get("risk") == "LOW" for h in horses):
        reasons.append("Low combined risk profile")

    if any(
        "Strong recent form" in " ".join(h.get("recommendation_reasons", []))
        for h in horses
    ):
        reasons.append("Strong recent form signal")

    if any("Trainer positive" in h.get("recommendation_reasons", []) for h in horses):
        reasons.append("Trainer confidence signal")

    if any("Jockey positive" in h.get("recommendation_reasons", []) for h in horses):
        reasons.append("Jockey confidence signal")

    confidence = avg_rec

    if unique_races < len(horses):
        confidence -= 12

    if worst_risk == "MEDIUM-HIGH":
        confidence -= 6
    elif worst_risk == "HIGH":
        confidence -= 12

    confidence = max(0, min(100, confidence))

    if confidence >= 92:
        ai_rating = "★★★★★"
    elif confidence >= 85:
        ai_rating = "★★★★☆"
    elif confidence >= 75:
        ai_rating = "★★★☆☆"
    elif confidence >= 65:
        ai_rating = "★★☆☆☆"
    else:
        ai_rating = "★☆☆☆☆"

    if bet_type == "single":
        expected_strike_rate = min(75, round(confidence * 0.62))
        strategy = "Smart Single"
    elif bet_type == "double":
        expected_strike_rate = min(62, round(confidence * 0.52))
        strategy = "Pulse Double"
    elif bet_type == "treble":
        expected_strike_rate = min(48, round(confidence * 0.42))
        strategy = "Pulse Treble"
    else:
        expected_strike_rate = min(50, round(confidence * 0.45))
        strategy = "Pulse Strategy"

    if confidence >= 90:
        verdict = (
            f"{title} is strongly recommended by Pulse based on elite "
            f"recommendation scores and a favourable risk profile."
        )
    elif confidence >= 80:
        verdict = (
            f"{title} is playable, but should be treated as a selective "
            f"opportunity rather than a banker."
        )
    else:
        verdict = f"{title} carries elevated uncertainty. Review before placing."

    settled = [
        h for h in horses
        if h.get("status") == "SETTLED"
    ]

    won = [
        h for h in settled
        if h.get("profit", 0) > 0
    ]

    total_profit = round(
        sum(h.get("profit") or 0 for h in settled),
        2,
    )

    total_stake = len(settled)

    roi = 0
    if total_stake:
        roi = round((total_profit / total_stake) * 100, 2)

    if not settled:
        tracker_status = "WAITING"
    elif len(settled) < len(horses):
        tracker_status = "IN PROGRESS"
    else:
        tracker_status = "COMPLETE"

    return {
        "title": title,
        "type": bet_type,
        "horses": horses,
        "confidence": confidence,
        "ai_rating": ai_rating,
        "combined_iq": combined_iq,
        "combined_recommendation": avg_rec,
        "combined_risk": worst_risk,
        "expected_strike_rate": expected_strike_rate,
        "strategy": strategy,
        "reasons": reasons,
        "verdict": verdict,
        "tracker_status": tracker_status,
        "settled_count": len(settled),
        "selection_count": len(horses),
        "winners": len(won),
        "profit": total_profit,
        "roi": roi,
    }


def build_verdict(bet_horses, portfolio_quality=0):
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

    if portfolio_quality >= 90 and len(elite) >= 2:
        confidence = "HIGH"
        strategy = "Balanced Portfolio"
        verdict = "Good betting day. Pulse has found strong picks without overloading one horse."
    elif len(elite) >= 3:
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
        "portfolio_quality": portfolio_quality,
    }


def build_bets():
    horses = list(get_top_horses(50))
    live_status = load_live_status()

    def to_bet_horse(horse):
        course = horse.get("course")
        race_time = horse.get("off_time")
        horse_name = horse.get("horse")

        key = (
            str(horse_name or "").lower().strip(),
            str(course or "").lower().strip(),
            str(race_time or "").strip(),
        )

        status = live_status.get(key, {})

        return {
            "horse": horse_name,
            "course": course,
            "time": race_time,
            "race_name": horse.get("race_name"),
            "race_id": horse.get("race_id"),
            "score": horse.get("pulse_score", 0),
            "form": horse.get("form"),
            "notes": horse.get("notes", []),
            "odds_url": build_oddschecker_url(
                course=course,
                race_time=race_time,
                horse=horse_name,
            ),
            "status": status.get("status", "WAITING"),
            "position": status.get("position"),
            "sp": status.get("sp"),
            "returned": status.get("returned"),
            "profit": status.get("profit"),
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

    qualified_bet_horses = [
        h for h in bet_horses
        if h.get("course") in SUPPORTED_COURSES
        and h.get("score", 0) >= 85
    ]

    portfolio = PortfolioBuilder(qualified_bet_horses)
    portfolio_data = portfolio.build_portfolio()

    best_single = portfolio_data["best_single"]
    smart_singles = portfolio_data["safe_singles"]
    pulse_double = portfolio_data["best_double"]
    pulse_treble = portfolio_data["best_treble"]
    dominant_double = portfolio_data["dominant_double"]
    dominant_treble = []

    avoid_bets = [
        h for h in bet_horses
        if h.get("recommendation_score", 0) < 75
    ][:8]

    portfolio_quality = portfolio_data["portfolio_quality"]

    bet_reports = []

    if len(best_single) >= 1:
        bet_reports.append(build_bet_report("Best Single", "single", best_single))

    if len(smart_singles) >= 2:
        bet_reports.append(build_bet_report("Smart Singles", "single", smart_singles))

    if len(pulse_double) >= 2:
        bet_reports.append(build_bet_report("Pulse Double", "double", pulse_double))

    if len(pulse_treble) >= 3:
        bet_reports.append(build_bet_report("Pulse Treble", "treble", pulse_treble))

    if len(dominant_double) >= 2:
        bet_reports.append(build_bet_report("Dominant Double", "double", dominant_double))

    decision = build_daily_decision(
        bet_horses=qualified_bet_horses,
        portfolio_quality=portfolio_quality,
        recommended_reports=bet_reports,
    )

    return {
        "decision": decision,
        "verdict": build_verdict(
            qualified_bet_horses,
            portfolio_quality=portfolio_quality,
        ),
        "bet_reports": bet_reports,
        "best_single": best_single,
        "smart_singles": smart_singles,
        "pulse_double": pulse_double,
        "pulse_treble": pulse_treble,
        "dominant_double": dominant_double,
        "dominant_treble": dominant_treble,
        "portfolio_quality": portfolio_quality,
        "exposure": portfolio_data["exposure"],
        "avoid_bets": avoid_bets,
    }
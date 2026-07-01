from app.modules.strategy.trends import analyse_strategy_trends


def recommendation_score(strategy):
    score = strategy.get("current_trust", 0)

    trend = strategy.get("trend")

    if trend == "IMPROVING_FAST":
        score += 15
    elif trend == "IMPROVING":
        score += 8
    elif trend == "DECLINING":
        score -= 10
    elif trend == "DECLINING_FAST":
        score -= 20

    status = strategy.get("current_status")

    if status == "ELITE":
        score += 20
    elif status == "VERIFIED":
        score += 12
    elif status == "TESTING":
        score += 5
    elif status == "RETIRED":
        score -= 50

    return round(score, 1)


def recommendation_label(score):
    if score >= 90:
        return "★★★★★ STRONG BUY"

    if score >= 75:
        return "★★★★ USE"

    if score >= 60:
        return "★★★ WATCH"

    if score >= 40:
        return "★★ MONITOR"

    return "★ AVOID"


def build_recommendations():
    recommendations = []

    for strategy in analyse_strategy_trends():
        score = recommendation_score(strategy)

        recommendations.append({
            **strategy,
            "recommendation_score": score,
            "recommendation": recommendation_label(score),
        })

    recommendations.sort(
        key=lambda item: item["recommendation_score"],
        reverse=True,
    )

    return recommendations


if __name__ == "__main__":
    for item in build_recommendations():
        print(
            f"{item['name']} | "
            f"{item['recommendation']} | "
            f"Score {item['recommendation_score']}"
        )
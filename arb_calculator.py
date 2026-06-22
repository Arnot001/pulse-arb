def find_arbitrage(bookmakers: list) -> dict | None:
    if not bookmakers:
        return None

    outcomes = {}
    for bm in bookmakers:
        for outcome in bm.get("outcomes", []):
            name = outcome["name"]
            odds = outcome["price"]
            if name not in outcomes or odds > outcomes[name]["odds"]:
                outcomes[name] = {"odds": odds, "book": bm["key"]}

    if len(outcomes) < 2:
        return None

    inv_sum = sum(1 / o["odds"] for o in outcomes.values())
    if inv_sum >= 1.0:
        return None

    profit = (1 / inv_sum - 1) * 100
    if profit < 1.0:
        return None

    total_stake = 100.0
    stakes = {}
    for name, data in outcomes.items():
        stakes[data["book"]] = round(total_stake * (1 / data["odds"]) / inv_sum, 2)

    return {
        "best_odds": {name: data["odds"] for name, data in outcomes.items()},
        "profit_percent": round(profit, 2),
        "suggested_stakes": stakes,
        "books": list({data["book"] for data in outcomes.values()})
    }


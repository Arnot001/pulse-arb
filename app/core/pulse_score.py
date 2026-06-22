def calculate_pulse_score(item, profit):
    score = 40
    reasons = []

    # Profit should drive the score
    if profit > 0:
        reasons.append("Positive arb detected")

        if profit >= 10:
            score = 95
            reasons.append("Elite profit margin")
        elif profit >= 7:
            score = 88
            reasons.append("Very strong profit margin")
        elif profit >= 5:
            score = 80
            reasons.append("High value opportunity")
        elif profit >= 3:
            score = 72
            reasons.append("Strong profit margin")
        elif profit >= 1:
            score = 62
            reasons.append("Good profit margin")
        else:
            score = 52
            reasons.append("Small positive edge")

    else:
        # Near-arb scoring
        score = 45

        if profit >= -1:
            score = 44
            reasons.append("Close near-arb")
        elif profit >= -3:
            score = 34
            reasons.append("Near-arb")
        else:
            score = 24
            reasons.append("Weak near-arb")

    # Same-book should never be treated as a real opportunity
    if item.get("same_book_market"):
        score -= 30
        reasons.append("Same-book price gap only")

    # Exchange involvement is execution context, not a score killer
    if item.get("exchange_arb") or item.get("contains_exchange"):
        score -= 3
        reasons.append("Exchange involved")

    # 3-way markets are more complex, but not bad
    if len(item.get("legs", [])) >= 3:
        score -= 4
        reasons.append("3-way market complexity")

    # Large gaps can be useful, but may indicate stale pricing
    large_gap_count = 0

    for gap in item.get("price_gaps", []):
        gap_percent = gap.get("gap_percent", 0)

        if gap_percent > 50:
            large_gap_count += 1

    if large_gap_count:
        score -= min(20, large_gap_count * 10)
        reasons.append("Extreme pricing gap detected")
        reasons.append("Possible stale or low-liquidity price")

    # Stability bonus
    stable_seconds = item.get("stable_seconds", 0)

    if stable_seconds >= 60:
        score += 5
        reasons.append("Strong stable window")
    elif stable_seconds >= 30:
        score += 3
        reasons.append("Stable opportunity")

    score = max(1, min(99, round(score)))

    return score, reasons
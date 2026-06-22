def detect_stable_window(item, profit):
    status = "UNSTABLE"

    if profit > 2:
        status = "GOOD"

    if profit > 5:
        status = "STRONG"

    if item.get("exchange_arb"):
        status = "REVIEW"

    return status
def calculate_execution(item, profit):
    status = "STABLE"

    if item.get("exchange_arb"):
        status = "REVIEW"

    if profit < 0:
        status = "VOLATILE"

    if len(item.get("legs", [])) > 2:
        status = "COMPLEX"

    return status
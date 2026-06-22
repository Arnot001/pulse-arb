import logging
from datetime import datetime, timezone


STABILITY_TRACKER = {}


def build_execution_status(
    profit_percent,
    contains_exchange=False,
    stable_seconds=0,
):
    status = "STILL PROFITABLE" if profit_percent > 0 else "WATCHING"

    if contains_exchange:
        pulse_state = "EXCHANGE REVIEW"
        execution_stability = "REVIEW"
        stability_score = 60

    elif stable_seconds >= 60 and profit_percent >= 2:
        pulse_state = "STRONG PULSE"
        execution_stability = "STRONG"
        stability_score = 95

    elif stable_seconds >= 30 and profit_percent >= 1:
        pulse_state = "STABLE PULSE"
        execution_stability = "STABLE"
        stability_score = 85

    elif profit_percent >= 1:
        pulse_state = "TRACKING"
        execution_stability = "REVIEW"
        stability_score = 65

    elif profit_percent >= 0:
        pulse_state = "WEAK PULSE"
        execution_stability = "LOW"
        stability_score = 50

    else:
        pulse_state = "NEAR PULSE"
        execution_stability = "WATCHLIST"
        stability_score = 40

    if profit_percent >= 10 and stable_seconds < 30:
        pulse_state = "HIGH PROFIT REVIEW"
        execution_stability = "REVIEW"
        stability_score = min(stability_score, 70)

    return {
        "pulse_state": pulse_state,
        "execution_stability": execution_stability,
        "stability_score": stability_score,
        "execution_status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def build_market_key(item):
    legs = item.get("legs", [])

    leg_identity = "|".join(
        sorted(
            f"{leg.get('selection')}:{leg.get('bookmaker')}"
            for leg in legs
        )
    )

    return f"{item.get('sport')}::{item.get('event')}::{leg_identity}"


def update_stability_tracking(item):
    now = datetime.now(timezone.utc)

    market_key = build_market_key(item)

    if market_key not in STABILITY_TRACKER:
        STABILITY_TRACKER[market_key] = {
            "first_seen": now,
            "last_seen": now,
            "seen_count": 1,
        }
    else:
        STABILITY_TRACKER[market_key]["last_seen"] = now
        STABILITY_TRACKER[market_key]["seen_count"] += 1

    tracker = STABILITY_TRACKER[market_key]

    stable_seconds = int(
        (tracker["last_seen"] - tracker["first_seen"]).total_seconds()
    )

    item["stability_tracking"] = {
        "market_key": market_key,
        "seen_count": tracker["seen_count"],
        "stable_seconds": stable_seconds,
        "is_stable_pulse": stable_seconds >= 30,
    }

    logging.info(
        "STABILITY | seen=%s | seconds=%s | key=%s",
        tracker["seen_count"],
        stable_seconds,
        market_key[:120],
    )

    return item
import json
import re
from datetime import datetime, timezone
from pathlib import Path


VERIFIED_STRATEGY_FILE = Path("data/strategy/verified_strategies.json")


def strategy_id(name):
    text = str(name or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def get_lifecycle_status(sample, trust_score, top_pick_rate, top_3_rate):
    if sample >= 1000 and trust_score >= 85 and top_pick_rate >= 45 and top_3_rate >= 75:
        return "ELITE"

    if sample >= 300 and trust_score >= 75 and top_pick_rate >= 40 and top_3_rate >= 70:
        return "VERIFIED"

    if sample >= 50 and trust_score >= 60 and top_3_rate >= 60:
        return "TESTING"

    if sample >= 20 and trust_score < 15:
        return "RETIRED"

    if sample >= 50 and top_3_rate < 45:
        return "RETIRED"

    return "EXPERIMENTAL"


def get_lifecycle_reason(status):
    reasons = {
        "ELITE": "Large sample with strong long-term evidence.",
        "VERIFIED": "Strong evidence across a meaningful sample.",
        "TESTING": "Promising but needs more data.",
        "EXPERIMENTAL": "Early-stage strategy still collecting evidence.",
        "RETIRED": "Weak evidence or poor reliability.",
    }

    return reasons.get(status, "No lifecycle reason available.")


def get_trust_score(sample, top_pick_rate, top_3_rate):
    """
    Weighted trust model v3.

    Trust is based on:
    - sample size
    - top pick strength
    - top 3 reliability
    - consistency
    - early-stage caution
    - weakness penalties
    """

    sample_score = min(sample / 300, 1) * 35
    top_pick_score = min(top_pick_rate / 55, 1) * 25
    top_3_score = min(top_3_rate / 85, 1) * 30

    consistency_score = 0

    if top_pick_rate >= 50 and top_3_rate >= 75:
        consistency_score += 10
    elif top_pick_rate >= 40 and top_3_rate >= 65:
        consistency_score += 6
    elif top_3_rate >= 60:
        consistency_score += 3

    trust_score = sample_score + top_pick_score + top_3_score + consistency_score

    if sample < 10:
        trust_score *= 0.45
    elif sample < 25:
        trust_score *= 0.70
    elif sample < 50:
        trust_score *= 0.85

    if top_pick_rate <= 0:
        trust_score *= 0.25

    if top_3_rate < 50:
        trust_score *= 0.50

    return round(min(trust_score, 100), 1)


def verify_discovery(discovery):
    sample = discovery.get("sample", 0)
    top_pick_rate = discovery.get("top_pick_rate", 0)
    top_3_rate = discovery.get("top_3_rate", 0)

    trust_score = get_trust_score(sample, top_pick_rate, top_3_rate)

    lifecycle_status = get_lifecycle_status(
        sample,
        trust_score,
        top_pick_rate,
        top_3_rate,
    )

    verified = dict(discovery)
    verified["strategy_id"] = strategy_id(discovery.get("name"))
    verified["trust_score"] = trust_score
    verified["lifecycle_status"] = lifecycle_status
    verified["lifecycle_reason"] = get_lifecycle_reason(lifecycle_status)
    verified["verified_at"] = datetime.now(timezone.utc).isoformat()

    return verified


def verify_discoveries(discoveries):
    verified = [
        verify_discovery(discovery)
        for discovery in discoveries
    ]

    verified.sort(
        key=lambda item: (
            item.get("lifecycle_status") != "RETIRED",
            item.get("trust_score", 0),
            item.get("sample", 0),
        ),
        reverse=True,
    )

    return verified


def save_verified_strategies(strategies):
    VERIFIED_STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)

    with VERIFIED_STRATEGY_FILE.open("w", encoding="utf-8") as f:
        json.dump(strategies, f, indent=2, ensure_ascii=False)

    return VERIFIED_STRATEGY_FILE


def load_verified_strategies():
    if not VERIFIED_STRATEGY_FILE.exists():
        return []

    try:
        with VERIFIED_STRATEGY_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
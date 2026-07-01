from app.modules.strategy.engine import percent


CONFIDENCE_ORDER = {
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "TINY SAMPLE": 1,
}


def confidence_label(sample_size, hit_rate):
    if sample_size >= 100 and hit_rate >= 70:
        return "HIGH"
    if sample_size >= 40 and hit_rate >= 60:
        return "MEDIUM"
    if sample_size >= 10:
        return "LOW"
    return "TINY SAMPLE"


def make_discovery(name, description, reviews, category="General"):
    sample = len(reviews)

    top_pick_wins = sum(
        1 for r in reviews
        if r.get("winner_rank") == 1
    )

    top_3_hits = sum(
        1 for r in reviews
        if r.get("winner_rank") and r.get("winner_rank") <= 3
    )

    top_pick_rate = percent(top_pick_wins, sample)
    top_3_rate = percent(top_3_hits, sample)
    confidence = confidence_label(sample, top_3_rate)

    return {
        "category": category,
        "name": name,
        "description": description,
        "sample": sample,
        "top_pick_wins": top_pick_wins,
        "top_pick_rate": top_pick_rate,
        "top_3_hits": top_3_hits,
        "top_3_rate": top_3_rate,
        "confidence": confidence,
        "confidence_score": CONFIDENCE_ORDER.get(confidence, 0),
    }
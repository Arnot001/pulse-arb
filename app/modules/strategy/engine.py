import json
from pathlib import Path


RACE_REVIEW_DIR = Path("data/horses/race_reviews")


def load_race_reviews():
    reviews = []

    if not RACE_REVIEW_DIR.exists():
        return reviews

    for file in RACE_REVIEW_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                reviews.append(json.load(f))
        except Exception:
            continue

    return reviews


def percent(value, total):
    if not total:
        return 0

    return round((value / total) * 100, 1)


def get_strategy_lab_data():
    reviews = load_race_reviews()

    total_races = len(reviews)

    top_pick_wins = sum(
        1 for r in reviews
        if r.get("winner_rank") == 1
    )

    top_2_hits = sum(
        1 for r in reviews
        if r.get("winner_rank") and r.get("winner_rank") <= 2
    )

    top_3_hits = sum(
        1 for r in reviews
        if r.get("winner_rank") and r.get("winner_rank") <= 3
    )

    top_5_hits = sum(
        1 for r in reviews
        if r.get("winner_rank") and r.get("winner_rank") <= 5
    )

    misses = [
        r for r in reviews
        if not r.get("winner_rank") or r.get("winner_rank") > 3
    ]

    strategies = [
        {
            "name": "Top Pick Win",
            "description": "Back Pulse rank #1 in every reviewed race.",
            "races": total_races,
            "hits": top_pick_wins,
            "hit_rate": percent(top_pick_wins, total_races),
        },
        {
            "name": "Top 2 Coverage",
            "description": "Winner appeared inside Pulse top 2.",
            "races": total_races,
            "hits": top_2_hits,
            "hit_rate": percent(top_2_hits, total_races),
        },
        {
            "name": "Top 3 Coverage",
            "description": "Winner appeared inside Pulse top 3.",
            "races": total_races,
            "hits": top_3_hits,
            "hit_rate": percent(top_3_hits, total_races),
        },
        {
            "name": "Top 5 Safety Net",
            "description": "Winner appeared inside Pulse top 5.",
            "races": total_races,
            "hits": top_5_hits,
            "hit_rate": percent(top_5_hits, total_races),
        },
    ]

    best_strategy = max(
        strategies,
        key=lambda s: s["hit_rate"],
    ) if strategies else None

    return {
        "total_races": total_races,
        "strategies": strategies,
        "best_strategy": best_strategy,
        "misses": misses[:10],
    }
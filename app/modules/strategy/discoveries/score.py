from app.modules.strategy.discoveries.common import make_discovery


def score_discoveries(reviews):
    return [
        make_discovery(
            "All Reviewed Races",
            "Baseline across every race review.",
            reviews,
            category="Baseline",
        ),
        make_discovery(
            "Top Pick Score 70+",
            "Races where Pulse top pick scored 70 or higher.",
            [r for r in reviews if (r.get("top_pick_score") or 0) >= 70],
            category="Score",
        ),
        make_discovery(
            "Top Pick Score 80+",
            "Races where Pulse top pick scored 80 or higher.",
            [r for r in reviews if (r.get("top_pick_score") or 0) >= 80],
            category="Score",
        ),
        make_discovery(
            "Top Pick Score 90+",
            "Races where Pulse top pick scored 90 or higher.",
            [r for r in reviews if (r.get("top_pick_score") or 0) >= 90],
            category="Score",
        ),
        make_discovery(
            "Near Misses",
            "Races where winner was ranked 4th or 5th.",
            [r for r in reviews if r.get("winner_rank") in (4, 5)],
            category="Review",
        ),
    ]
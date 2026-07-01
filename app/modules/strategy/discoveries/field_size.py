from app.modules.strategy.discoveries.common import make_discovery


def field_size_discoveries(reviews):
    return [
        make_discovery(
            "Small Fields",
            "Races with 7 or fewer runners where field size is known.",
            [r for r in reviews if 0 < (r.get("field_size") or 0) <= 7],
            category="Field Size",
        ),
        make_discovery(
            "Medium Fields",
            "Races with 8 to 11 runners where field size is known.",
            [r for r in reviews if 8 <= (r.get("field_size") or 0) <= 11],
            category="Field Size",
        ),
        make_discovery(
            "Large Fields",
            "Races with 12 or more runners where field size is known.",
            [r for r in reviews if (r.get("field_size") or 0) >= 12],
            category="Field Size",
        ),
    ]
from app.modules.horses.data import get_demo_horses
from app.modules.horses.models import HorseSelection
from app.modules.horses.scoring import (
    calculate_value_score,
    is_dark_horse,
)
from app.modules.horses.output import build_horse_card


def get_horse_dashboard():
    cards = []

    for row in get_demo_horses():
        value_score = calculate_value_score(
            tipster_support=row["tipster_support"],
            market_support=row["market_support"],
            odds=row["odds"],
        )

        selection = HorseSelection(
            race_time=row["race_time"],
            race_name=row["race_name"],
            horse=row["horse"],
            odds=row["odds"],
            tipster_support=row["tipster_support"],
            market_support=row["market_support"],
            value_score=value_score,
            each_way=row["odds"] >= 8,
            dark_horse=is_dark_horse(
                odds=row["odds"],
                tipster_support=row["tipster_support"],
            ),
        )

        cards.append(build_horse_card(selection))

    return cards
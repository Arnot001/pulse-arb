def build_horse_card(selection):
    return {
        "race_time": selection.race_time,
        "race_name": selection.race_name,
        "horse": selection.horse,
        "odds": selection.odds,
        "value_score": selection.value_score,
        "each_way": selection.each_way,
        "dark_horse": selection.dark_horse,
    }
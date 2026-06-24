def score_race_class(race_class):
    if not race_class:
        return 0

    text = str(race_class).lower()

    if "class 1" in text:
        return 8
    if "class 2" in text:
        return 6
    if "class 3" in text:
        return 4
    if "class 4" in text:
        return 2

    return 0
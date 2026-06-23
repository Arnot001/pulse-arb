from app.modules.horses.output import get_top_horses, get_race_groups


def get_horse_dashboard():
    cards = []

    for horse in get_top_horses(50):
        cards.append({
            "score": horse.get("pulse_score"),
            "horse": horse.get("horse"),
            "course": horse.get("course"),
            "time": horse.get("off_time"),
            "form": horse.get("form"),
            "notes": horse.get("notes", []),
        })

    return cards


def get_horse_race_groups():
    return get_race_groups()
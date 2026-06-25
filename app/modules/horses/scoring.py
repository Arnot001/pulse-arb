from app.modules.horses.history_stats import get_horse_history
from app.modules.horses.tipster_support import get_tipster_boost
from app.modules.horses.trainer_lookup import get_trainer_bonus
from app.modules.horses.jockey_lookup import get_jockey_bonus
from app.modules.horses.class_score import score_race_class
from app.modules.horses.value import value_rating
from app.utils import to_int


def score_form(form):
    if not form:
        return 0

    score = 0
    recent = str(form).replace("-", "")[-4:]

    for char in recent:
        if char == "1":
            score += 10
        elif char == "2":
            score += 7
        elif char == "3":
            score += 5
        elif char in ("4", "5"):
            score += 2
        elif char in ("0", "6", "7", "8", "9"):
            score -= 3

    return score


def score_last_run(days):
    days = to_int(days)

    if days is None:
        return 0
    if 10 <= days <= 35:
        return 8
    if 36 <= days <= 60:
        return 4
    if days < 7:
        return -6
    if days > 120:
        return -8

    return 0


def score_draw(draw, field_size):
    draw = to_int(draw)
    field_size = to_int(field_size)

    if draw is None or field_size is None:
        return 0
    if field_size <= 6:
        return 1
    if draw <= 3:
        return 4
    if draw <= field_size / 2:
        return 2

    return 0


def format_tipster_note(tip):
    source = tip.get("source", "")
    tipster = tip.get("tipster", "")
    tip_type = tip.get("tip_type", "")

    label_parts = [part for part in [source, tipster, tip_type] if part]

    if not label_parts:
        return "Tipster support"

    return "Tipster: " + " · ".join(label_parts)


def calculate_horse_score(runner):
    score = 40
    notes = []

    form_score = score_form(runner.get("form"))
    score += form_score

    if form_score >= 12:
        notes.append("Strong recent form")
    elif form_score > 0:
        notes.append("Positive recent form")
    elif form_score < 0:
        notes.append("Weak recent form")

    last_run_score = score_last_run(runner.get("last_run"))
    score += last_run_score

    if last_run_score > 0:
        notes.append("Good recent run timing")
    elif last_run_score < 0:
        notes.append("Questionable run timing")

    draw_score = score_draw(runner.get("draw"), runner.get("field_size"))
    score += draw_score

    if draw_score > 0:
        notes.append("Helpful draw")

    if runner.get("number") in (None, "NR"):
        score -= 30
        notes.append("Non-runner risk")

    class_score = score_race_class(runner.get("race_class"))
    score += class_score

    if class_score > 0:
        notes.append(f"Race class strength +{class_score}")

    trainer_bonus = get_trainer_bonus(runner.get("trainer_id"))
    score += trainer_bonus

    if trainer_bonus > 0:
        notes.append(f"Trainer bonus +{trainer_bonus}")
    elif trainer_bonus < 0:
        notes.append(f"Trainer concern {trainer_bonus}")

    jockey_bonus = get_jockey_bonus(runner.get("jockey_id"))
    score += jockey_bonus

    if jockey_bonus > 0:
        notes.append(f"Jockey bonus +{jockey_bonus}")
    elif jockey_bonus < 0:
        notes.append(f"Jockey concern {jockey_bonus}")

    tipster_boost, tipster_matches = get_tipster_boost(
        runner.get("horse", "")
    )

    if tipster_boost > 0:
        score += tipster_boost
        notes.append(f"Tipster support +{tipster_boost}")

        for tip in tipster_matches:
            notes.append(format_tipster_note(tip))

    history = get_horse_history(runner.get("horse", ""))

    if history:
        wins = history.get("wins", 0)

        if wins >= 1:
            score += 3
            notes.append("Historical winner +3")

        course_name = runner.get("course", "")
        course_history = history.get("courses", {}).get(course_name)

        if course_history and course_history.get("wins", 0) >= 1:
            score += 4
            notes.append("Previous course winner +4")

    score = max(0, min(100, round(score)))

    value = value_rating(
        score,
        runner.get("sp")
    )

    return {
        "pulse_score": score,
        "notes": notes,
        "tipster_boost": tipster_boost,
        "tipsters": tipster_matches,
        "value_rating": value,
    }
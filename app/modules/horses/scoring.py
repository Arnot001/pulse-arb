from functools import lru_cache
from app.modules.horses.history_stats import (
    get_horse_history,
    get_distance_profile,
    get_going_profile,
    get_trainer_recent_form,
    get_jockey_recent_form,
)
from app.modules.horses.tipster_support import get_tipster_boost
from app.modules.horses.trainer_lookup import get_trainer_bonus
from app.modules.horses.jockey_lookup import get_jockey_bonus
from app.modules.horses.class_score import score_race_class
from app.modules.horses.value import value_rating
from app.utils import to_int

@lru_cache(maxsize=None)
def cached_trainer_bonus(trainer_id):
    return get_trainer_bonus(trainer_id)


@lru_cache(maxsize=None)
def cached_jockey_bonus(jockey_id):
    return get_jockey_bonus(jockey_id)


@lru_cache(maxsize=None)
def cached_trainer_recent_form(trainer_name, trainer_id, days):
    return get_trainer_recent_form(
        trainer_name=trainer_name,
        trainer_id=trainer_id,
        days=days,
    )


@lru_cache(maxsize=None)
def cached_jockey_recent_form(jockey_name, jockey_id, days):
    return get_jockey_recent_form(
        jockey_name=jockey_name,
        jockey_id=jockey_id,
        days=days,
    )


@lru_cache(maxsize=None)
def cached_tipster_boost(horse_name):
    return get_tipster_boost(horse_name)


@lru_cache(maxsize=None)
def cached_horse_history(horse_name):
    return get_horse_history(horse_name)


@lru_cache(maxsize=None)
def cached_distance_profile(horse_name, distance_value):
    return get_distance_profile(horse_name, distance_value)


@lru_cache(maxsize=None)
def cached_going_profile(horse_name, going):
    return get_going_profile(horse_name, going)


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

def score_layoff(days):
    days = to_int(days)

    if days is None:
        return 0

    if 14 <= days <= 35:
        return 2
    if days < 7:
        return -3
    if 121 <= days <= 240:
        return -4
    if days > 240:
        return -7

    return 0

    pace_score = score_pace_profile(runner)
    factors["pace_score"] = pace_score
    score += pace_score

    if pace_score > 0:
        notes.append(f"Positive pace profile +{pace_score}")
    elif pace_score < 0:
        notes.append(f"Pace concern {pace_score}")

def score_pace_profile(runner):
    # Pace data is not collected yet.
    # Keep this as a safe placeholder so future pace intelligence has a stored factor.
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
    factors = {}

    form_score = score_form(runner.get("form"))
    factors["form_score"] = form_score
    score += form_score

    if form_score >= 12:
        notes.append("Strong recent form")
    elif form_score > 0:
        notes.append("Positive recent form")
    elif form_score < 0:
        notes.append("Weak recent form")

    last_run_score = score_last_run(runner.get("last_run"))
    factors["last_run_score"] = last_run_score
    score += last_run_score

    if last_run_score > 0:
        notes.append("Good recent run timing")
    elif last_run_score < 0:
        notes.append("Questionable run timing")
        
    layoff_score = score_layoff(runner.get("last_run"))
    factors["layoff_score"] = layoff_score
    score += layoff_score

    if layoff_score > 0:
        notes.append(f"Ideal layoff profile +{layoff_score}")
    elif layoff_score == -3:
        notes.append("Sharp return concern -3")
    elif layoff_score == -4:
        notes.append("Long layoff concern -4")
    elif layoff_score == -7:
        notes.append("Very long absence concern -7")
        
    pace_score = score_pace_profile(runner)
    factors["pace_score"] = pace_score
    score += pace_score

    if pace_score > 0:
        notes.append(f"Positive pace profile +{pace_score}")
    elif pace_score < 0:
        notes.append(f"Pace concern {pace_score}")

    draw_score = score_draw(
        runner.get("draw"),
        runner.get("field_size"),
    )
    factors["draw_score"] = draw_score
    score += draw_score

    if draw_score > 0:
        notes.append("Helpful draw")

    non_runner_penalty = 0

    if runner.get("number") in (None, "NR"):
        non_runner_penalty = -30
        score += non_runner_penalty
        notes.append("Non-runner risk")

    factors["non_runner_penalty"] = non_runner_penalty

    class_score = score_race_class(runner.get("race_class"))
    factors["class_score"] = class_score
    score += class_score

    if class_score > 0:
        notes.append(f"Race class strength +{class_score}")

    trainer_bonus = cached_trainer_bonus(runner.get("trainer_id"))
    factors["trainer_bonus"] = trainer_bonus
    score += trainer_bonus

    if trainer_bonus > 0:
        notes.append(f"Trainer bonus +{trainer_bonus}")
    elif trainer_bonus < 0:
        notes.append(f"Trainer concern {trainer_bonus}")
        
    stable_form_bonus = 0

    stable_form = cached_trainer_recent_form(
        trainer_name=runner.get("trainer", ""),
        trainer_id=runner.get("trainer_id"),
        days=14,
    )

    if stable_form:
        stable_wins = stable_form.get("wins", 0)
        stable_runs = stable_form.get("runs", 0)
        stable_win_rate = stable_form.get("win_rate", 0)

        if stable_wins >= 3 and stable_win_rate >= 25:
            stable_form_bonus = 4
            score += stable_form_bonus
            notes.append(
                f"Stable flying +4 "
                f"({stable_wins}/{stable_runs} last 14 days)"
            )

        elif stable_wins >= 1 and stable_win_rate >= 15:
            stable_form_bonus = 2
            score += stable_form_bonus
            notes.append(
                f"Stable in form +2 "
                f"({stable_wins}/{stable_runs} last 14 days)"
            )

    factors["stable_form_bonus"] = stable_form_bonus

    jockey_bonus = cached_jockey_bonus(runner.get("jockey_id"))
    factors["jockey_bonus"] = jockey_bonus
    score += jockey_bonus

    if jockey_bonus > 0:
        notes.append(f"Jockey bonus +{jockey_bonus}")
    elif jockey_bonus < 0:
        notes.append(f"Jockey concern {jockey_bonus}")
        
    jockey_form_bonus = 0

    jockey_form = cached_jockey_recent_form(
        jockey_name=runner.get("jockey", ""),
        jockey_id=runner.get("jockey_id"),
        days=14,
    )

    if jockey_form:
        jockey_wins = jockey_form.get("wins", 0)
        jockey_runs = jockey_form.get("runs", 0)
        jockey_win_rate = jockey_form.get("win_rate", 0)

        if jockey_wins >= 3 and jockey_win_rate >= 25:
            jockey_form_bonus = 4
            score += jockey_form_bonus
            notes.append(
                f"Jockey flying +4 "
                f"({jockey_wins}/{jockey_runs} last 14 days)"
            )

        elif jockey_wins >= 1 and jockey_win_rate >= 15:
            jockey_form_bonus = 2
            score += jockey_form_bonus
            notes.append(
                f"Jockey in form +2 "
                f"({jockey_wins}/{jockey_runs} last 14 days)"
            )

    factors["jockey_form_bonus"] = jockey_form_bonus

    tipster_boost, tipster_matches = get_tipster_boost(
        runner.get("horse", "")
    )
    factors["tipster_boost"] = tipster_boost

    if tipster_boost > 0:
        score += tipster_boost
        notes.append(f"Tipster support +{tipster_boost}")

        for tip in tipster_matches:
            notes.append(format_tipster_note(tip))

    history = cached_horse_history(runner.get("horse", ""))

    historical_winner_bonus = 0
    previous_course_winner_bonus = 0

    if history:
        wins = history.get("wins", 0)

        if wins >= 1:
            historical_winner_bonus = 3
            score += historical_winner_bonus
            notes.append("Historical winner +3")

        course_name = runner.get("course", "")
        course_history = history.get("courses", {}).get(course_name)

        if course_history and course_history.get("wins", 0) >= 1:
            previous_course_winner_bonus = 4
            score += previous_course_winner_bonus
            notes.append("Previous course winner +4")
            
    distance_bonus = 0

    distance_value = runner.get("distance_f")

    if distance_value is not None:
        distance_value = f"{distance_value:g}f"
    else:
        distance_value = ""

    distance_profile = cached_distance_profile(
        runner.get("horse", ""),
        distance_value,
    )

    if distance_profile:
        distance_wins = distance_profile.get("wins", 0)
        distance_runs = distance_profile.get("runs", 0)
        distance_win_rate = distance_profile.get("win_rate", 0)

        if distance_wins >= 2 and distance_win_rate >= 40:
            distance_bonus = 4
            score += distance_bonus
            notes.append(
                f"Distance specialist +4 "
                f"({distance_wins}/{distance_runs} at trip)"
            )

        elif distance_wins >= 1:
            distance_bonus = 2
            score += distance_bonus
            notes.append(
                f"Proven at distance +2 "
                f"({distance_wins}/{distance_runs} at trip)"
            )

    factors["distance_bonus"] = distance_bonus
    
    going_bonus = 0

    going_profile = cached_going_profile(
        runner.get("horse", ""),
        runner.get("going", ""),
    )

    if going_profile:
        going_wins = going_profile.get("wins", 0)
        going_runs = going_profile.get("runs", 0)
        going_win_rate = going_profile.get("win_rate", 0)

        if going_wins >= 2 and going_win_rate >= 40:
            going_bonus = 4
            score += going_bonus
            notes.append(
                f"Going specialist +4 "
                f"({going_wins}/{going_runs} on going)"
            )

        elif going_wins >= 1:
            going_bonus = 2
            score += going_bonus
            notes.append(
                f"Proven on going +2 "
                f"({going_wins}/{going_runs} on going)"
            )

    factors["going_bonus"] = going_bonus

    factors["historical_winner_bonus"] = historical_winner_bonus
    factors["previous_course_winner_bonus"] = previous_course_winner_bonus

    raw_score = round(score)
    score = max(0, min(100, raw_score))

    value = value_rating(
        score,
        runner.get("sp"),
    )

    return {
        "pulse_score": score,
        "raw_score": raw_score,
        "notes": notes,
        "tipster_boost": tipster_boost,
        "tipsters": tipster_matches,
        "value_rating": value,
        "factors": factors,
    }
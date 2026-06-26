import json
from pathlib import Path


TEAM_HISTORY_DIR = Path("data/football/team_history")
TEAM_PROFILES_DIR = Path("data/football/team_profiles")


LEAGUE_STRENGTH = {
    "Premier League": 1.20,
    "Championship": 1.08,
    "League One": 0.98,
    "League Two": 0.90,
    "National League": 0.82,
}


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, round(value)))


def load_team_histories():
    teams = []

    if not TEAM_HISTORY_DIR.exists():
        return teams

    for file_path in TEAM_HISTORY_DIR.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                teams.append(json.load(f))
        except Exception:
            continue

    return teams


def rate_label(score):
    if score >= 85:
        return "Elite"
    if score >= 75:
        return "Strong"
    if score >= 65:
        return "Positive"
    if score >= 50:
        return "Average"
    return "Weak"


def get_primary_league(team):
    leagues = team.get("leagues", {})

    if not leagues:
        return "Unknown"

    return max(leagues.items(), key=lambda item: item[1])[0]


def get_league_strength(team):
    primary_league = get_primary_league(team)
    return LEAGUE_STRENGTH.get(primary_league, 1.0)


def calculate_attack_score(team):
    goals_pg = team.get("goals_for_per_game", 0)
    failed_rate = team.get("failed_to_score_rate", 0)
    shots_pg = team.get("total_shots_for", 0) / max(team.get("matches_played", 1), 1)

    score = 45
    score += goals_pg * 18
    score += shots_pg * 1.2
    score -= failed_rate * 0.35

    return clamp(score)


def calculate_defence_score(team):
    conceded_pg = team.get("goals_against_per_game", 0)
    clean_sheet_rate = team.get("clean_sheet_rate", 0)
    shots_against_pg = team.get("total_shots_against", 0) / max(team.get("matches_played", 1), 1)

    score = 75
    score -= conceded_pg * 18
    score += clean_sheet_rate * 0.35
    score -= shots_against_pg * 0.8

    return clamp(score)


def calculate_form_score(team):
    recent = team.get("recent_results", [])

    if not recent:
        return 50

    points = 0

    for result in recent[-10:]:
        if result == "W":
            points += 3
        elif result == "D":
            points += 1

    max_points = len(recent[-10:]) * 3

    if max_points == 0:
        return 50

    return clamp((points / max_points) * 100)


def calculate_discipline_score(team):
    played = max(team.get("matches_played", 1), 1)

    yellows_pg = team.get("yellow_cards", 0) / played
    reds_pg = team.get("red_cards", 0) / played

    score = 85
    score -= yellows_pg * 6
    score -= reds_pg * 25

    return clamp(score)


def calculate_consistency_score(team):
    win_rate = team.get("win_rate", 0)
    loss_rate = team.get("loss_rate", 0)
    goal_difference = team.get("goal_difference", 0)
    played = max(team.get("matches_played", 1), 1)

    gd_pg = goal_difference / played

    score = 50
    score += win_rate * 0.45
    score -= loss_rate * 0.25
    score += gd_pg * 12

    return clamp(score)


def build_notes(profile):
    strengths = []
    weaknesses = []

    if profile["attack_score"] >= 75:
        strengths.append("Strong attacking output")
    elif profile["attack_score"] <= 45:
        weaknesses.append("Low attacking output")

    if profile["defence_score"] >= 75:
        strengths.append("Strong defensive profile")
    elif profile["defence_score"] <= 45:
        weaknesses.append("Defensive weakness")

    if profile["form_score"] >= 75:
        strengths.append("Positive recent form")
    elif profile["form_score"] <= 45:
        weaknesses.append("Poor recent form")

    if profile["discipline_score"] <= 50:
        weaknesses.append("Discipline risk")

    if profile["consistency_score"] >= 75:
        strengths.append("Consistent results")
    elif profile["consistency_score"] <= 45:
        weaknesses.append("Inconsistent results")

    if profile["league_strength"] >= 1.15:
        strengths.append("Competing in elite league")
    elif profile["league_strength"] <= 0.90:
        weaknesses.append("Lower league strength adjustment")

    return strengths, weaknesses


def create_profile(team):
    attack_score = calculate_attack_score(team)
    defence_score = calculate_defence_score(team)
    form_score = calculate_form_score(team)
    discipline_score = calculate_discipline_score(team)
    consistency_score = calculate_consistency_score(team)

    raw_iq = clamp(
        attack_score * 0.25
        + defence_score * 0.25
        + form_score * 0.25
        + consistency_score * 0.20
        + discipline_score * 0.05
    )

    primary_league = get_primary_league(team)
    league_strength = get_league_strength(team)
    football_iq = clamp(raw_iq * league_strength)

    profile = {
        "team": team.get("team"),
        "football_iq": football_iq,
        "raw_iq": raw_iq,
        "rating": rate_label(football_iq),
        "primary_league": primary_league,
        "league_strength": league_strength,
        "attack_score": attack_score,
        "defence_score": defence_score,
        "form_score": form_score,
        "discipline_score": discipline_score,
        "consistency_score": consistency_score,
        "matches_played": team.get("matches_played", 0),
        "wins": team.get("wins", 0),
        "draws": team.get("draws", 0),
        "losses": team.get("losses", 0),
        "goals_for": team.get("goals_for", 0),
        "goals_against": team.get("goals_against", 0),
        "goal_difference": team.get("goal_difference", 0),
        "win_rate": team.get("win_rate", 0),
        "goals_for_per_game": team.get("goals_for_per_game", 0),
        "goals_against_per_game": team.get("goals_against_per_game", 0),
        "clean_sheet_rate": team.get("clean_sheet_rate", 0),
        "failed_to_score_rate": team.get("failed_to_score_rate", 0),
        "btts_rate": team.get("btts_rate", 0),
        "over_2_5_rate": team.get("over_2_5_rate", 0),
        "recent_form": team.get("recent_form", ""),
        "leagues": team.get("leagues", {}),
    }

    strengths, weaknesses = build_notes(profile)
    profile["strengths"] = strengths
    profile["weaknesses"] = weaknesses

    return profile


def save_profile(profile):
    TEAM_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    file_name = (
        profile["team"]
        .lower()
        .replace("&", "and")
        .replace(".", "")
        .replace("'", "")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
        + ".json"
    )

    file_path = TEAM_PROFILES_DIR / file_name

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def build_football_iq():
    teams = load_team_histories()

    profiles = []

    for team in teams:
        profile = create_profile(team)
        save_profile(profile)
        profiles.append(profile)

    profiles.sort(
        key=lambda item: item.get("football_iq", 0),
        reverse=True,
    )

    leaderboard_path = Path("data/football/team_profiles_leaderboard.json")
    leaderboard_path.parent.mkdir(parents=True, exist_ok=True)

    with leaderboard_path.open("w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)

    print(f"Football team histories loaded: {len(teams)}")
    print(f"Football IQ profiles saved: {len(profiles)}")

    print("\nTop 10 Football IQ")
    print("-" * 60)

    for profile in profiles[:10]:
        print(
            f"{profile['football_iq']:>3} | "
            f"raw {profile['raw_iq']:>3} | "
            f"x{profile['league_strength']:<4} | "
            f"{profile['rating']:<8} | "
            f"{profile['team']} "
            f"({profile['primary_league']})"
        )


if __name__ == "__main__":
    build_football_iq()
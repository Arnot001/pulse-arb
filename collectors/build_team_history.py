import json
from collections import defaultdict
from pathlib import Path


RESULTS_DIR = Path("data/football/results")
TEAM_HISTORY_DIR = Path("data/football/team_history")


def slugify_team_name(name):
    return (
        name.lower()
        .replace("&", "and")
        .replace(".", "")
        .replace("'", "")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )


def load_results():
    results = []

    if not RESULTS_DIR.exists():
        return results

    for file_path in RESULTS_DIR.glob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if record.get("status") == "finished":
                    results.append(record)

    return results


def blank_profile(team_name):
    return {
        "team": team_name,
        "matches_played": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
        "goal_difference": 0,
        "home_matches": 0,
        "away_matches": 0,
        "home_wins": 0,
        "home_draws": 0,
        "home_losses": 0,
        "away_wins": 0,
        "away_draws": 0,
        "away_losses": 0,
        "clean_sheets": 0,
        "failed_to_score": 0,
        "btts": 0,
        "over_2_5_goals": 0,
        "total_shots_for": 0,
        "total_shots_against": 0,
        "total_shots_on_target_for": 0,
        "total_shots_on_target_against": 0,
        "total_corners_for": 0,
        "total_corners_against": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "leagues": {},
        "recent_results": [],
        "matches": [],
    }


def add_number(value):
    if value is None:
        return 0

    try:
        return int(value)
    except Exception:
        return 0


def update_team(profile, result, side):
    is_home = side == "home"

    team = result["home_team"] if is_home else result["away_team"]
    opponent = result["away_team"] if is_home else result["home_team"]

    goals_for = add_number(result["home_score"] if is_home else result["away_score"])
    goals_against = add_number(result["away_score"] if is_home else result["home_score"])

    profile["matches_played"] += 1
    profile["goals_for"] += goals_for
    profile["goals_against"] += goals_against

    if is_home:
        profile["home_matches"] += 1
    else:
        profile["away_matches"] += 1

    if goals_for > goals_against:
        outcome = "W"
        profile["wins"] += 1
        if is_home:
            profile["home_wins"] += 1
        else:
            profile["away_wins"] += 1
    elif goals_for < goals_against:
        outcome = "L"
        profile["losses"] += 1
        if is_home:
            profile["home_losses"] += 1
        else:
            profile["away_losses"] += 1
    else:
        outcome = "D"
        profile["draws"] += 1
        if is_home:
            profile["home_draws"] += 1
        else:
            profile["away_draws"] += 1

    if goals_against == 0:
        profile["clean_sheets"] += 1

    if goals_for == 0:
        profile["failed_to_score"] += 1

    if goals_for > 0 and goals_against > 0:
        profile["btts"] += 1

    if goals_for + goals_against >= 3:
        profile["over_2_5_goals"] += 1

    profile["total_shots_for"] += add_number(result.get("home_shots") if is_home else result.get("away_shots"))
    profile["total_shots_against"] += add_number(result.get("away_shots") if is_home else result.get("home_shots"))

    profile["total_shots_on_target_for"] += add_number(
        result.get("home_shots_on_target") if is_home else result.get("away_shots_on_target")
    )
    profile["total_shots_on_target_against"] += add_number(
        result.get("away_shots_on_target") if is_home else result.get("home_shots_on_target")
    )

    profile["total_corners_for"] += add_number(result.get("home_corners") if is_home else result.get("away_corners"))
    profile["total_corners_against"] += add_number(result.get("away_corners") if is_home else result.get("home_corners"))

    profile["yellow_cards"] += add_number(result.get("home_yellow_cards") if is_home else result.get("away_yellow_cards"))
    profile["red_cards"] += add_number(result.get("home_red_cards") if is_home else result.get("away_red_cards"))

    league_name = result.get("league_name") or result.get("league") or "Unknown"
    profile["leagues"][league_name] = profile["leagues"].get(league_name, 0) + 1

    match_summary = {
        "match_id": result.get("match_id"),
        "date": result.get("date"),
        "league": league_name,
        "side": side,
        "team": team,
        "opponent": opponent,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "outcome": outcome,
    }

    profile["matches"].append(match_summary)
    profile["recent_results"].append(outcome)


def finalise_profile(profile):
    played = profile["matches_played"]

    profile["goal_difference"] = profile["goals_for"] - profile["goals_against"]

    if played:
        profile["win_rate"] = round(profile["wins"] / played * 100, 2)
        profile["draw_rate"] = round(profile["draws"] / played * 100, 2)
        profile["loss_rate"] = round(profile["losses"] / played * 100, 2)
        profile["goals_for_per_game"] = round(profile["goals_for"] / played, 2)
        profile["goals_against_per_game"] = round(profile["goals_against"] / played, 2)
        profile["clean_sheet_rate"] = round(profile["clean_sheets"] / played * 100, 2)
        profile["failed_to_score_rate"] = round(profile["failed_to_score"] / played * 100, 2)
        profile["btts_rate"] = round(profile["btts"] / played * 100, 2)
        profile["over_2_5_rate"] = round(profile["over_2_5_goals"] / played * 100, 2)
    else:
        profile["win_rate"] = 0
        profile["draw_rate"] = 0
        profile["loss_rate"] = 0
        profile["goals_for_per_game"] = 0
        profile["goals_against_per_game"] = 0
        profile["clean_sheet_rate"] = 0
        profile["failed_to_score_rate"] = 0
        profile["btts_rate"] = 0
        profile["over_2_5_rate"] = 0

    profile["recent_results"] = profile["recent_results"][-20:]
    profile["recent_form"] = "".join(profile["recent_results"])


def build_team_history():
    TEAM_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    results = load_results()
    teams = {}

    for result in results:
        home_team = result.get("home_team")
        away_team = result.get("away_team")

        if not home_team or not away_team:
            continue

        if home_team not in teams:
            teams[home_team] = blank_profile(home_team)

        if away_team not in teams:
            teams[away_team] = blank_profile(away_team)

        update_team(teams[home_team], result, "home")
        update_team(teams[away_team], result, "away")

    for profile in teams.values():
        finalise_profile(profile)

        file_name = slugify_team_name(profile["team"]) + ".json"
        file_path = TEAM_HISTORY_DIR / file_name

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"Football results loaded: {len(results)}")
    print(f"Team history profiles saved: {len(teams)}")


if __name__ == "__main__":
    build_team_history()
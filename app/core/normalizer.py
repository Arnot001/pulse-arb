import re


def normalize_text(value: str) -> str:
    """
    General text cleaner.
    """
    if not value:
        return ""

    value = value.lower().strip()

    value = re.sub(r"[^a-z0-9\s]", "", value)

    value = re.sub(r"\s+", " ", value)

    return value


def normalize_team_name(team_name: str) -> str:
    """
    Normalizes team names across bookmakers.
    """

    if not team_name:
        return ""

    team_name = normalize_text(team_name)

    replacements = {
        "man utd": "manchester united",
        "man united": "manchester united",
        "psg": "paris saint germain",
        "inter": "inter milan",
    }

    return replacements.get(team_name, team_name)


def normalize_bookmaker_name(bookmaker_name: str) -> str:
    """
    Cleans bookmaker names.
    """

    if not bookmaker_name:
        return ""

    bookmaker_name = normalize_text(bookmaker_name)

    replacements = {
        "bet fair": "betfair",
        "bet365 sportsbook": "bet365",
    }

    return replacements.get(bookmaker_name, bookmaker_name)


def normalize_market_name(market_name: str) -> str:
    """
    Cleans market names.
    """

    if not market_name:
        return ""

    market_name = normalize_text(market_name)

    replacements = {
        "match odds": "moneyline",
        "full time result": "moneyline",
    }

    return replacements.get(market_name, market_name)


def normalize_event(
    home_team: str,
    away_team: str,
) -> dict:
    """
    Builds normalized event object.
    """

    return {
        "home_team": normalize_team_name(home_team),
        "away_team": normalize_team_name(away_team),
    }
from app.modules.odds.paddypower import get_best_odds as pp_get_best_odds
from app.modules.odds.william_hill import get_best_odds as wh_get_best_odds
from app.modules.odds.oddschecker import get_best_odds as oc_get_best_odds


def get_best_odds(course, race_time, horse):
    # 1. Paddy Power
    try:
        result = pp_get_best_odds(course, race_time, horse)

        if result.get("success"):
            return result

        print(f"PP fallback: {horse} -> {result.get('error')}")

    except Exception as exc:
        print(f"Paddy Power error: {exc}")

    # 2. William Hill
    try:
        result = wh_get_best_odds(course, race_time, horse)

        if result.get("success"):
            return result

        print(f"WH fallback: {horse} -> {result.get('error')}")

    except Exception as exc:
        print(f"William Hill error: {exc}")

    # 3. Oddschecker
    try:
        result = oc_get_best_odds(
            course=course,
            race_time=race_time,
            horse=horse,
            headless=False,
        )

        result["odds_source"] = "oddschecker"

        return result

    except Exception as exc:
        return {
            "success": False,
            "horse": horse,
            "best_odds": None,
            "best_odds_decimal": None,
            "bookmaker": None,
            "odds_source": "none",
            "error": str(exc),
        }
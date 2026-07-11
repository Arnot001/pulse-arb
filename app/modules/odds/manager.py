from app.modules.odds.paddypower import (
    load_paddypower_data,
    normalise as pp_normalise,
    decimal_from_runner,
    fractional_from_runner,
    previous_prices,
)
from app.modules.odds.william_hill import get_best_odds as wh_get_best_odds
from app.modules.odds.oddschecker import get_best_odds as oc_get_best_odds


class OddsProviderManager:
    def __init__(self):
        self.paddy_records = []
        self.paddy_index = {}

    def preload(self):
        print("Preloading Paddy Power odds...")
        self.paddy_records = load_paddypower_data(force_refresh=True)
        self.paddy_index = self.build_paddy_index(self.paddy_records)
        print(f"Paddy Power records loaded: {len(self.paddy_records)}")
        print(f"Paddy Power runner index: {len(self.paddy_index)}")

    def build_paddy_index(self, records):
        index = {}

        for data in records:
            attachments = data.get("attachments", {})
            races = attachments.get("races", {})
            markets = attachments.get("markets", {})

            for market in markets.values():
                race = races.get(market.get("raceId"), {})
                venue = race.get("venue") or market.get("venue")
                start_time = race.get("startTime") or market.get("marketTime")

                for runner in market.get("runners", []):
                    if runner.get("runnerStatus") != "ACTIVE":
                        continue

                    horse_key = pp_normalise(runner.get("runnerName"))
                    decimal_odds = decimal_from_runner(runner)
                    fractional_odds = fractional_from_runner(runner)

                    if not horse_key or not decimal_odds or not fractional_odds:
                        continue

                    index[horse_key] = {
                        "success": True,
                        "horse": runner.get("runnerName"),
                        "matched_horse": runner.get("runnerName"),
                        "url": "https://www.paddypower.com/horse-racing",
                        "best_odds": fractional_odds,
                        "best_odds_decimal": decimal_odds,
                        "bookmaker": "Paddy Power",
                        "odds_source": "paddypower",
                        "event_id": market.get("eventId"),
                        "race_id": market.get("raceId"),
                        "market_id": market.get("marketId"),
                        "selection_id": runner.get("selectionId"),
                        "course": venue,
                        "start_time": start_time,
                        "price_history": previous_prices(runner),
                        "error": None,
                    }

        return index

    def get_best_odds(self, course, race_time, horse):
        horse_key = pp_normalise(horse)

        if horse_key in self.paddy_index:
            result = dict(self.paddy_index[horse_key])
            result["horse"] = horse
            return result

        try:
            result = wh_get_best_odds(course, race_time, horse)
            if result.get("success"):
                return result
            print(f"WH fallback: {horse} -> {result.get('error')}")
        except Exception as exc:
            print(f"William Hill error: {exc}")

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
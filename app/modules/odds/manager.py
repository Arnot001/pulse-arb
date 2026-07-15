from app.modules.odds.paddypower import (
    load_paddypower_data,
    normalise as pp_normalise,
    decimal_from_runner,
    fractional_from_runner,
    previous_prices,
)
from app.modules.odds.william_hill import (
    get_best_odds as wh_get_best_odds,
)
from app.modules.odds.oddschecker import (
    get_best_odds as oc_get_best_odds,
)


class OddsProviderManager:
    def __init__(self):
        self.paddy_records = []
        self.paddy_index = {}

    def preload(self):
        print("Preloading Paddy Power odds...")

        self.paddy_records = (
            load_paddypower_data(
                force_refresh=True
            )
        )

        self.paddy_index = (
            self.build_paddy_index(
                self.paddy_records
            )
        )

        print(
            "Paddy Power records loaded: "
            f"{len(self.paddy_records)}"
        )

        print(
            "Paddy Power runner index: "
            f"{len(self.paddy_index)}"
        )

    def build_paddy_index(
        self,
        records,
    ):
        index = {}

        for data in records:
            attachments = data.get(
                "attachments",
                {},
            )

            races = attachments.get(
                "races",
                {},
            )

            markets = attachments.get(
                "markets",
                {},
            )

            for market in markets.values():
                race = races.get(
                    market.get("raceId"),
                    {},
                )

                venue = (
                    race.get("venue")
                    or market.get("venue")
                )

                start_time = (
                    race.get("startTime")
                    or market.get("marketTime")
                )

                for runner in market.get(
                    "runners",
                    [],
                ):
                    if (
                        runner.get("runnerStatus")
                        != "ACTIVE"
                    ):
                        continue

                    horse_key = pp_normalise(
                        runner.get("runnerName")
                    )

                    decimal_odds = (
                        decimal_from_runner(
                            runner
                        )
                    )

                    fractional_odds = (
                        fractional_from_runner(
                            runner
                        )
                    )

                    if (
                        not horse_key
                        or decimal_odds is None
                        or not fractional_odds
                    ):
                        continue

                    try:
                        decimal_odds = float(
                            decimal_odds
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        continue

                    if decimal_odds <= 1.0:
                        continue

                    index[horse_key] = {
                        "success": True,
                        "horse": runner.get(
                            "runnerName"
                        ),
                        "matched_horse": runner.get(
                            "runnerName"
                        ),
                        "url": (
                            "https://www.paddypower.com/"
                            "horse-racing"
                        ),
                        "best_odds": (
                            fractional_odds
                        ),
                        "best_odds_decimal": (
                            round(
                                decimal_odds,
                                4,
                            )
                        ),
                        "bookmaker": "Paddy Power",
                        "odds_source": "paddypower",
                        "event_id": market.get(
                            "eventId"
                        ),
                        "race_id": market.get(
                            "raceId"
                        ),
                        "market_id": market.get(
                            "marketId"
                        ),
                        "selection_id": runner.get(
                            "selectionId"
                        ),
                        "course": venue,
                        "start_time": start_time,
                        "price_history": (
                            previous_prices(
                                runner
                            )
                        ),
                        "error": None,
                    }

        return index

    def _usable_result(
        self,
        result,
    ):
        if not isinstance(
            result,
            dict,
        ):
            return False

        if not result.get("success"):
            return False

        decimal_odds = result.get(
            "best_odds_decimal"
        )

        if decimal_odds is None:
            return False

        try:
            decimal_odds = float(
                decimal_odds
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        if decimal_odds <= 1.0:
            return False

        result[
            "best_odds_decimal"
        ] = round(
            decimal_odds,
            4,
        )

        return True

    def _normalise_failure(
        self,
        *,
        horse,
        source,
        result=None,
        error=None,
    ):
        result = (
            result
            if isinstance(result, dict)
            else {}
        )

        return {
            "success": False,
            "horse": horse,
            "matched_horse": (
                result.get("matched_horse")
            ),
            "best_odds": result.get(
                "best_odds"
            ),
            "best_odds_decimal": (
                result.get(
                    "best_odds_decimal"
                )
            ),
            "bookmaker": result.get(
                "bookmaker"
            ),
            "url": result.get("url"),
            "odds_source": source,
            "error": (
                error
                or result.get("error")
                or (
                    f"{source} returned no "
                    "usable decimal price"
                )
            ),
        }

    def get_best_odds(
        self,
        course,
        race_time,
        horse,
    ):
        horse_key = pp_normalise(
            horse
        )

        if horse_key in self.paddy_index:
            result = dict(
                self.paddy_index[
                    horse_key
                ]
            )

            result["horse"] = horse

            if self._usable_result(
                result
            ):
                return result

        william_hill_result = None

        try:
            william_hill_result = (
                wh_get_best_odds(
                    course,
                    race_time,
                    horse,
                )
            )

            if self._usable_result(
                william_hill_result
            ):
                william_hill_result[
                    "odds_source"
                ] = "william_hill"

                return william_hill_result

            print(
                f"WH fallback: {horse} -> "
                f"{(
                    william_hill_result
                    or {}
                ).get('error')}"
            )

        except Exception as exc:
            print(
                "William Hill error: "
                f"{exc}"
            )

            william_hill_result = (
                self._normalise_failure(
                    horse=horse,
                    source="william_hill",
                    error=str(exc),
                )
            )

        oddschecker_result = None

        try:
            oddschecker_result = (
                oc_get_best_odds(
                    course=course,
                    race_time=race_time,
                    horse=horse,
                    headless=False,
                )
            )

            if not isinstance(
                oddschecker_result,
                dict,
            ):
                oddschecker_result = {}

            oddschecker_result[
                "odds_source"
            ] = "oddschecker"

            if self._usable_result(
                oddschecker_result
            ):
                return oddschecker_result

            return self._normalise_failure(
                horse=horse,
                source="oddschecker",
                result=oddschecker_result,
            )

        except Exception as exc:
            return self._normalise_failure(
                horse=horse,
                source="oddschecker",
                result=oddschecker_result,
                error=str(exc),
            )
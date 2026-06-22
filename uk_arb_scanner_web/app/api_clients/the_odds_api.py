import os
from datetime import datetime, timedelta, timezone

import httpx


BASE_URL = "https://api.the-odds-api.com/v4"


class TheOddsApiClient:
    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")

        self.remaining_credits = None
        self.used_credits = None

    async def fetch_sports(self):
        url = f"{BASE_URL}/sports"

        params = {
            "apiKey": self.api_key,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)

            response.raise_for_status()

            data = response.json()

        priority = [
            "soccer_epl",
            "soccer_spain_la_liga",
            "soccer_italy_serie_a",
            "soccer_germany_bundesliga",
            "soccer_france_ligue_one",
            "basketball_nba",
            "basketball_euroleague",
            "tennis_atp_italian_open",
            "tennis_wta_italian_open",
        ]

        available_keys = {
            sport.get("key", "")
            for sport in data
        }

        return [
            sport_key
            for sport_key in priority
            if sport_key in available_keys
        ]

    async def fetch_sport_odds(
        self,
        sport_key: str,
        search_days: int = 5,
    ):
        commence_to = datetime.now(timezone.utc) + timedelta(days=search_days)

        commence_to_str = (
            commence_to
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        params = {
            "apiKey": self.api_key,
            "regions": "uk,eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "commenceTimeTo": commence_to_str,
        }

        url = f"{BASE_URL}/sports/{sport_key}/odds"

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url, params=params)

                response.raise_for_status()

                self.remaining_credits = response.headers.get(
                    "x-requests-remaining"
                )

                self.used_credits = response.headers.get(
                    "x-requests-used"
                )

                data = response.json()

            print(
                f"[OK] {sport_key}: "
                f"{len(data)} events | "
                f"Remaining credits: {self.remaining_credits}"
            )

            return data

        except Exception as e:
            print(f"[WARN] Failed {sport_key}: {e}")

            return []

    async def fetch_all(self, search_days: int = 5):
        sports = await self.fetch_sports()

        print()
        print(f"Scanning {len(sports)} priority sports...")

        all_events = []

        for sport in sports:
            events = await self.fetch_sport_odds(
                sport_key=sport,
                search_days=search_days,
            )

            all_events.extend(events)

        return {
            "events": all_events,
            "remaining_credits": self.remaining_credits,
            "used_credits": self.used_credits,
        }
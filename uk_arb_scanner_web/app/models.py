from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OutcomeOdds:
    name: str
    price: float
    bookmaker: str
    bookmaker_key: str
    event_url: Optional[str] = None
    last_update: Optional[datetime] = None


@dataclass
class EventMarket:
    event_id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    market_key: str
    outcomes: dict[str, list[OutcomeOdds]]

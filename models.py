from pydantic import BaseModel
from typing import Dict, List

class ArbOpportunity(BaseModel):
    event_id: str
    event: str
    commence_time: str
    market: str
    best_odds: Dict[str, float]
    profit_percent: float
    suggested_stakes: Dict[str, float]
    books: List[str]
    sport: str
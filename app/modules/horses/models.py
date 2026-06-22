from dataclasses import dataclass


@dataclass
class HorseSelection:
    race_time: str
    race_name: str
    horse: str

    odds: float = 0.0

    tipster_support: int = 0
    market_support: int = 0

    value_score: int = 0

    each_way: bool = False
    dark_horse: bool = False
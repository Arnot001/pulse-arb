from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict


# ---------------------------------------------------------
# Models
# ---------------------------------------------------------

@dataclass(slots=True)
class Bookmaker:

    id: str

    display_name: str

    homepage: str

    exchange: bool = False

    enabled: bool = True

    uk_supported: bool = True

    supports_deep_links: bool = False

    execution_priority: int = 100

    notes: str = ""

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------
# Canonical Registry
# ---------------------------------------------------------

BOOKMAKERS: Dict[str, Bookmaker] = {

    "bet365": Bookmaker(
        id="bet365",
        display_name="Bet365",
        homepage="https://www.bet365.com/",
        execution_priority=10,
    ),

    "skybet": Bookmaker(
        id="skybet",
        display_name="Sky Bet",
        homepage="https://m.skybet.com/",
        execution_priority=20,
    ),

    "williamhill": Bookmaker(
        id="williamhill",
        display_name="William Hill",
        homepage="https://sports.williamhill.com/",
        execution_priority=30,
    ),

    "ladbrokes": Bookmaker(
        id="ladbrokes",
        display_name="Ladbrokes",
        homepage="https://sports.ladbrokes.com/",
        execution_priority=40,
    ),

    "coral": Bookmaker(
        id="coral",
        display_name="Coral",
        homepage="https://sports.coral.co.uk/",
        execution_priority=50,
    ),

    "paddypower": Bookmaker(
        id="paddypower",
        display_name="Paddy Power",
        homepage="https://www.paddypower.com/",
        execution_priority=60,
    ),

    "betfair": Bookmaker(
        id="betfair",
        display_name="Betfair Sportsbook",
        homepage="https://www.betfair.com/sport/",
        execution_priority=70,
    ),

    "betfair_exchange": Bookmaker(
        id="betfair_exchange",
        display_name="Betfair Exchange",
        homepage="https://www.betfair.com/exchange/",
        exchange=True,
        execution_priority=80,
    ),

    "smarkets": Bookmaker(
        id="smarkets",
        display_name="Smarkets",
        homepage="https://smarkets.com/",
        exchange=True,
        execution_priority=90,
    ),

    "matchbook": Bookmaker(
        id="matchbook",
        display_name="Matchbook",
        homepage="https://www.matchbook.com/",
        exchange=True,
        execution_priority=100,
    ),

    "unibet": Bookmaker(
        id="unibet",
        display_name="Unibet",
        homepage="https://www.unibet.co.uk/",
        execution_priority=110,
    ),

    "betvictor": Bookmaker(
        id="betvictor",
        display_name="BetVictor",
        homepage="https://www.betvictor.com/",
        execution_priority=120,
    ),

    "888sport": Bookmaker(
        id="888sport",
        display_name="888sport",
        homepage="https://www.888sport.com/",
        execution_priority=130,
    ),

    "betway": Bookmaker(
        id="betway",
        display_name="Betway",
        homepage="https://betway.com/",
        execution_priority=140,
    ),

    "boylesports": Bookmaker(
        id="boylesports",
        display_name="BoyleSports",
        homepage="https://www.boylesports.com/",
        execution_priority=150,
    ),
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_bookmaker(
    bookmaker_id: str,
) -> Bookmaker | None:

    if bookmaker_id is None:
        return None

    key = (
        bookmaker_id
        .strip()
        .lower()
        .replace(" ", "")
    )

    return BOOKMAKERS.get(key)


def all_bookmakers():

    return sorted(
        BOOKMAKERS.values(),
        key=lambda b: b.execution_priority,
    )


def sportsbook_bookmakers():

    return [
        bookmaker
        for bookmaker in all_bookmakers()
        if not bookmaker.exchange
    ]


def exchange_bookmakers():

    return [
        bookmaker
        for bookmaker in all_bookmakers()
        if bookmaker.exchange
    ]
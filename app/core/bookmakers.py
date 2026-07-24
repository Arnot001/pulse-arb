from __future__ import annotations

from typing import Any


BOOKMAKER_INFO: dict[str, dict[str, Any]] = {
    # Sportsbooks
    "bet365": {
        "name": "Bet365",
        "url": "https://www.bet365.com/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": True,
    },
    "paddypower": {
        "name": "Paddy Power",
        "url": "https://www.paddypower.com/",
        "regions": {"GB", "IE"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "williamhill": {
        "name": "William Hill",
        "url": "https://sports.williamhill.com/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "betway": {
        "name": "Betway",
        "url": "https://betway.com/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "betvictor": {
        "name": "BetVictor",
        "url": "https://www.betvictor.com/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "coral": {
        "name": "Coral",
        "url": "https://sports.coral.co.uk/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "skybet": {
        "name": "Sky Bet",
        "url": "https://m.skybet.com/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "boylesports": {
        "name": "BoyleSports",
        "url": "https://www.boylesports.com/",
        "regions": {"GB", "IE"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "unibet": {
        "name": "Unibet",
        "url": "https://www.unibet.co.uk/",
        "regions": {"GB"},
        "product_type": "sportsbook",
        "sportsbook": True,
        "exchange": False,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },

    # Exchanges — retained in the registry but excluded from sportsbook arbs.
    "betfair_ex_uk": {
        "name": "Betfair Exchange",
        "url": "https://www.betfair.com/exchange/plus/",
        "regions": {"GB"},
        "product_type": "exchange",
        "sportsbook": False,
        "exchange": True,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "betfair_ex_eu": {
        "name": "Betfair Exchange EU",
        "url": "https://www.betfair.com/exchange/plus/",
        "regions": {"EU"},
        "product_type": "exchange",
        "sportsbook": False,
        "exchange": True,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "smarkets": {
        "name": "Smarkets",
        "url": "https://smarkets.com/",
        "regions": {"GB"},
        "product_type": "exchange",
        "sportsbook": False,
        "exchange": True,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
    "matchbook": {
        "name": "Matchbook",
        "url": "https://www.matchbook.com/",
        "regions": {"GB"},
        "product_type": "exchange",
        "sportsbook": False,
        "exchange": True,
        "horse_racing": True,
        "verified": True,
        "active": True,
        "execution_adapter": False,
    },
}


def normalize_bookmaker(bookmaker: str) -> str:
    return (
        str(bookmaker or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


BOOKMAKER_ALIASES: dict[str, str] = {
    normalize_bookmaker("Bet365"): "bet365",
    normalize_bookmaker("Paddy Power"): "paddypower",
    normalize_bookmaker("William Hill"): "williamhill",
    normalize_bookmaker("Betway"): "betway",
    normalize_bookmaker("BetVictor"): "betvictor",
    normalize_bookmaker("Coral"): "coral",
    normalize_bookmaker("Sky Bet"): "skybet",
    normalize_bookmaker("BoyleSports"): "boylesports",
    normalize_bookmaker("Unibet"): "unibet",
    normalize_bookmaker("Betfair Exchange"): "betfair_ex_uk",
    normalize_bookmaker("Betfair"): "betfair_ex_uk",
    normalize_bookmaker("Smarkets"): "smarkets",
    normalize_bookmaker("Matchbook"): "matchbook",
}


def resolve_bookmaker_key(bookmaker: str) -> str:
    raw_key = str(bookmaker or "").strip().lower()

    if raw_key in BOOKMAKER_INFO:
        return raw_key

    normalized = normalize_bookmaker(bookmaker)
    return BOOKMAKER_ALIASES.get(normalized, normalized)


def get_bookmaker(bookmaker: str) -> dict[str, Any] | None:
    return BOOKMAKER_INFO.get(resolve_bookmaker_key(bookmaker))


def is_verified_bookmaker(bookmaker: str) -> bool:
    info = get_bookmaker(bookmaker)

    return bool(
        info
        and info.get("verified")
        and info.get("active")
    )


def is_sportsbook(bookmaker: str) -> bool:
    info = get_bookmaker(bookmaker)

    return bool(
        info
        and info.get("sportsbook")
        and not info.get("exchange")
    )


def is_exchange(bookmaker: str) -> bool:
    info = get_bookmaker(bookmaker)
    return bool(info and info.get("exchange"))


def supports_horse_racing(bookmaker: str) -> bool:
    info = get_bookmaker(bookmaker)
    return bool(info and info.get("horse_racing"))


def has_execution_adapter(bookmaker: str) -> bool:
    info = get_bookmaker(bookmaker)
    return bool(info and info.get("execution_adapter"))


def get_bookmaker_url(bookmaker: str) -> str:
    info = get_bookmaker(bookmaker)

    if info and info.get("url"):
        return str(info["url"])

    return (
        "https://www.google.com/search?q="
        f"{str(bookmaker).strip()}+sportsbook"
    )

def sportsbook_ids() -> set[str]:
    return {
        bookmaker.id
        for bookmaker in sportsbook_bookmakers()
    }


def exchange_ids() -> set[str]:
    return {
        bookmaker.id
        for bookmaker in exchange_bookmakers()
    }
    
GB_SPORTSBOOKS = {
    key
    for key, info in BOOKMAKER_INFO.items()
    if (
        "GB" in info.get("regions", set())
        and info.get("sportsbook")
        and not info.get("exchange")
        and info.get("verified")
        and info.get("active")
    )
}


EXCHANGE_BOOKS = {
    key
    for key, info in BOOKMAKER_INFO.items()
    if info.get("exchange")
}


BOOKMAKER_URLS = {
    key: str(info["url"])
    for key, info in BOOKMAKER_INFO.items()
    if info.get("url")
}


# Backwards-compatible alias.
# Existing imports will continue working while we migrate the codebase.
UK_ALLOWED_BOOKS = GB_SPORTSBOOKS
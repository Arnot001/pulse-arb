UK_ALLOWED_BOOKS = {
    "betfair_ex_uk",
    "smarkets",
    "paddypower",
    "williamhill",
    "betway",
    "betvictor",
    "coral",
    "skybet",
    "boylesports",
    "unibet",
}


EXCHANGE_BOOKS = {
    "betfair_ex_uk",
    "smarkets",
}


BOOKMAKER_URLS = {
    "betfair_ex_eu": "https://www.betfair.com/exchange/plus/",
    "betfair_ex_uk": "https://www.betfair.com/exchange/plus/",
    "smarkets": "https://smarkets.com/",
    "matchbook": "https://www.matchbook.com/",
    "paddypower": "https://www.paddypower.com/",
    "williamhill": "https://sports.williamhill.com/",
    "betway": "https://betway.com/",
    "unibet": "https://www.unibet.co.uk/",
    "betvictor": "https://www.betvictor.com/",
    "coral": "https://sports.coral.co.uk/",
    "skybet": "https://m.skybet.com/",
    "boylesports": "https://boylesports.com/",
}


def get_bookmaker_url(bookmaker):
    return BOOKMAKER_URLS.get(
        bookmaker,
        f"https://www.google.com/search?q={bookmaker}+sportsbook",
    )
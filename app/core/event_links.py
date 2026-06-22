from urllib.parse import quote_plus


EXCHANGE_SEARCH_URLS = {
    "smarkets": "https://smarkets.com/sport/search?q={query}",
    "matchbook": "https://www.matchbook.com/events?query={query}",
    "betfair_ex_uk": "https://www.betfair.com/exchange/plus/search?query={query}",
    "betfair_ex_eu": "https://www.betfair.com/exchange/plus/search?query={query}",
}


def build_event_search_url(bookmaker, event_name):
    query = quote_plus(event_name)

    if bookmaker in EXCHANGE_SEARCH_URLS:
        return EXCHANGE_SEARCH_URLS[bookmaker].format(query=query)

    return (
        "https://www.google.com/search?q="
        + quote_plus(f"{event_name} {bookmaker} odds")
    )


def get_leg_url(bookmaker, event_name):
    return build_event_search_url(bookmaker, event_name)
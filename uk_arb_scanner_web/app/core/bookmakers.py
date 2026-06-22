UK_ALLOWED = {
    'bet365', 'betfair', 'betfair_ex_uk', 'skybet', 'williamhill', 'ladbrokes',
    'coral', 'paddypower', 'unibet_uk', 'betvictor', 'boylesports', '888sport',
    'betway', 'virginbet', 'spreadex', 'betfred', 'smarkets', 'matchbook',
    'grosvenor', 'livescorebet', 'quinnbet', 'talksportbet', 'betmgm_uk'
}

EXCLUDED = {'pinnacle', 'pinnacle_eu', 'bovada', 'mybookieag', 'betonlineag'}

BOOKMAKER_HOME_URLS = {
    'bet365': 'https://www.bet365.com/',
    'betfair': 'https://www.betfair.com/exchange/plus/',
    'betfair_ex_uk': 'https://www.betfair.com/exchange/plus/',
    'skybet': 'https://m.skybet.com/',
    'williamhill': 'https://sports.williamhill.com/betting/en-gb',
    'ladbrokes': 'https://sports.ladbrokes.com/',
    'coral': 'https://sports.coral.co.uk/',
    'paddypower': 'https://www.paddypower.com/',
    'unibet_uk': 'https://www.unibet.co.uk/betting',
    'betvictor': 'https://www.betvictor.com/en-gb/sports',
    'boylesports': 'https://www.boylesports.com/',
    '888sport': 'https://www.888sport.com/',
    'betway': 'https://sports.betway.com/',
    'virginbet': 'https://www.virginbet.com/',
    'spreadex': 'https://www.spreadex.com/sports',
    'betfred': 'https://www.betfred.com/sports',
    'smarkets': 'https://smarkets.com/sport/',
    'matchbook': 'https://www.matchbook.com/',
}

EXCHANGE_COMMISSION = {
    'betfair': 0.02,
    'betfair_ex_uk': 0.02,
    'smarkets': 0.02,
    'matchbook': 0.02,
}


def is_allowed_bookmaker(key: str) -> bool:
    k = key.lower()
    return k in UK_ALLOWED and k not in EXCLUDED


def manual_link(bookmaker_key: str, event_url: str | None = None) -> str:
    return event_url or BOOKMAKER_HOME_URLS.get(bookmaker_key.lower(), '')


def adjusted_decimal_odds(bookmaker_key: str, odds: float) -> float:
    commission = EXCHANGE_COMMISSION.get(bookmaker_key.lower(), 0)
    if commission <= 0:
        return odds
    # Commission applies to profit, not stake: net odds = 1 + (odds - 1) * (1 - commission)
    return 1 + ((odds - 1) * (1 - commission))

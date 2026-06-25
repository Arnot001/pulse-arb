from app.utils import to_float


FAIR_ODDS = [
    (90, 2.0),
    (85, 3.0),
    (80, 4.0),
    (75, 6.0),
    (70, 8.0),
    (65, 12.0),
    (60, 16.0),
]


def fair_odds(score):
    for minimum, odds in FAIR_ODDS:
        if score >= minimum:
            return odds

    return 20.0


def fractional_to_decimal(sp):
    if not sp:
        return None

    text = str(sp).strip().lower()

    if text in ("evens", "even"):
        return 2.0

    if "/" not in text:
        return to_float(text)

    try:
        a, b = text.split("/")
        return float(a) / float(b) + 1
    except Exception:
        return None


def value_rating(score, sp):
    fair = fair_odds(score)
    market = fractional_to_decimal(sp)

    if market is None:
        return None

    edge = market - fair

    if edge >= 3:
        return "★★★★★ VALUE"

    if edge >= 2:
        return "★★★★ VALUE"

    if edge >= 1:
        return "★★★ VALUE"

    if edge >= 0:
        return "★★ FAIR"

    return "❌ TOO SHORT"
from itertools import product
from app.core.stakes import calculate_stakes
from app.core.bookmakers import manual_link
from app.core.confidence import confidence_score, execution_difficulty


def find_opportunities(event, bankroll: float, min_profit: float, max_profit: float, near_arb_percent: float) -> list[dict]:
    outcome_names = list(event.outcomes.keys())
    if len(outcome_names) < 2:
        return []

    opportunities = []
    for combo in product(*[event.outcomes[name] for name in outcome_names]):
        # Avoid same bookmaker twice in same arb.
        bookmaker_keys = [leg.bookmaker_key for leg in combo]
        if len(bookmaker_keys) != len(set(bookmaker_keys)):
            continue

        odds = [leg.price for leg in combo]
        implied_total = sum(1 / odd for odd in odds)
        edge_percent = (1 - implied_total) * 100
        distance_to_arb = max(0, (implied_total - 1) * 100)

        is_arb = edge_percent > 0
        is_near = (not is_arb) and distance_to_arb <= near_arb_percent
        if not is_arb and not is_near:
            continue
        if is_arb and not (min_profit <= edge_percent <= max_profit):
            continue

        stakes = calculate_stakes(bankroll, odds)
        legs = []
        for i, raw in enumerate(combo):
            legs.append({
                'outcome': outcome_names[i],
                'bookmaker': raw.bookmaker,
                'bookmaker_key': raw.bookmaker_key,
                'odds': raw.price,
                'stake': stakes['stakes'][i],
                'event_url': manual_link(raw.bookmaker_key, raw.event_url),
                'last_update': raw.last_update,
            })

        conf = confidence_score(legs, max(edge_percent, 0), event.commence_time)
        opportunities.append({
            'type': 'ARB' if is_arb else 'NEAR_ARB',
            'event_id': event.event_id,
            'event_name': f'{event.home_team} vs {event.away_team}',
            'sport': event.sport_title,
            'sport_key': event.sport_key,
            'market': event.market_key,
            'commence_time': event.commence_time.isoformat(),
            'profit_percent': round(edge_percent, 2) if is_arb else 0,
            'distance_to_arb_percent': round(distance_to_arb, 2),
            'total_stake': bankroll,
            'guaranteed_profit': stakes['guaranteed_profit'] if is_arb else 0,
            'confidence': conf,
            'difficulty': execution_difficulty(max(edge_percent, 0), conf['label'], len(legs)),
            'legs': legs,
        })

    opportunities.sort(key=lambda x: (x['type'] != 'ARB', -x['profit_percent'], x['distance_to_arb_percent']))
    return opportunities

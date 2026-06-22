import asyncio
import httpx


def _field_for_leg(leg: dict) -> dict:
    return {
        'name': leg['bookmaker'],
        'value': (
            f"Outcome: **{leg['outcome']}**\n"
            f"Odds: **{leg['odds']}**\n"
            f"Stake: **£{leg['stake']}**\n"
            f"[Open bookmaker]({leg['event_url']})"
        ),
        'inline': True,
    }


async def send_discord(webhook_url: str, opportunities: list[dict], max_alerts: int = 20):
    if not webhook_url:
        return

    async with httpx.AsyncClient(timeout=15) as client:
        for opp in opportunities[:max_alerts]:
            is_arb = opp['type'] == 'ARB'
            title = '✅ ARB FOUND' if is_arb else '👀 NEAR ARB'
            fields = [
                {'name': 'Profit', 'value': f"{opp['profit_percent']}%" if is_arb else f"{opp['distance_to_arb_percent']}% away", 'inline': True},
                {'name': 'Total Stake', 'value': f"£{opp['total_stake']}", 'inline': True},
                {'name': 'Guaranteed Profit', 'value': f"£{opp['guaranteed_profit']}", 'inline': True},
                {'name': 'Confidence', 'value': opp['confidence']['label'], 'inline': True},
                {'name': 'Difficulty', 'value': opp['difficulty'], 'inline': True},
                *[_field_for_leg(leg) for leg in opp['legs']],
            ]
            embed = {
                'title': title,
                'description': f"**{opp['event_name']}**\n{opp['sport']} | {opp['market']}\nStarts: {opp['commence_time']}",
                'color': 3066993 if is_arb else 16776960,
                'fields': fields,
                'footer': {'text': 'Manual execution only — verify odds before placing bets.'},
            }
            r = await client.post(webhook_url, json={'embeds': [embed]})
            if r.status_code == 429:
                retry = float(r.headers.get('Retry-After', '2'))
                await asyncio.sleep(retry)
            else:
                r.raise_for_status()
            await asyncio.sleep(0.35)

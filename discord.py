import requests

from app.core.bookmakers import get_bookmaker_url


def format_discord_arb(item):
    lines = []

    lines.append("🚨 **SPORTSBOOK-ONLY TRUE ARB FOUND**")
    lines.append("")
    lines.append(f"**{item['event']}**")
    lines.append(f"Sport: `{item['sport']}`")
    lines.append(f"Start: `{item['commence_time']}`")
    lines.append(f"Profit: **{item['profit_percent']}%**")
    lines.append(f"Pulse Score: **{item.get('opportunity_score', 'N/A')}/100**")
    lines.append(f"Type: `{item.get('opportunity_type', 'N/A')}`")
    lines.append(f"Book %: **{item.get('book_percentage', 'N/A')}%**")
    lines.append("")

    movements = item.get("line_movements", [])

    if movements:
        lines.append("📈 **Line Movement**")

        for move in movements:
            arrow = "⬆️" if move["direction"] == "UP" else "⬇️"

            lines.append(
                f"{arrow} {move['outcome']} at {move['bookmaker']}: "
                f"{move['old_price']} → {move['new_price']} "
                f"({move['change']:+})"
            )

        lines.append("")

    for leg in item["legs"]:
        bookmaker = leg["bookmaker"]
        url = get_bookmaker_url(bookmaker)

        lines.append(
            f"[{bookmaker}]({url}) — **{leg['selection']}** "
            f"@ `{leg['odds']}` — Stake `£{leg['stake']}`"
        )

    return "\n".join(lines)


def send_discord_alert(arbs, discord_webhook_url):
    if not discord_webhook_url or not arbs:
        return

    top_arbs = arbs[:5]
    chunks = []

    for index, arb in enumerate(top_arbs, start=1):
        chunks.append(f"**#{index}**")
        chunks.append(format_discord_arb(arb))
        chunks.append("")

    if len(arbs) > 5:
        chunks.append(
            f"...and **{len(arbs) - 5}** more sportsbook-only true arbs in Pulse."
        )

    message = "\n".join(chunks)

    requests.post(
        discord_webhook_url,
        json={"content": message[:1900]},
        timeout=20,
    )
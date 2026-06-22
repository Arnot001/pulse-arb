from app.core.event_links import get_leg_url
from app.core.bookmakers import (
    EXCHANGE_BOOKS,
    get_bookmaker_url,
)

from app.core.pulse_score import calculate_pulse_score
from app.core.stable_window import detect_stable_window
from app.core.execution import calculate_execution


SPORT_LABELS = {
    "soccer_epl": "⚽ Premier League",
    "soccer_germany_bundesliga": "⚽ Bundesliga",
    "soccer_italy_serie_a": "⚽ Serie A",
    "soccer_spain_la_liga": "⚽ La Liga",
    "tennis_atp_french_open": "🎾 ATP French Open",
    "tennis_wta_french_open": "🎾 WTA French Open",
}


def render_result_card(item, result_type):
    is_new = item.get("is_new", False)
    badge_class = "arb" if result_type == "ARB" else "near"
    badge_text = "TRUE ARB" if result_type == "ARB" else "WATCHLIST"

    if item.get("exchange_arb"):
        badge_class = "exchange"
        badge_text = "EXCHANGE WATCHLIST"

    profit = item.get("profit_percent", 0)

    sport_label = SPORT_LABELS.get(
        item.get("sport", ""),
        item.get("sport", "Unknown Sport"),
    )

    pulse_score, pulse_reasons = calculate_pulse_score(
        item,
        profit,
    )

    score_class = "score-low"

    if pulse_score >= 70:
        score_class = "score-good"

    if pulse_score >= 85:
        score_class = "score-elite"

    execution = calculate_execution(item, profit)
    stable_window = detect_stable_window(item, profit)

    tracking = item.get("stability_tracking", {})
    stable_seconds = tracking.get("stable_seconds", 0)

    if profit <= 0:
        stable_label = f"👀 Watching ({stable_seconds}s)"
    elif stable_seconds >= 60:
        stable_label = f"🟣 Strong Price Stable ({stable_seconds}s)"
    elif stable_seconds >= 30:
        stable_label = f"🟢 Price Stable ({stable_seconds}s)"
    else:
        stable_label = f"⏳ Tracking ({stable_seconds}s)"

    legs_html = ""
    exchange_tools_html = ""
    legs_layout_class = "legs-grid"

    for leg in item.get("legs", []):
        bookmaker = leg["bookmaker"]
        url = get_leg_url(
            bookmaker=bookmaker,
            event_name=item.get("event", ""),
        )

        exchange_label = ""

        if bookmaker in EXCHANGE_BOOKS:
            exchange_label = """
            <span class="exchange-label">
                Exchange
            </span>
            """

            exchange_tools_html += f"""
            <div class="exchange-tool-row">
                <div>
                    <strong>{leg['selection']}</strong>
                    <span class="muted">@ {leg['odds']} on {bookmaker}</span>
                </div>

                <a
                    class="mini-button"
                    href="/lay-calculator?back_odds=2.0&back_stake=100.0&lay_odds={leg['odds']}&commission_percent=2.0"
                    target="_blank"
                >
                    Open Lay Calculator
                </a>
            </div>
            """

        legs_html += f"""
        <div class="leg-row">
            <div>
                <a href="{url}" target="_blank" class="bookmaker-link">
                    Open {bookmaker}
                </a>

                {exchange_label}

                <div class="selection-name">
                    {leg['selection']}
                </div>
            </div>

            <div class="leg-metrics">
                <div class="odds-pill">
                    @ {leg['odds']}
                </div>

                <div class="stake-text">
                    Stake £{leg.get('natural_stake', leg.get('stake', 0))}
                </div>
            </div>
        </div>
        """

    exchange_warning = ""
    
    stale_warning = ""

    event_age_seconds = item.get(
        "event_age_seconds",
        0,
    )

    if event_age_seconds > 10800:
        stale_warning = """
        <div class='warning-box'>
            <strong>⚠️ Market may be stale</strong><br>
            Event started more than 3 hours ago.
            Prices may no longer be active.
        </div>
        """

    if item.get("same_book_market"):
        exchange_warning = """
        <div class='warning-box'>
            <strong>⚠️ Same bookmaker/exchange detected</strong><br>
            This is a price gap/watchlist signal, not a confirmed executable arb.
        </div>
        """

    elif item.get("exchange_arb"):
        if profit > 0:
            exchange_warning = """
            <div class='warning-box'>
                <strong>⚠️ Exchange opportunity</strong><br>
                Mathematically positive based on available odds, but exchange prices may require liquidity, lay checks, and commission review before execution.
            </div>
            """
        else:
            exchange_warning = """
            <div class='warning-box'>
                <strong>⚠️ Exchange watchlist</strong><br>
                This is not currently profitable. It is being monitored because prices are close or moving.
            </div>
            """

    price_gap_html = ""

    if item.get("price_gaps"):
        gap_rows = ""

        for gap in item["price_gaps"]:
            gap_rows += f"""
            <div class="gap-row">
                <div>
                    <strong>{gap['selection']}</strong>

                    <div class="muted">
                        Best {gap['best_odds']} at {gap['best_bookmaker']}
                        / Worst {gap['worst_odds']} at {gap['worst_bookmaker']}
                    </div>
                </div>

                <div class="gap-percent">
                    {gap['gap_percent']}%
                </div>
            </div>
            """

        price_gap_html = f"""
        <div class="price-gap-box">
            <div class="section-label">
                📈 Price Gap Watchlist
            </div>

            {gap_rows}
        </div>
        """

    return f"""
    <div
        class="card pulse-card"
        data-scanned="{item.get('scanned_at', '')}"
    >

        <div class="card-top">

            <div class="card-top-left">

                <div class="event-title">
                    {item['event']}
                </div>

                <div class="event-meta">
                    {sport_label} · {item['commence_time']}
                </div>

            </div>

            <div class="card-badges">

                {
                    '<span class="new-badge">⚡ NEW</span>'
                    if is_new else ''
                }

                <span class="badge {badge_class}">
                    {badge_text}
                </span>

            </div>

        </div>

        <div class="pulse-card-metrics">
            <div class="metric-box">
                <div class="metric-label">
                    Profit / Gap
                </div>

                <div class="metric-value profit">
                    {profit}%
                </div>
            </div>

            <div class="metric-box pulse-score-box">
                <div class="metric-label">
                    Pulse Score
                </div>

                <div class="metric-value pulse-score {score_class}">
                    {pulse_score}
                </div>
            </div>

            <div class="metric-box">
                <div class="metric-label">
                    Execution
                </div>

                <div class="metric-value execution-{execution.lower()}">
                    {execution}
                </div>
            </div>

            <div class="metric-box">
                <div class="metric-label">
                    Stable Window
                </div>

                <div class="metric-value stable-{stable_window.lower()}">
                    {stable_label}
                </div>
            </div>
        </div>

        <div class="section-label">
            Best Legs
        </div>

        <div class="{legs_layout_class}">
            {legs_html}
        </div>

        {price_gap_html}

        <div class="price-gap-box">
            <div class="section-label">
                🧠 Pulse Notes
            </div>

            <ul class="pulse-notes">
                {
                    "".join(
                        f"<li>{reason}</li>"
                        for reason in pulse_reasons
                    )
                }
            </ul>
        </div>

        {stale_warning}
        {exchange_warning}
    </div>
    """
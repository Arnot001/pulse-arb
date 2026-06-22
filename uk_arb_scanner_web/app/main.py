from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.core.scanner import run_scan


app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    bankroll: float = Query(100, ge=1),
    near_threshold: float = Query(-3),
    scan: int = Query(0),
):
    cards = ""
    credit_html = ""

    if scan == 1:
        results = await run_scan(
            send_alerts=False,
            bankroll=bankroll,
            near_threshold=near_threshold,
        )

        credit_html = f"""
        <div class="panel">
            <strong>API Credits</strong><br>
            Remaining: {results.get('remaining_credits')}<br>
            Used: {results.get('used_credits')}
        </div>
        """

        for item in results["arbs"] + results["near_arbs"]:
            label = "ARB" if item in results["arbs"] else "NEAR-ARB"

            legs_html = ""

            for i, leg in enumerate(item["legs"]):
                legs_html += f"""
                <li>
                    <strong>{leg['bookmaker']}</strong> —
                    {leg['outcome']} @ {leg['price']} —
                    Stake £{item['stakes'][i]}
                    <a href="{leg['url']}" target="_blank">Open</a>
                </li>
                """

            cards += f"""
            <div class="card">
                <h2>{item['event']}</h2>
                <p><strong>Start:</strong> {item.get('commence_time')}</p>
                <p><strong>{label}</strong> | {item['sport']}</p>
                <p>Profit / Gap: <strong>{item['profit_percent']}%</strong></p>
                <p>Total stake: £{item['bankroll']}</p>
                <ul>{legs_html}</ul>
            </div>
            """

        if not cards:
            cards = "<p>No arbs or near-arbs found.</p>"
    else:
        cards = "<p>Press Run Scan to fetch odds.</p>"

    return f"""
    <!doctype html>
    <html>
    <head>
        <title>UK Arb Scanner</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #111827;
                color: #f9fafb;
                padding: 30px;
            }}
            .panel, .card {{
                background: #1f2937;
                border: 1px solid #374151;
                border-radius: 14px;
                padding: 20px;
                margin-bottom: 18px;
            }}
            input {{
                padding: 8px;
                margin: 8px;
                width: 100px;
            }}
            button {{
                padding: 10px 18px;
                cursor: pointer;
            }}
            a {{
                color: #93c5fd;
                margin-left: 10px;
            }}
        </style>
    </head>
    <body>
        <h1>UK Arb Scanner</h1>
        <p>Manual execution only. Check odds before placing bets.</p>

        <div class="panel">
            <form method="get">
                <input type="hidden" name="scan" value="1">

                <label>
                    Bankroll £
                    <input type="number" name="bankroll" value="{bankroll}" step="10">
                </label>

                <label>
                    Near threshold %
                    <input type="number" name="near_threshold" value="{near_threshold}" step="0.1">
                </label>

                <button type="submit">Run Scan</button>
            </form>
        </div>

        {credit_html}
        {cards}
    </body>
    </html>
    """
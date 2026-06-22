# UK Arb Scanner Web

A local web interface for one-shot daily arbitrage scanning.

Manual execution only. The app never logs in, fills bet slips, clicks bookmaker buttons, or places bets.

## Install

```bash
unzip uk_arb_scanner_web.zip
cd uk_arb_scanner_web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your keys:

```bash
ODDS_API_KEY=your_odds_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

## Run the web interface

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Press **Run one scan**. When finished, stop the server with `CTRL+C`.

## Optional command-line scan

```bash
python -m app.once
```

Results are saved to:

```text
app/output/latest_results.json
```

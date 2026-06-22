from dotenv import load_dotenv
import os

load_dotenv()

THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

BASE_URL = "https://api.the-odds-api.com/v4"
REGIONS = "uk,eu"
POLL_INTERVAL_MINUTES = 10
MIN_PROFIT_PERCENT = 1.0
MAX_HOURS_AHEAD = 72
SPORTS_TO_SCAN = ["soccer_epl", "soccer_championship", "soccer_europa_league", "tennis_atp", "basketball_nba"]
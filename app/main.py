from pathlib import Path
import logging
import os
import subprocess
import sys
import threading
import requests
import time

from app.modules.performance.profit_engine import simulate_level_stakes
from app.modules.performance.bet_ledger import (load_jsonl,LEDGER_FILE,get_verified_official_stats,get_all_settled_stats,get_bankroll_history,get_performance_insights,)
from app.modules.race_intelligence.output import (get_race_intelligence_dashboard,)
from app.modules.strategy.engine import get_strategy_lab_data
from app.modules.dashboard import get_dashboard_data
from app.modules.betting.builder import build_bets
from app.modules.football.routes import get_football_leaderboard
from collectors.daily_update import run_jobs
from collectors.pulse_live_engine import run_loop as run_pulse_live_engine
from fastapi import FastAPI, Query, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.modules.horses.market_events import get_market_events
from app.modules.horses.performance import get_latest_performance_report
from app.modules.horses.profile import get_horse_profile
from app.modules.horses.leaderboard_routes import get_leaderboard_data
from app.modules.horses.output import get_race_by_key
from app.modules.horses.routes import get_horse_dashboard, get_horse_race_groups

from app.services.scanner import (
    fetch_sport_results,
    run_full_scan,
)

from app.ui.cards import render_result_card
from app.core.pulse_score import calculate_pulse_score

from app.core.history import (
    save_scan_results,
    save_latest_scan,
    load_latest_scan,
    get_sport_stats,
    get_bookmaker_stats,
)

from app.core.settings import (
    load_settings,
    save_settings,
)

from app.core.lay_calculator import calculate_lay_arb


app = FastAPI(title="Pulse")

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

templates = Jinja2Templates(directory="app/templates")

logging.basicConfig(level=logging.INFO)
PULSE_LIVE_THREAD = None
PULSE_LIVE_ENABLED = os.getenv("PULSE_LIVE_ENABLED", "1") == "1"


@app.on_event("startup")
def start_pulse_live_engine():
    global PULSE_LIVE_THREAD

    if not PULSE_LIVE_ENABLED:
        print("Pulse Live Engine disabled.")
        return

    if PULSE_LIVE_THREAD and PULSE_LIVE_THREAD.is_alive():
        return

    PULSE_LIVE_THREAD = threading.Thread(
        target=run_pulse_live_engine,
        daemon=True,
    )
    PULSE_LIVE_THREAD.start()

    print("Pulse Live Engine plugged in ✅")

UPDATE_LOCK = threading.Lock()

UPDATE_STATUS = {
    "running": False,
    "mode": None,
    "current_task": "Ready",
    "percent": 0,
    "bar": "░░░░░░░░░░░░░░░░░░░░ 0%",
    "completed": [],
    "failed": [],
    "started_at": None,
    "finished_at": None,
    "runtime": None,
}


def build_progress_bar(percent):
    filled = int(percent / 5)
    empty = 20 - filled
    return f"{'█' * filled}{'░' * empty} {percent}%"


def run_update_job(mode):
    with UPDATE_LOCK:
        UPDATE_STATUS["running"] = True
        UPDATE_STATUS["mode"] = mode
        UPDATE_STATUS["current_task"] = "Starting..."
        UPDATE_STATUS["percent"] = 0
        UPDATE_STATUS["bar"] = build_progress_bar(0)
        UPDATE_STATUS["completed"] = []
        UPDATE_STATUS["failed"] = []
        UPDATE_STATUS["started_at"] = time.time()
        UPDATE_STATUS["finished_at"] = None
        UPDATE_STATUS["runtime"] = None

    def progress(update_event):
        if update_event["event"] == "start":
            with UPDATE_LOCK:
                UPDATE_STATUS["current_task"] = update_event["label"]

        elif update_event["event"] == "finish":
            percent = int(
                (update_event["index"] / update_event["total"]) * 100
            )

            with UPDATE_LOCK:
                UPDATE_STATUS["percent"] = percent
                UPDATE_STATUS["bar"] = build_progress_bar(percent)

                if update_event["success"]:
                    UPDATE_STATUS["completed"].append(update_event["label"])
                else:
                    UPDATE_STATUS["failed"].append(update_event["label"])

    summary = run_jobs(
        mode,
        progress_callback=progress,
    )

    finished_at = time.time()

    with UPDATE_LOCK:
        UPDATE_STATUS["running"] = False
        UPDATE_STATUS["current_task"] = "Complete"
        UPDATE_STATUS["finished_at"] = finished_at
        UPDATE_STATUS["runtime"] = summary["runtime"]


def start_update(mode, redirect_url="/"):
    with UPDATE_LOCK:
        if UPDATE_STATUS["running"]:
            return RedirectResponse(
                url=f"{redirect_url}?update=already-running",
                status_code=303,
            )

    thread = threading.Thread(
        target=run_update_job,
        args=(mode,),
        daemon=True,
    )
    thread.start()

    return RedirectResponse(
        url=f"{redirect_url}?update=started",
        status_code=303,
    )

@app.get("/update/status")
def update_status():
    with UPDATE_LOCK:
        return dict(UPDATE_STATUS)


@app.post("/update/horses")
def update_horses():
    return start_update("horses", "/horses")


@app.post("/update/dogs")
def update_dogs():
    return start_update("dogs", "/")


@app.post("/update/football")
def update_football():
    return start_update("football", "/")


@app.post("/update/all")
def update_all():
    return start_update("all", "/")


@app.post("/update/performance")
def update_performance():
    return start_update("performance", "/results-intelligence")

@app.post("/update/settlement")
def update_settlement():
    return start_update("settlement", "/bet-builder")

@app.get("/horses", response_class=HTMLResponse)
def horses(request: Request):
    return templates.TemplateResponse(
        request,
        "horses.html",
        {
            "cards": get_horse_dashboard(),
            "active_page": "horses",
        },
    )
    
@app.get("/bet-builder", response_class=HTMLResponse)
def bet_builder(request: Request):
    return templates.TemplateResponse(
        request,
        "bet_builder.html",
        {
            "active_page": "bet_builder",
            "bets": build_bets(),
        },
    )
    
@app.get("/race-intelligence", response_class=HTMLResponse)
def race_intelligence(request: Request):
    return templates.TemplateResponse(
        request,
        "race_intelligence.html",
        {
            "active_page": "race_intelligence",
            **get_race_intelligence_dashboard(),
        },
    )
    
@app.get("/horses/profile/{horse_name}", response_class=HTMLResponse)
def horse_profile(request: Request, horse_name: str):
    horse = get_horse_profile(horse_name)

    if not horse:
        return HTMLResponse("Horse profile not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "horse_profile.html",
        {
            "active_page": "horses",
            "horse": horse,
        },
    )

@app.get("/horses/market-events", response_class=HTMLResponse)
def horse_market_events(request: Request):
    return templates.TemplateResponse(
        request,
        "horse_market_events.html",
        {
            "active_page": "market_events",
            "events": get_market_events(),
        },
    )
    
@app.get("/football", response_class=HTMLResponse)
def football(request: Request):
    return templates.TemplateResponse(
        request,
        "football.html",
        {
            "active_page": "football",
            "teams": get_football_leaderboard(),
        },
    )

@app.get("/horses/races", response_class=HTMLResponse)
def horses_races(request: Request):
    races = get_horse_race_groups()

    racecards = {}

    for race in races:
        course = race.get("course", "Unknown")

        if course not in racecards:
            racecards[course] = {
                "course": course,
                "races": [],
                "top_pick": None,
                "best_score": 0,
                "dominant_count": 0,
                "tight_count": 0,
            }

        racecards[course]["races"].append(race)

        if race.get("top_score", 0) > racecards[course]["best_score"]:
            racecards[course]["best_score"] = race.get("top_score", 0)
            racecards[course]["top_pick"] = race.get("pulse_pick", {}).get("horse")

        if race.get("confidence") == "DOMINANT":
            racecards[course]["dominant_count"] += 1

        if race.get("confidence") == "TIGHT RACE":
            racecards[course]["tight_count"] += 1

    return templates.TemplateResponse(
        request,
        "horses_races.html",
        {
            "racecards": racecards.values(),
            "active_page": "racecards",
        },
    )

@app.get("/strategy", response_class=HTMLResponse)
def strategy_lab(request: Request):
    return templates.TemplateResponse(
        request,
        "strategy_lab.html",
        {
            "active_page": "strategy",
            **get_strategy_lab_data(),
        },
    )

@app.get("/horses/leaderboards", response_class=HTMLResponse)
def horses_leaderboards(request: Request):
    data = get_leaderboard_data()

    return templates.TemplateResponse(
        request,
        "horses_leaderboards.html",
        {
            "active_page": "horses",
            "trainers": data["trainers"],
            "jockeys": data["jockeys"],
        },
    )
    
@app.get("/bet-ledger", response_class=HTMLResponse)
def bet_ledger(request: Request, stake: float = Query(1.0)):
    bets = load_jsonl(LEDGER_FILE)
    report = simulate_level_stakes(stake)

    open_bets = [
        bet for bet in bets
        if bet.get("status") == "OPEN"
    ]

    settled_bets = [
        bet for bet in bets
        if bet.get("status") == "SETTLED"
    ]

    official_bets = [
        bet for bet in bets
        if bet.get("official_bet")
    ]

    near_misses = [
        bet for bet in bets
        if (
            not bet.get("official_bet")
            and (bet.get("pulse_score") or 0) >= 80
        )
    ]

    prediction_only = [
        bet for bet in bets
        if (
            not bet.get("official_bet")
            and (bet.get("pulse_score") or 0) < 80
        )
    ]

    official_settled = [
        bet for bet in official_bets
        if bet.get("status") == "SETTLED"
    ]

    official_winners = [
        bet for bet in official_settled
        if bet.get("won")
    ]

    official_profit = round(
        sum(bet.get("profit") or 0 for bet in official_settled),
        2,
    )

    official_total = len(official_bets)

    official_strike_rate = 0
    official_roi = 0

    if official_settled:
        official_strike_rate = round(
            (len(official_winners) / len(official_settled)) * 100,
            1,
        )

        official_roi = round(
            (official_profit / len(official_settled)) * 100,
            1,
        )

    today = None
    if bets:
        today = max(bet.get("date") for bet in bets if bet.get("date"))

    today_bets = [
        bet for bet in bets
        if bet.get("date") == today
    ]

    settled_today_bets = [
        bet for bet in today_bets
        if bet.get("status") == "SETTLED"
    ]

    won_today_bets = [
        bet for bet in settled_today_bets
        if bet.get("won")
    ]

    today_profit = round(
        sum(bet.get("profit") or 0 for bet in settled_today_bets),
        2,
    )

    return templates.TemplateResponse(
        request,
        "bet_ledger.html",
        {
            "active_page": "bet_ledger",
            "bets": bets[-50:][::-1],
            "official_bets": official_bets,
            "prediction_only": prediction_only,
            "near_misses": near_misses,
            "open_bets": open_bets,
            "settled_bets": settled_bets,
            "report": report,
            "stake": stake,

            "official_total": official_total,
            "official_winners": len(official_winners),
            "official_strike_rate": official_strike_rate,
            "official_roi": official_roi,
            "official_profit": official_profit,

            "settled_today": len(settled_today_bets),
            "won_today": len(won_today_bets),
            "today_profit": today_profit,
        },
    )

@app.get("/performance", response_class=HTMLResponse)
def performance(request: Request):
    return templates.TemplateResponse(
        request,
        "performance.html",
        {
            "request": request,
            "active_page": "performance",
            "official_stats": get_verified_official_stats(),
            "all_stats": get_all_settled_stats(),
            "bankroll_history": get_bankroll_history(),
            "insights": get_performance_insights(),
        },
    )
    
@app.get("/results-intelligence", response_class=HTMLResponse)
def horses_performance(request: Request):
    report = get_latest_performance_report()

    return templates.TemplateResponse(
        request,
        "horses_performance.html",
        {
            "active_page": "performance",
            "report": report,
        },
    )


CREDIT_STOP_LIMIT = 20
BACKGROUND_SCAN_SECONDS = 3600


SPORT_OPTIONS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026",
    "tennis_atp_halle_open": "ATP Halle Open",
    "tennis_atp_queens_club_champ": "ATP Queen's Club",
    "tennis_wta_german_open": "WTA German Open",
    "baseball_mlb": "MLB",
    "basketball_wnba": "WNBA",
    "mma_mixed_martial_arts": "MMA",
    "boxing_boxing": "Boxing",
    "soccer_sweden_allsvenskan": "Sweden Allsvenskan",
    "soccer_norway_eliteserien": "Norway Eliteserien",
    "cricket_t20_world_cup_womens": "Women's T20 World Cup",
}


LOADED_SCAN = load_latest_scan()

SCAN_CACHE = {
    "arbs": LOADED_SCAN.get("arbs", []),
    "near_arbs": LOADED_SCAN.get("near_arbs", []),
    "last_scan": LOADED_SCAN.get("last_scan"),
    "api_remaining": LOADED_SCAN.get("api_remaining"),
    "api_used": LOADED_SCAN.get("api_used"),
}


def get_the_odds_api_key():
    settings = load_settings()
    return settings["providers"]["the_odds_api"]["api_key"]


def get_discord_webhook_url():
    settings = load_settings()
    return settings.get("discord_webhook", "")


def save_current_cache():
    save_latest_scan(
        arbs=SCAN_CACHE["arbs"],
        near_arbs=SCAN_CACHE["near_arbs"],
        last_scan=SCAN_CACHE["last_scan"],
        api_remaining=SCAN_CACHE["api_remaining"],
        api_used=SCAN_CACHE["api_used"],
    )


def get_remaining_credits():
    try:
        return int(SCAN_CACHE.get("api_remaining"))
    except Exception:
        return None


def should_pause_for_credits():
    remaining = get_remaining_credits()

    if remaining is None:
        return False

    if remaining <= 0:
        return False

    return remaining <= CREDIT_STOP_LIMIT


@app.get("/health")
def health():
    return {"status": "running ✅"}


@app.get("/lay-calculator", response_class=HTMLResponse)
def lay_calculator_page(
    back_odds: float = Query(2.0),
    back_stake: float = Query(100.0),
    lay_odds: float = Query(2.1),
    commission_percent: float = Query(2.0),
):
    commission = commission_percent / 100

    result = calculate_lay_arb(
        back_odds=back_odds,
        back_stake=back_stake,
        lay_odds=lay_odds,
        commission=commission,
    )

    if result:
        result_html = f"""
        <div class="result">
            <p>Lay Stake: <strong>£{result['lay_stake']}</strong></p>
            <p>Liability: <strong>£{result['liability']}</strong></p>

            <p class="green">
                Profit if BACK wins:
                £{result['profit_if_back_wins']}
            </p>

            <p class="green">
                Profit if LAY wins:
                £{result['profit_if_lay_wins']}
            </p>
        </div>
        """
    else:
        result_html = """
        <div class="result">
            <p class="red">Invalid numbers. Check your odds and stake.</p>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pulse Lay Calculator</title>
        <link rel="icon" type="image/png" href="/static/favicon.png">
        <style>
            body {{
                background: #050505;
                color: white;
                font-family: Arial, sans-serif;
                padding: 40px;
            }}
            h1 {{
                color: #ff174f;
                font-size: 42px;
            }}
            .panel {{
                background: #111;
                border: 1px solid #333;
                border-radius: 14px;
                padding: 24px;
                max-width: 700px;
            }}
            label {{
                display: block;
                margin-bottom: 6px;
                color: #ccc;
                font-weight: bold;
            }}
            input {{
                width: 100%;
                padding: 12px;
                margin-bottom: 18px;
                background: #050505;
                color: white;
                border: 1px solid #444;
                border-radius: 8px;
                box-sizing: border-box;
            }}
            button {{
                background: linear-gradient(90deg, #ff174f, #9b2cff);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 18px;
                font-weight: bold;
                cursor: pointer;
            }}
            .result {{
                margin-top: 24px;
                padding: 20px;
                background: #181818;
                border-radius: 12px;
                border: 1px solid #333;
            }}
            .green {{
                color: #00e676;
                font-weight: bold;
            }}
            .red {{
                color: #ff5252;
                font-weight: bold;
            }}
            .muted {{
                color: #aaa;
            }}
            a {{
                color: #d066ff;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>

    <body>
        <h1>Pulse Lay Calculator</h1>

        <div class="panel">
            <form method="get" action="/lay-calculator">
                <label>Back Odds</label>
                <input type="number" step="0.01" name="back_odds" value="{back_odds}">

                <label>Back Stake (£)</label>
                <input type="number" step="0.01" name="back_stake" value="{back_stake}">

                <label>Lay Odds</label>
                <input type="number" step="0.01" name="lay_odds" value="{lay_odds}">

                <label>Commission (%)</label>
                <input type="number" step="0.01" name="commission_percent" value="{commission_percent}">

                <button type="submit">
                    Calculate Hedge
                </button>
            </form>

            {result_html}

            <p class="muted">
                Use this for same-selection back/lay hedges.
                Exchange watchlist cards are not guaranteed arbs until checked here.
            </p>

            <p>
                <a href="/">← Back to Pulse</a>
            </p>
        </div>
    </body>
    </html>
    """


@app.get("/settings", response_class=HTMLResponse)
def settings_page():
    settings = load_settings()

    api_key = settings["providers"]["the_odds_api"]["api_key"]
    discord_webhook = settings.get("discord_webhook", "")

    masked_status = "Saved ✅" if api_key else "Missing ❌"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pulse Settings</title>
        <link rel="icon" type="image/png" href="/static/favicon.png">
        <style>
            body {{
                background: #050505;
                color: white;
                font-family: Arial, sans-serif;
                padding: 40px;
            }}
            h1 {{
                color: #ff174f;
                font-size: 42px;
            }}
            .panel {{
                background: #111;
                border: 1px solid #333;
                border-radius: 14px;
                padding: 22px;
                max-width: 760px;
                margin-bottom: 24px;
            }}
            label {{
                display: block;
                margin-bottom: 6px;
                color: #ccc;
                font-weight: bold;
            }}
            input {{
                width: 100%;
                padding: 12px;
                margin-bottom: 18px;
                background: #050505;
                color: white;
                border: 1px solid #444;
                border-radius: 8px;
                box-sizing: border-box;
            }}
            button {{
                background: linear-gradient(90deg, #ff174f, #9b2cff);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 18px;
                font-weight: bold;
                cursor: pointer;
            }}
            a {{
                color: #d066ff;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .muted {{
                color: #aaa;
            }}
        </style>
    </head>

    <body>
        <h1>Pulse Settings</h1>

        <div class="panel">
            <p>The Odds API key status: <strong>{masked_status}</strong></p>

            <form method="post" action="/save-settings">
                <h2>Provider: The Odds API</h2>

                <label>API Key</label>
                <input
                    type="password"
                    name="the_odds_api_key"
                    value="{api_key}"
                    placeholder="Paste your The Odds API key here"
                >

                <h2>Discord</h2>

                <label>Discord Webhook URL</label>
                <input
                    type="password"
                    name="discord_webhook"
                    value="{discord_webhook}"
                    placeholder="Optional Discord webhook"
                >

                <button type="submit">Save Settings</button>
            </form>

            <p class="muted">
                Settings are saved to app/output/settings.json.
            </p>

            <p>
                <a href="/">← Back to Pulse</a>
            </p>
        </div>
    </body>
    </html>
    """


@app.post("/save-settings")
def save_settings_route(
    the_odds_api_key: str = Form(""),
    discord_webhook: str = Form(""),
):
    settings = load_settings()

    settings["providers"]["the_odds_api"]["api_key"] = the_odds_api_key.strip()
    settings["discord_webhook"] = discord_webhook.strip()

    save_settings(settings)

    return RedirectResponse(
        url="/settings",
        status_code=303,
    )


@app.get("/shutdown", response_class=HTMLResponse)
def shutdown():
    save_current_cache()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pulse Shutting Down</title>
        <link rel="icon" type="image/png" href="/static/favicon.png">
        <style>
            body {
                background: #050505;
                color: white;
                font-family: Arial, sans-serif;
                padding: 40px;
            }

            h1 {
                color: #ff174f;
            }
        </style>
    </head>
    <body>
        <h1>Pulse saved and is shutting down...</h1>
        <p>Your latest arbs have been saved.</p>
        <p>You can close this browser tab now.</p>
    </body>
    </html>
    """

    threading.Timer(
        1.0,
        lambda: os._exit(0),
    ).start()

    return html

@app.get("/", response_class=HTMLResponse)
def pulse_home(request: Request):
    dashboard = get_dashboard_data()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "active_page": "home",
            **dashboard,
            "official_stats": get_verified_official_stats(),
            "all_settled_stats": get_all_settled_stats(),
        },
    )

@app.get("/arb", response_class=HTMLResponse)
def dashboard(
    request: Request,
    bankroll: float = Query(100.0),
    min_profit: float = Query(1.0),
    near_threshold: float = Query(-3.0),
    scan: bool = Query(False),
    selected_sports: list[str] = Query(None),
):
    if scan:
        scan_result = run_full_scan(
            sports_to_scan=selected_sports or list(SPORT_OPTIONS.keys()),
            api_key=get_the_odds_api_key(),
            should_pause_callback=should_pause_for_credits,
            save_results_callback=save_scan_results,
            bankroll=bankroll,
            min_profit=min_profit,
            near_threshold=near_threshold,
        )

        SCAN_CACHE["arbs"] = scan_result["arbs"]
        SCAN_CACHE["near_arbs"] = scan_result["near_arbs"]
        SCAN_CACHE["last_scan"] = scan_result["last_scan"]

        SCAN_CACHE["api_remaining"] = scan_result.get(
            "api_remaining",
            SCAN_CACHE.get("api_remaining"),
        )

        SCAN_CACHE["api_used"] = scan_result.get(
            "api_used",
            SCAN_CACHE.get("api_used"),
        )

        for item in SCAN_CACHE["arbs"]:
            item["is_new"] = True

        for item in SCAN_CACHE["near_arbs"]:
            item["is_new"] = True

        save_current_cache()

    checked_sports = selected_sports or ["soccer_epl"]

    sports_html = ""

    for sport_key, sport_name in SPORT_OPTIONS.items():
        checked = "checked" if sport_key in checked_sports else ""

        sports_html += f"""
        <label style="display:inline-block;margin-right:18px;margin-bottom:10px;">
            <input
                type="checkbox"
                name="selected_sports"
                value="{sport_key}"
                {checked}
            >
            {sport_name}
        </label>
        """

    arbs = sorted(
        SCAN_CACHE["arbs"],
        key=lambda item: calculate_pulse_score(
            item,
            item.get("profit_percent", 0),
        )[0],
        reverse=True,
    )

    near_arbs = sorted(
        SCAN_CACHE["near_arbs"],
        key=lambda item: calculate_pulse_score(
            item,
            item.get("profit_percent", 0),
        )[0],
        reverse=True,
    )

    live_arbs = [
        item for item in arbs
        if item.get("is_live")
    ]

    live_near_arbs = [
        item for item in near_arbs
        if item.get("is_live")
    ]

    live_arbs = [
        item for item in live_arbs
        if item.get("profit_percent", 0) > 0
    ]

    live_near_arbs = [
        item for item in live_near_arbs
        if item.get("profit_percent", 0) > 0
    ]

    prematch_arbs = [
        item for item in arbs
        if not item.get("is_live")
    ]

    prematch_near_arbs = [
        item for item in near_arbs
        if not item.get("is_live")
    ]

    print("ARBS:", len(arbs))
    print("NEAR:", len(near_arbs))
    print("LIVE ARBS:", len(live_arbs))
    print("LIVE NEAR:", len(live_near_arbs))
    print("PREMATCH ARBS:", len(prematch_arbs))
    print("PREMATCH NEAR:", len(prematch_near_arbs))

    live_html = ""

    for item in live_arbs:
        live_html += render_result_card(item, "LIVE ARB")

    for item in live_near_arbs:
        live_html += render_result_card(item, "LIVE WATCHLIST")

    arb_html = ""

    for item in prematch_arbs:
        arb_html += render_result_card(item, "ARB")

    near_html = ""

    for item in prematch_near_arbs:
        near_html += render_result_card(item, "NEAR-ARB")

    if not arb_html:
        arb_html = "<p class='muted'>No sportsbook-only true arbs saved yet. Run a scan.</p>"

    if not live_html:
        live_html = "<p class='muted'>No live Pulse opportunities detected yet.</p>"

    if not near_html:
        near_html = "<p class='muted'>No near-arbs or exchange watchlist items saved yet. Run a scan.</p>"

    sport_stats = get_sport_stats()[:5]
    bookmaker_stats = get_bookmaker_stats()[:5]

    sport_html = ""

    for s in sport_stats:
        sport_html += f"""
        <li>
            {s['sport']}
            | Avg {s['avg_profit']}%
            | Best {s['best_profit']}%
            | Hits {s['count']}
        </li>
        """

    book_html = ""

    for b in bookmaker_stats:
        book_html += f"""
        <li>
            {b['bookmaker']}
            | Avg {b['avg_profit']}%
            | Best {b['best_profit']}%
            | Hits {b['count']}
        </li>
        """

    if not sport_html:
        sport_html = "<li>No scan history yet.</li>"

    if not book_html:
        book_html = "<li>No scan history yet.</li>"

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "arb",
            "live_html": live_html,
            "arb_html": arb_html,
            "near_html": near_html,
            "sport_html": sport_html,
            "book_html": book_html,
            "sports_html": sports_html,
            "bankroll": bankroll,
            "min_profit": min_profit,
            "near_threshold": near_threshold,
            "scan_cache": SCAN_CACHE,
        },
    )


@app.get("/sports")
def list_sports():
    api_key = get_the_odds_api_key()

    if not api_key:
        raise HTTPException(
            400,
            "Missing The Odds API key. Add it in Pulse Settings.",
        )

    resp = requests.get(
        "https://api.the-odds-api.com/v4/sports",
        params={"apiKey": api_key},
        timeout=20,
    )

    return resp.json()


@app.get("/arbitrage")
async def get_arbs(
    sport: str = Query("soccer_epl"),
    min_profit: float = 1.0,
    bankroll: float = 100.0,
):
    arbs, near_arbs, api_remaining, api_used = fetch_sport_results(
        sport=sport,
        api_key=get_the_odds_api_key(),
        bankroll=bankroll,
        min_profit=min_profit,
        near_threshold=-999,
    )

    if arbs:
        save_scan_results(arbs)

    return arbs


# threading.Thread(target=background_scanner, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
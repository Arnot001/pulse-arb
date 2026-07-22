from pathlib import Path
import logging
import os
import subprocess
import sys
import threading
import requests
import time

from app.modules.arbitrage.execution.routes import (
    router as execution_router,
)
from app.modules.arbitrage.execution.service import (
    execution_service,
)
from typing import Optional
from app.modules.notifications import (load_notification_settings,save_notification_settings,test_discord_notification,test_telegram_notification,)
from app.modules.performance.profit_engine import simulate_level_stakes
from app.modules.performance.bet_ledger import (
    load_jsonl,
    LEDGER_FILE,
    get_verified_official_stats,
    get_all_settled_stats,
    get_verified_official_each_way_stats,
    get_all_settled_each_way_stats,
    get_bankroll_history,
    get_each_way_bankroll_history,
    get_performance_insights,
)
from app.modules.race_intelligence.output import (get_race_intelligence_dashboard,)
from app.modules.arbitrage.dashboard import (
    get_dashboard as get_horse_arb_dashboard,
)
from app.modules.strategy.engine import get_strategy_lab_data
from app.modules.dashboard import get_dashboard_data
from app.modules.betting.builder import build_bets
from app.modules.football.routes import get_football_leaderboard
from collectors.daily_update import (
    get_mode_update_state,
    is_mode_complete_today,
    run_jobs,
)
from collectors.pulse_live_engine import (LIVE_ENGINE_BUSY,run_loop as run_pulse_live_engine,)
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
app.include_router(execution_router)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

templates = Jinja2Templates(directory="app/templates")

logging.basicConfig(level=logging.INFO)
PULSE_LIVE_THREAD = None
PULSE_LIVE_ENABLED = os.getenv("PULSE_LIVE_ENABLED", "1") == "1"

UPDATE_LOCK = threading.Lock()

UPDATE_STATUS = {
    "running": False,
    "mode": "",
    "current_task": "",
    "percent": 0,
    "bar": "",
    "completed": [],
    "failed": [],
    "total_tasks": 0,
    "completed_count": 0,
    "failed_count": 0,
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
        UPDATE_STATUS["total_tasks"] = 0
        UPDATE_STATUS["completed_count"] = 0
        UPDATE_STATUS["failed_count"] = 0
        UPDATE_STATUS["started_at"] = time.time()
        UPDATE_STATUS["finished_at"] = None
        UPDATE_STATUS["runtime"] = None

    def progress(update_event):
        total = update_event.get("total") or 0

        if update_event["event"] == "start":
            with UPDATE_LOCK:
                UPDATE_STATUS["current_task"] = (
                    update_event["label"]
                )
                UPDATE_STATUS["total_tasks"] = total

        elif update_event["event"] == "finish":
            percent = int(
                (
                    update_event["index"]
                    / max(total, 1)
                ) * 100
            )

            with UPDATE_LOCK:
                UPDATE_STATUS["percent"] = percent
                UPDATE_STATUS["bar"] = (
                    build_progress_bar(percent)
                )

                if update_event["success"]:
                    UPDATE_STATUS["completed"].append(
                        update_event["label"]
                    )
                else:
                    UPDATE_STATUS["failed"].append(
                        update_event["label"]
                    )

                UPDATE_STATUS["completed_count"] = len(
                    UPDATE_STATUS["completed"]
                )
                UPDATE_STATUS["failed_count"] = len(
                    UPDATE_STATUS["failed"]
                )

    summary = run_jobs(
        mode,
        progress_callback=progress,
    )

    finished_at = time.time()
    failed_count = len([
        result
        for result in summary["results"]
        if result.get("success") is not True
    ])

    with UPDATE_LOCK:
        UPDATE_STATUS["running"] = False
        UPDATE_STATUS["current_task"] = (
            "Complete"
            if failed_count == 0
            else "Completed with errors"
        )
        UPDATE_STATUS["percent"] = 100
        UPDATE_STATUS["bar"] = build_progress_bar(100)
        UPDATE_STATUS["finished_at"] = finished_at
        UPDATE_STATUS["runtime"] = summary["runtime"]
        UPDATE_STATUS["total_tasks"] = summary["total"]
        UPDATE_STATUS["completed_count"] = (
            summary["total"] - failed_count
        )
        UPDATE_STATUS["failed_count"] = failed_count


def is_manual_update_running():

    with UPDATE_LOCK:
        return bool(UPDATE_STATUS["running"])

def has_manual_update_completed():
    with UPDATE_LOCK:
        if UPDATE_STATUS["finished_at"] is not None:
            return True

    return is_mode_complete_today("all")

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
        kwargs={
            "is_manual_update_running": is_manual_update_running,
            "has_manual_update_completed": has_manual_update_completed,
        },
        daemon=True,
    )

    PULSE_LIVE_THREAD.start()

    print("Pulse Live Engine plugged in ✅")

@app.on_event("startup")
def start_execution_service():
    execution_service.start()
    print("Pulse Execution Service plugged in ✅")


@app.on_event("shutdown")
def stop_execution_service():
    execution_service.stop()
    print("Pulse Execution Service stopped.")

def start_update(mode, redirect_url="/"):
    with UPDATE_LOCK:
        if UPDATE_STATUS["running"]:
            return RedirectResponse(
                url=f"{redirect_url}?update=already-running",
                status_code=303,
            )

        if LIVE_ENGINE_BUSY.is_set():
            return RedirectResponse(
                url=f"{redirect_url}?update=live-engine-running",
                status_code=303,
            )

        # Reserve the update slot before starting the thread so the
        # live engine cannot begin during this small transition.
        UPDATE_STATUS["running"] = True
        UPDATE_STATUS["mode"] = mode
        UPDATE_STATUS["current_task"] = "Queued..."

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
        status = dict(UPDATE_STATUS)

    persistent = get_mode_update_state(
        status.get("mode") or "all"
    )

    all_state = get_mode_update_state("all")

    status["persistent"] = persistent
    status["all_update"] = all_state
    status["updated_today"] = (
        is_mode_complete_today("all")
    )

    return status


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
def horses(
    request: Request,
    iq_band: Optional[list[str]] = Query(None),
):
    cards = get_horse_dashboard()

    iq_options = [
        {
            "key": "under_70",
            "label": "Below 70",
            "minimum": None,
            "maximum": 69,
        },
        {
            "key": "70_74",
            "label": "70–74",
            "minimum": 70,
            "maximum": 74,
        },
        {
            "key": "75_79",
            "label": "75–79",
            "minimum": 75,
            "maximum": 79,
        },
        {
            "key": "80_84",
            "label": "80–84",
            "minimum": 80,
            "maximum": 84,
        },
        {
            "key": "85_89",
            "label": "85–89",
            "minimum": 85,
            "maximum": 89,
        },
        {
            "key": "90_plus",
            "label": "90+",
            "minimum": 90,
            "maximum": None,
        },
    ]

    allowed_bands = {
        option["key"]
        for option in iq_options
    }

    selected_iq_bands = [
        band
        for band in (iq_band or [])
        if band in allowed_bands
    ]

    total_cards = len(cards)

    if selected_iq_bands:
        selected_options = [
            option
            for option in iq_options
            if option["key"] in selected_iq_bands
        ]

        filtered_cards = []

        for card in cards:
            try:
                score = int(float(card.get("score") or 0))
            except (TypeError, ValueError):
                score = 0

            matches_band = any(
                (
                    option["minimum"] is None
                    or score >= option["minimum"]
                )
                and (
                    option["maximum"] is None
                    or score <= option["maximum"]
                )
                for option in selected_options
            )

            if matches_band:
                filtered_cards.append(card)

        cards = filtered_cards

    return templates.TemplateResponse(
        request,
        "horses.html",
        {
            "cards": cards,
            "active_page": "horses",
            "iq_options": iq_options,
            "selected_iq_bands": selected_iq_bands,
            "visible_card_count": len(cards),
            "total_card_count": total_cards,
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
    

@app.get("/horse-arb", response_class=HTMLResponse)
def horse_arb(request: Request):
    return templates.TemplateResponse(
        request,
        "horse_arb.html",
        {
            "active_page": "horse_arb",
            **get_horse_arb_dashboard(),
        },
    )


@app.get("/arbitrage-intelligence", response_class=HTMLResponse)
def arbitrage_intelligence(request: Request):
    dashboard = get_horse_arb_dashboard()
    stats = dashboard.get("stats") or {}
    market_summary = dashboard.get("market_summary") or {}

    engine_cards = [
        {"key": "back_back", "title": "Back ↔ Back", "eyebrow": "Guaranteed", "description": "Best sportsbook price on every runner, verified as one complete market.", "href": "/horse-arb", "status": "LIVE", "metric": market_summary.get("guaranteed_arbs", 0), "metric_label": "verified arbs"},
        {"key": "back_lay", "title": "Back ↔ Lay", "eyebrow": "Exchange", "description": "Compare sportsbook back odds with exchange lay prices, commission and liability.", "href": "/lay-calculator", "status": "FOUNDATION", "metric": 0, "metric_label": "live opportunities"},
        {"key": "each_way", "title": "Each-Way Arbitrage", "eyebrow": "Win + Place", "description": "Detect win and place pricing mismatches across bookmakers and place terms.", "href": "#", "status": "PLANNED", "metric": 0, "metric_label": "opportunities"},
        {"key": "extra_places", "title": "Extra Places", "eyebrow": "Enhanced Terms", "description": "Identify bookmakers paying deeper places than the standard market.", "href": "#", "status": "PLANNED", "metric": 0, "metric_label": "offers"},
        {"key": "dutching", "title": "Dutching Studio", "eyebrow": "Portfolio", "description": "Build multi-runner coverage with balanced stakes, returns and portfolio risk.", "href": "#", "status": "PLANNED", "metric": 0, "metric_label": "portfolios"},
        {"key": "cross_market", "title": "Cross-Market", "eyebrow": "Market Links", "description": "Compare winner, without favourite, place and related derivative markets.", "href": "#", "status": "PLANNED", "metric": 0, "metric_label": "opportunities"},
        {"key": "boosts", "title": "Boost Finder", "eyebrow": "Enhanced Odds", "description": "Rank bookmaker boosts against the true market and Pulse fair-price estimates.", "href": "#", "status": "PLANNED", "metric": 0, "metric_label": "boosts"},
        {"key": "value", "title": "Value Engine", "eyebrow": "Positive EV", "description": "Find prices above Pulse fair value and track whether the edge is profitable.", "href": "#", "status": "FOUNDATION", "metric": market_summary.get("best_value", 0), "metric_label": "value markets"},
    ]

    return templates.TemplateResponse(
        request,
        "arbitrage_intelligence.html",
        {
            "active_page": "arbitrage_intelligence",
            "engine_cards": engine_cards,
            "arb_dashboard": dashboard,
            "stats": stats,
            "market_summary": market_summary,
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
def performance(
    request: Request,
    score: Optional[int] = Query(None),
    group: str = Query("all"),
):
    allowed_scores = {
        None,
        70,
        75,
        80,
        85,
        90,
    }

    if score not in allowed_scores:
        score = None

    allowed_groups = {
        "all",
        "official",
        "watchlist",
        "predictions",
    }

    if group not in allowed_groups:
        group = "all"

    return templates.TemplateResponse(
        request,
        "performance.html",
        {
            "request": request,
            "active_page": "performance",
            "selected_score": score,
            "selected_group": group,
            "score_options": [
                None,
                70,
                75,
                80,
                85,
                90,
            ],
            "group_options": [
                ("all", "All Picks"),
                ("official", "Official"),
                ("watchlist", "Watchlist"),
                ("predictions", "Predictions"),
            ],
            "official_stats": (
                get_verified_official_stats(
                    min_score=score,
                )
            ),
            "all_stats": get_all_settled_stats(
                min_score=score,
                bet_group=group,
            ),
            "official_ew_stats": (
                get_verified_official_each_way_stats(
                    min_score=score,
                )
            ),
            "all_ew_stats": (
                get_all_settled_each_way_stats(
                    min_score=score,
                    bet_group=group,
                )
            ),
            "bankroll_history": get_bankroll_history(
                min_score=score,
                bet_group=group,
            ),
            "each_way_bankroll_history": (
                get_each_way_bankroll_history(
                    min_score=score,
                    bet_group=group,
                )
            ),
            "insights": get_performance_insights(
                min_score=score,
                bet_group=group,
            ),
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
def pulse_home(
    request: Request,
    notification_status: str = Query(""),
    notification_message: str = Query(""),
):
    dashboard = get_dashboard_data()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "active_page": "home",
            **dashboard,
            "official_stats": (
                get_verified_official_stats()
            ),
            "all_settled_stats": (
                get_all_settled_stats()
            ),
            "notification_settings": (
                load_notification_settings()
            ),
            "notification_status": (
                notification_status
            ),
            "notification_message": (
                notification_message
            ),
            "daily_update_state": (
                get_mode_update_state("all")
            ),
            "updated_today": (
                is_mode_complete_today("all")
            ),
        },
    )

@app.post("/notifications/save")
def save_notifications_route(
    discord_enabled: Optional[str] = Form(None),
    discord_webhook: str = Form(""),
    telegram_enabled: Optional[str] = Form(None),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    official_only: Optional[str] = Form(None),

    notify_horses: Optional[str] = Form(None),
    notify_dogs: Optional[str] = Form(None),
    notify_football: Optional[str] = Form(None),
    notify_arb: Optional[str] = Form(None),
    notify_market_movers: Optional[str] = Form(None),
    notify_settlements: Optional[str] = Form(None),
    notify_performance: Optional[str] = Form(None),
    notify_learning: Optional[str] = Form(None),
    notify_strategy: Optional[str] = Form(None),
    notify_system: Optional[str] = Form(None),
):
    current = load_notification_settings()

    current.update(
        {
            "discord_enabled": (
                discord_enabled is not None
            ),
            "discord_webhook": (
                discord_webhook.strip()
            ),
            "telegram_enabled": (
                telegram_enabled is not None
            ),
            "telegram_bot_token": (
                telegram_bot_token.strip()
            ),
            "telegram_chat_id": (
                telegram_chat_id.strip()
            ),
            "official_only": (
                official_only is not None
            ),
            "modules": {
                "horses": (
                    notify_horses is not None
                ),
                "dogs": (
                    notify_dogs is not None
                ),
                "football": (
                    notify_football is not None
                ),
                "arb": (
                    notify_arb is not None
                ),
                "market_movers": (
                    notify_market_movers
                    is not None
                ),
                "settlements": (
                    notify_settlements
                    is not None
                ),
                "performance": (
                    notify_performance
                    is not None
                ),
                "learning": (
                    notify_learning
                    is not None
                ),
                "strategy": (
                    notify_strategy
                    is not None
                ),
                "system": (
                    notify_system is not None
                ),
            },
        }
    )

    save_notification_settings(
        current
    )

    return RedirectResponse(
        url=(
            "/?notification_status=success"
            "&notification_message="
            "Notification+settings+saved"
        ),
        status_code=303,
    )


@app.post("/notifications/test-discord")
def test_discord_route():
    result = test_discord_notification()

    status = (
        "success"
        if result["success"]
        else "error"
    )

    message = requests.utils.quote(
        result["message"]
    )

    return RedirectResponse(
        url=(
            f"/?notification_status={status}"
            f"&notification_message={message}"
        ),
        status_code=303,
    )


@app.post("/notifications/test-telegram")
def test_telegram_route():
    result = test_telegram_notification()

    status = (
        "success"
        if result["success"]
        else "error"
    )

    message = requests.utils.quote(
        result["message"]
    )

    return RedirectResponse(
        url=(
            f"/?notification_status={status}"
            f"&notification_message={message}"
        ),
        status_code=303,
    )

@app.post("/notifications/save")
def save_notifications_route(
    discord_enabled: Optional[str] = Form(None),
    discord_webhook: str = Form(""),
    telegram_enabled: Optional[str] = Form(None),
    telegram_bot_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    official_only: Optional[str] = Form(None),

    notify_horses: Optional[str] = Form(None),
    notify_dogs: Optional[str] = Form(None),
    notify_football: Optional[str] = Form(None),
    notify_arb: Optional[str] = Form(None),
    notify_market_movers: Optional[str] = Form(None),
    notify_settlements: Optional[str] = Form(None),
    notify_performance: Optional[str] = Form(None),
    notify_learning: Optional[str] = Form(None),
    notify_strategy: Optional[str] = Form(None),
    notify_system: Optional[str] = Form(None),
):
    current = load_notification_settings()

    current.update(
        {
            "discord_enabled": (
                discord_enabled is not None
            ),
            "discord_webhook": (
                discord_webhook.strip()
            ),
            "telegram_enabled": (
                telegram_enabled is not None
            ),
            "telegram_bot_token": (
                telegram_bot_token.strip()
            ),
            "telegram_chat_id": (
                telegram_chat_id.strip()
            ),
            "official_only": (
                official_only is not None
            ),
            "modules": {
                "horses": (
                    notify_horses is not None
                ),
                "dogs": (
                    notify_dogs is not None
                ),
                "football": (
                    notify_football is not None
                ),
                "arb": (
                    notify_arb is not None
                ),
                "market_movers": (
                    notify_market_movers
                    is not None
                ),
                "settlements": (
                    notify_settlements
                    is not None
                ),
                "performance": (
                    notify_performance
                    is not None
                ),
                "learning": (
                    notify_learning
                    is not None
                ),
                "strategy": (
                    notify_strategy
                    is not None
                ),
                "system": (
                    notify_system is not None
                ),
            },
        }
    )

    save_notification_settings(
        current
    )

    return RedirectResponse(
        url=(
            "/?notification_status=success"
            "&notification_message="
            "Notification+settings+saved"
        ),
        status_code=303,
    )


@app.post("/notifications/test-discord")
def test_discord_route():
    result = test_discord_notification()

    status = (
        "success"
        if result["success"]
        else "error"
    )

    message = requests.utils.quote(
        result["message"]
    )

    return RedirectResponse(
        url=(
            f"/?notification_status={status}"
            f"&notification_message={message}"
        ),
        status_code=303,
    )


@app.post("/notifications/test-telegram")
def test_telegram_route():
    result = test_telegram_notification()

    status = (
        "success"
        if result["success"]
        else "error"
    )

    message = requests.utils.quote(
        result["message"]
    )

    return RedirectResponse(
        url=(
            f"/?notification_status={status}"
            f"&notification_message={message}"
        ),
        status_code=303,
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
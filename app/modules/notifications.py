import json
from pathlib import Path

import requests


SETTINGS_FILE = Path("data/settings/notifications.json")


def load_notification_settings():
    defaults = {
        "discord_enabled": False,
        "discord_webhook": "",
        "telegram_enabled": False,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "official_only": False,
    }

    if not SETTINGS_FILE.exists():
        return defaults

    try:
        data = json.loads(
            SETTINGS_FILE.read_text(encoding="utf-8")
        )

        defaults.update(data)
    except Exception as exc:
        print(f"Notification settings error: {exc}")

    return defaults


def format_profit(bet):
    profit = bet.get("profit")

    if profit is None:
        return "No captured odds"

    try:
        profit = float(profit)
    except Exception:
        return "Unknown"

    return f"{profit:+.2f} pts"


def format_result_line(bet):
    won = bet.get("won") is True
    position = bet.get("result_position")
    horse = bet.get("horse") or "Unknown horse"
    course = bet.get("course") or "Unknown course"
    race_time = bet.get("race_time") or ""
    sp = bet.get("sp") or "Unknown"
    pulse_score = bet.get("pulse_score")
    bookmaker = bet.get("bookmaker") or "No captured bookmaker"
    captured_odds = bet.get("best_odds") or "No captured odds"

    outcome = "WINNER" if won else f"Finished {position or '?'}"

    lines = [
        f"{'WIN' if won else 'LOSS'} | {horse}",
        f"{course} {race_time}".strip(),
        f"Result: {outcome}",
        f"SP: {sp}",
    ]

    if pulse_score is not None:
        lines.append(f"Pulse IQ: {pulse_score}")

    lines.extend([
        f"Captured: {captured_odds} ({bookmaker})",
        f"Profit: {format_profit(bet)}",
    ])

    return "\n".join(lines)


def build_summary_message(bets):
    winners = sum(
        1 for bet in bets
        if bet.get("won") is True
    )

    priced_profit = sum(
        float(bet.get("profit") or 0)
        for bet in bets
        if bet.get("profit") is not None
    )

    sections = [
        "PULSE RESULTS UPDATE",
        "",
        f"Settled: {len(bets)}",
        f"Winners: {winners}",
        f"Priced profit: {priced_profit:+.2f} pts",
        "",
    ]

    for bet in bets:
        sections.append(format_result_line(bet))
        sections.append("-" * 30)

    return "\n".join(sections).rstrip("-\n ")


def send_discord_message(webhook_url, message):
    response = requests.post(
        webhook_url,
        json={"content": message[:1900]},
        timeout=20,
    )

    response.raise_for_status()


def send_telegram_message(bot_token, chat_id, message):
    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message[:4000],
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    response.raise_for_status()


def send_new_settlement_notifications(bets):
    if not bets:
        return {
            "sent": False,
            "discord": False,
            "telegram": False,
            "reason": "No newly settled bets",
        }

    settings = load_notification_settings()

    if settings.get("official_only"):
        bets = [
            bet for bet in bets
            if bet.get("official_bet") is True
        ]

    if not bets:
        return {
            "sent": False,
            "discord": False,
            "telegram": False,
            "reason": "No qualifying newly settled bets",
        }

    message = build_summary_message(bets)

    discord_sent = False
    telegram_sent = False
    errors = []

    if (
        settings.get("discord_enabled")
        and settings.get("discord_webhook")
    ):
        try:
            send_discord_message(
                settings["discord_webhook"],
                message,
            )
            discord_sent = True
        except Exception as exc:
            errors.append(f"Discord: {exc}")

    if (
        settings.get("telegram_enabled")
        and settings.get("telegram_bot_token")
        and settings.get("telegram_chat_id")
    ):
        try:
            send_telegram_message(
                settings["telegram_bot_token"],
                settings["telegram_chat_id"],
                message,
            )
            telegram_sent = True
        except Exception as exc:
            errors.append(f"Telegram: {exc}")

    return {
        "sent": discord_sent or telegram_sent,
        "discord": discord_sent,
        "telegram": telegram_sent,
        "errors": errors,
        "bets": len(bets),
    }
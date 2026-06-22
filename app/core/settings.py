import json
from pathlib import Path


SETTINGS_FILE = Path("app/output/settings.json")


DEFAULT_SETTINGS = {
    "providers": {
        "the_odds_api": {
            "enabled": True,
            "api_key": "",
        }
    },
    "discord_webhook": "",
}


def ensure_settings():
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)


def load_settings():
    ensure_settings()

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
from app.modules.race_intelligence.signals import signal_summary


def get_race_intelligence_dashboard():
    signals = []

    return {
        "signals": signals,
        "summary": signal_summary(signals),
        "status": "READY",
    }
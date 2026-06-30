from pathlib import Path

from app.modules.horses.market_events import get_market_events
from app.modules.horses.output import get_top_horses
from app.modules.horses.performance import get_latest_performance_report


def count_files(folder, pattern="*"):
    path = Path(folder)

    if not path.exists():
        return 0

    return len(list(path.glob(pattern)))


def count_jsonl_lines(folder):
    path = Path(folder)

    if not path.exists():
        return 0

    total = 0

    for file in path.glob("*.jsonl"):
        with file.open(encoding="utf-8") as f:
            total += sum(1 for line in f if line.strip())

    return total


def get_dashboard_data():
    performance = get_latest_performance_report()
    market_events = get_market_events(limit=5)
    top_horses = get_top_horses(limit=5)

    return {
        "horse_intelligence_count": count_files(
            "data/horses/intelligence",
            "*.json",
        ),
        "market_event_count": count_jsonl_lines(
            "data/horses/market_events",
        ),
        "runner_record_count": count_jsonl_lines(
            "data/horses/runner_records",
        ),
        "horse_profile_count": count_files(
            "data/horses/profiles",
            "*.json",
        ),
        "learning_report_count": count_jsonl_lines(
            "data/horses/market_learning_reports",
        ),
        "market_events": market_events,
        "top_horses": top_horses,
        "performance": performance,
    }
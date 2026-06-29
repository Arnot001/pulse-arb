import json
from pathlib import Path

REPORT_DIR = Path("data/horses/performance_reports")


def get_latest_performance_report():

    reports = sorted(REPORT_DIR.glob("*.json"))

    if not reports:
        return {
            "date": "-",
            "races_checked": 0,
            "top_1_rate": 0,
            "top_2_rate": 0,
            "top_3_rate": 0,
            "races": [],
        }

    with reports[-1].open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)
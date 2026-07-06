import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.modules.odds.url_builder import build_oddschecker_url
from app.modules.odds.url_builder import build_oddschecker_url


tests = [
    ("Ayr", "3:15", "Altareq"),
    ("Ayr", "5:00", "Celeborn"),
    ("Southwell AW", "1:50", "Lightning Glory"),
]

for course, time, horse in tests:
    print(course, time, horse)
    print(build_oddschecker_url(course, time, horse))
    print()
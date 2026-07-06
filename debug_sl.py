import json
import re
import requests

html = requests.get(
    "https://www.sportinglife.com/racing/results",
    headers={"User-Agent": "Mozilla/5.0"},
).text

match = re.search(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    html,
    re.S,
)

data = json.loads(match.group(1))

meetings = data["props"]["pageProps"]["meetings"]

print("Meetings:", len(meetings))

for meeting in meetings:
    for race in meeting.get("races", []):
        print("\n========================")
        print(race.keys())
        print(json.dumps(race, indent=2)[:4000])
        raise SystemExit
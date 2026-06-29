import json
import re
import requests


URL = "https://www.sportinglife.com/racing/results/yesterday"


response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20,
)

html = response.text

match = re.search(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    html,
    flags=re.DOTALL,
)

if not match:
    print("No __NEXT_DATA__ found")
    raise SystemExit

data = json.loads(match.group(1))

meetings = data["props"]["pageProps"].get("meetings", [])

print("Meetings found:", len(meetings))

if not meetings:
    raise SystemExit

meeting = meetings[0]

print("\nMeeting keys:")
print(meeting.keys())

print("\nMeeting name:")
print(meeting.get("course_name") or meeting.get("name") or meeting.get("meeting_name"))

races = meeting.get("races", [])

print("\nRaces found in first meeting:", len(races))

if not races:
    raise SystemExit

print("\nFirst race keys:")
print(races[0].keys())

print("\nFirst race JSON:")
print(json.dumps(races[0], indent=2)[:12000])
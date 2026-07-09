import json
import requests


URL = "https://sports.williamhill.com/data/rmp01/api/v2/desktop/horse-racing/en-gb/region-competitions/all/today"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://sports.williamhill.com/betting/en-gb/horse-racing",
}

r = requests.get(URL, headers=headers, timeout=20)

print("Status:", r.status_code)
print("Content-Type:", r.headers.get("content-type"))
print("Length:", len(r.text))
print("-" * 60)

try:
    data = r.json()
    print(json.dumps(data, indent=2)[:8000])
except Exception:
    print(r.text[:8000])
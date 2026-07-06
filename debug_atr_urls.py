import requests

urls = [
    "https://www.attheraces.com/results/05-July-2026",
    "https://www.attheraces.com/results/2026-07-05",
    "https://www.attheraces.com/results/2026-07-05/Southwell",
]

for url in urls:
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    print(url, r.status_code, "Sixpack" in r.text, "Southwell" in r.text, len(r.text))
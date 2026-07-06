import requests
from bs4 import BeautifulSoup

html = requests.get(
    "https://www.attheraces.com/results/yesterday",
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20,
).text

print("HTML length:", len(html))
print("Contains Sixpack:", "Sixpack" in html)
print("Contains Southwell:", "Southwell" in html)
print(html[:1000])

soup = BeautifulSoup(html, "html.parser")
lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]

for i, line in enumerate(lines):
    if "Southwell" in line or "Sixpack" in line or "17:55" in line:
        print("\n--- MATCH", i, "---")
        print("\n".join(lines[max(0, i-20):i+40]))
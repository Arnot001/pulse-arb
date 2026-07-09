import re
import requests
from bs4 import BeautifulSoup


URL = "https://www.attheraces.com/racecard/Carlisle/10-July-2026/1400"


def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


response = requests.get(
    URL,
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=20,
)

print("STATUS:", response.status_code)
print("URL:", response.url)
print("LENGTH:", len(response.text))

soup = BeautifulSoup(response.text, "html.parser")
text = clean_text(soup.get_text(" "))

print(text[:5000])
print("\n\nSearching for likely odds...")

keywords = [
    "Leopards Rock",
    "5/2",
    "11/4",
    "SP",
    "Odds",
    "Price",
]

for keyword in keywords:
    print(f"{keyword}: {keyword.lower() in text.lower()}")
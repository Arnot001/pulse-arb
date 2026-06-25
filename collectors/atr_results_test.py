import re
import requests
from bs4 import BeautifulSoup


URL = "https://www.attheraces.com/results"


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
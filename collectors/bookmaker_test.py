import requests

URL = "https://sports.williamhill.com/betting/en-gb/horse-racing"

headers = {
    "User-Agent": "Mozilla/5.0",
}

r = requests.get(URL, headers=headers, timeout=20)

print("Status:", r.status_code)
print("Length:", len(r.text))
print(r.text[:1000])

text = r.text.lower()

for term in [
    "horse-racing",
    "carlisle",
    "doncaster",
    "leopards rock",
    "odds",
    "price",
    "event",
    "market",
]:
    print(term, term in text)
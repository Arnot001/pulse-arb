import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.theracingapi.com/v1"

auth = (
    os.getenv(aJ4eOCq9cPHDUymuCedLUaMH),
    os.getenv(NqpiI0D042rC959FxjT20hPV),
)

tests = [
    "/results",
    "/results/free",
    "/racecards/results",
    "/racecards",
    "/horses/results",
    "/race",
]

for endpoint in tests:
    url = BASE + endpoint

    try:
        r = requests.get(url, auth=auth, timeout=20)

        print("=" * 60)
        print(endpoint)
        print("Status:", r.status_code)
        print(r.text[:500])

    except Exception as e:
        print(endpoint, e)
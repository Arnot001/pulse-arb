import json
import re
import requests
from bs4 import BeautifulSoup

url = "https://www.bbc.co.uk/sport/horse-racing/race/p-1571222"

html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20).text
soup = BeautifulSoup(html, "html.parser")

match = re.search(r'window\.__INITIAL_DATA__="(.*?)";', html)

if not match:
    print("No __INITIAL_DATA__ found")
    raise SystemExit

raw = match.group(1)
decoded = raw.encode("utf-8").decode("unicode_escape")
data = json.loads(decoded)

print("Parsed __INITIAL_DATA__ OK")
print(type(data))
print(data.keys())

dump = json.dumps(data, indent=2)
print("horseName location:", dump.find("horseName"))
print(dump[dump.find("horseName") - 1000:dump.find("horseName") + 3000])
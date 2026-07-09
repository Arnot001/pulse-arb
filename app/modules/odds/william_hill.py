import requests
from datetime import datetime


TODAY_URL = "https://sports.williamhill.com/data/rmp01/api/v2/desktop/horse-racing/en-gb/region-competitions/all/today"
EVENT_URL = "https://sports.williamhill.com/data/rmp01/api/v2/desktop/horse-racing/en-gb/events/{event_id}?variant=short"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://sports.williamhill.com/betting/en-gb/horse-racing",
}


def fraction_to_decimal(num, den):
    try:
        return round((float(num) / float(den)) + 1, 3)
    except Exception:
        return None


def normalise(value):
    value = str(value or "").lower().strip()

    for suffix in ["(aw)", "(gb)", "(ire)", "(fr)", "(usa)", "(aus)"]:
        value = value.replace(suffix, "")

    for char in ["'", "’", "-", ".", ",", "(", ")"]:
        value = value.replace(char, " ")

    value = " ".join(value.split())

    return value


def normalise_time(value):
    value = str(value or "").strip()
    if not value:
        return ""

    parts = value.split(":")
    if len(parts) != 2:
        return value

    hour = int(parts[0])
    minute = parts[1].zfill(2)

    if hour > 12:
        hour -= 12

    return f"{hour}:{minute}"


def get_today_events():
    r = requests.get(TODAY_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()

    events = []

    for region in data.get("regionCompetitions", []):
        for competition in region.get("competitions", []):
            for event in competition.get("events", []):
                events.append(event)

    return events


def find_event_id(course, race_time):
    course_key = normalise(course)
    time_key = normalise_time(race_time)

    for event in get_today_events():
        name = normalise(event.get("originalEventName"))
        event_time = normalise_time(event.get("timeString"))

        if event_time == time_key and course_key in name:
            return event.get("id")

    return None


def get_event(event_id):
    url = EVENT_URL.format(event_id=event_id)
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get("event", {})


def get_best_odds(course, race_time, horse):
    event_id = find_event_id(course, race_time)

    if not event_id:
        return {
            "success": False,
            "horse": horse,
            "url": TODAY_URL,
            "snapshot_time": datetime.now().isoformat(timespec="seconds"),
            "best_odds": None,
            "best_odds_decimal": None,
            "bookmaker": "William Hill",
            "error": "William Hill event not found",
        }

    event = get_event(event_id)
    horse_key = normalise(horse)

    for runner in event.get("topSelections", []):
        if normalise(runner.get("name")) != horse_key:
            continue

        num = runner.get("priceNum")
        den = runner.get("priceDen")

        if not num or not den:
            continue

        return {
            "success": True,
            "horse": horse,
            "url": EVENT_URL.format(event_id=event_id),
            "snapshot_time": datetime.now().isoformat(timespec="seconds"),
            "best_odds": f"{num}/{den}",
            "best_odds_decimal": fraction_to_decimal(num, den),
            "bookmaker": "William Hill",
            "odds_source": "william_hill",
            "event_id": event_id,
            "price_history": runner.get("priceHistory", []),
            "error": None,
        }

    return {
        "success": False,
        "horse": horse,
        "url": EVENT_URL.format(event_id=event_id),
        "snapshot_time": datetime.now().isoformat(timespec="seconds"),
        "best_odds": None,
        "best_odds_decimal": None,
        "bookmaker": "William Hill",
        "odds_source": "william_hill",
        "event_id": event_id,
        "error": "Horse not found in William Hill event",
    }


if __name__ == "__main__":
    print(get_best_odds("Newmarket", "1:50", "Del Maro"))
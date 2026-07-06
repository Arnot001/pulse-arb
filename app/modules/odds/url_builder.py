import re


def slugify(value):
    value = str(value or "").lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"\(.*?\)", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalise_time(time_value):
    value = str(time_value or "").strip()

    if not value:
        return ""

    parts = value.split(":")

    if len(parts) != 2:
        return value

    hour = int(parts[0])
    minute = parts[1].zfill(2)

    if hour < 10:
        hour += 12

    return f"{hour}:{minute}"


def build_oddschecker_url(course, race_time, horse):
    course_slug = slugify(course)
    horse_slug = slugify(horse)
    time_slug = normalise_time(race_time)

    return (
        f"https://www.oddschecker.com/horse-racing/"
        f"{course_slug}/{time_slug}/winner"
        f"?selectionName={horse_slug}"
    )
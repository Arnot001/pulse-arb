def to_int(value):
    try:
        if value in (None, "", "-", "NR"):
            return None
        return int(value)
    except Exception:
        return None


def to_float(value):
    try:
        if value in (None, "", "-", "NR"):
            return None
        return float(value)
    except Exception:
        return None
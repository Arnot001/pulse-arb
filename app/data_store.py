from pathlib import Path
from datetime import datetime, timezone
import json

DATA_DIR = Path("data")


def get_week_key():
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def append_jsonl(sport, data_type, record):
    week_key = get_week_key()

    folder = DATA_DIR / sport / data_type
    folder.mkdir(parents=True, exist_ok=True)

    file_path = folder / f"{week_key}.jsonl"

    record = dict(record)
    record["_stored_at"] = datetime.now(timezone.utc).isoformat()

    with file_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(record, ensure_ascii=False)
            + "\n"
        )

    return file_path
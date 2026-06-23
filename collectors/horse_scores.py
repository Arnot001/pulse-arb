import json
from pathlib import Path

from app.data_store import get_week_key
from app.modules.horses.scoring import calculate_horse_score


def show_top_horses(limit=20):
    week_key = get_week_key()
    file_path = Path("data") / "horses" / "runner_records" / f"{week_key}.jsonl"

    if not file_path.exists():
        print(f"No runner records found: {file_path}")
        return

    scored = []
    seen = set()

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            runner = json.loads(line)

            key = f'{runner.get("race_id")}:{runner.get("horse_id")}'
            if key in seen:
                continue
            seen.add(key)

            result = calculate_horse_score(runner)

            scored.append({
                **runner,
                "pulse_score": result["pulse_score"],
                "notes": result["notes"],
            })

    scored.sort(key=lambda x: x["pulse_score"], reverse=True)

    print("=" * 80)
    print("PULSE HORSES - TOP RATED")
    print("=" * 80)

    for runner in scored[:limit]:
        print(
            f'{runner["pulse_score"]:>3} | '
            f'{runner.get("horse")} | '
            f'{runner.get("course")} {runner.get("off_time")} | '
            f'Form: {runner.get("form")} | '
            f'Notes: {", ".join(runner.get("notes", []))}'
        )


if __name__ == "__main__":
    show_top_horses()
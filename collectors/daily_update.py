import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


UPDATE_STATE_FILE = Path("data/system/update_state.json")


HORSE_DATA_JOBS = [
    {"label": "Horse Racecards", "module": "collectors.real_horses"},
    {"label": "Clean Horse Racecards", "module": "collectors.clean_horse_racecards"},
    {"label": "Horse Scores", "module": "collectors.save_horse_scores"},
    {"label": "Horse Odds Snapshots", "module": "collectors.horse_odds_snapshots"},

    # Critical: turn today's snapshots into tracked ledger bets.
    {"label": "Update Bet Ledger", "module": "app.modules.performance.bet_ledger"},

    {"label": "Trainer Rankings", "module": "collectors.trainer_rankings"},
    {"label": "Jockey Rankings", "module": "collectors.jockey_rankings"},
    {"label": "Horse Profiles", "module": "collectors.build_horse_profiles"},
    {"label": "Enrich Horse Profiles", "module": "collectors.enrich_horse_profiles"},
    {"label": "Race Intelligence", "module": "collectors.build_race_intelligence"},
]


RESULT_AND_PERFORMANCE_JOBS = [
    {"label": "Live Results Update", "module": "collectors.update_market_results"},
    {"label": "BBC Horse Results", "module": "collectors.bbc_horse_results"},
    {"label": "Sporting Life Results", "module": "collectors.sporting_life_results"},
    {"label": "Settle Bet Ledger", "module": "app.modules.performance.settlement"},
    {"label": "Pulse Performance", "module": "collectors.analyse_pulse_performance"},
    {"label": "Learn From Results", "module": "collectors.learn_from_results"},
    {"label": "Learning Factors", "module": "collectors.analyse_learning_factors"},
]


DOG_JOBS = [
    {"label": "Dog Racecards", "module": "collectors.dogs"},
    {"label": "Dog Results", "module": "collectors.dog_results"},
    {"label": "Dog Runner Records", "module": "collectors.dog_runner_records"},
    {"label": "Dog History", "module": "collectors.build_dog_history"},
]


FOOTBALL_JOBS = [
    {"label": "Football Fixtures", "module": "collectors.football"},
    {"label": "Football Results", "module": "collectors.football_results"},
    {"label": "Football Team History", "module": "collectors.build_team_history"},
    {"label": "Football IQ", "module": "collectors.football_iq"},
]


JOBS = {
    "horses": HORSE_DATA_JOBS + RESULT_AND_PERFORMANCE_JOBS,
    "dogs": DOG_JOBS,
    "football": FOOTBALL_JOBS,
    "performance": [
        {"label": "Update Bet Ledger", "module": "app.modules.performance.bet_ledger"},
        *RESULT_AND_PERFORMANCE_JOBS,
    ],
    "settlement": [
        {"label": "Update Bet Ledger", "module": "app.modules.performance.bet_ledger"},
        {"label": "BBC Horse Results", "module": "collectors.bbc_horse_results"},
        {"label": "Sporting Life Results", "module": "collectors.sporting_life_results"},
        {"label": "Settle Bet Ledger", "module": "app.modules.performance.settlement"},
        {"label": "Pulse Performance", "module": "collectors.analyse_pulse_performance"},
    ],
}


JOBS["all"] = (
    HORSE_DATA_JOBS
    + DOG_JOBS
    + FOOTBALL_JOBS
    + RESULT_AND_PERFORMANCE_JOBS
)


def get_jobs(mode):
    return JOBS.get(mode, [])


def default_update_state():
    return {
        "version": 1,
        "modes": {},
    }


def load_update_state():
    if not UPDATE_STATE_FILE.exists():
        return default_update_state()

    try:
        data = json.loads(
            UPDATE_STATE_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return default_update_state()

    if not isinstance(data, dict):
        return default_update_state()

    data.setdefault("version", 1)
    data.setdefault("modes", {})

    return data


def save_update_state(state):
    UPDATE_STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = UPDATE_STATE_FILE.with_suffix(
        ".json.tmp"
    )

    temporary_file.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_file.replace(UPDATE_STATE_FILE)


def record_update_summary(summary):
    now = datetime.now()
    results = summary.get("results") or []

    completed = [
        result.get("label")
        for result in results
        if result.get("success") is True
    ]

    failed = [
        result.get("label")
        for result in results
        if result.get("success") is not True
    ]

    state = load_update_state()
    state["modes"][summary["mode"]] = {
        "date": now.date().isoformat(),
        "completed_at": now.isoformat(
            timespec="seconds"
        ),
        "success": not failed,
        "total": summary.get("total", len(results)),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "completed": completed,
        "failed": failed,
        "runtime": summary.get("runtime"),
    }

    save_update_state(state)

    return state["modes"][summary["mode"]]


def get_mode_update_state(mode):
    return (
        load_update_state()
        .get("modes", {})
        .get(mode)
    )


def is_mode_complete_today(mode):
    mode_state = get_mode_update_state(mode)

    if not mode_state:
        return False

    return (
        mode_state.get("date")
        == datetime.now().date().isoformat()
        and mode_state.get("success") is True
    )


def run_jobs(mode, progress_callback=None):
    jobs = get_jobs(mode)
    total = len(jobs)
    results = []
    started_at = time.time()

    for index, job in enumerate(jobs, start=1):
        label = job["label"]
        module = job["module"]
        job_started = time.time()

        print("=" * 70, flush=True)
        print(f"[{index}/{total}] {label}", flush=True)
        print(f"Module: {module}", flush=True)
        print("=" * 70, flush=True)

        if progress_callback:
            progress_callback(
                {
                    "event": "start",
                    "index": index,
                    "total": total,
                    "label": label,
                    "module": module,
                }
            )

        try:
            completed = subprocess.run(
                [sys.executable, "-m", module],
                text=True,
                capture_output=True,
                check=False,
            )

            if completed.stdout:
                print(completed.stdout, end="", flush=True)

            if completed.stderr:
                print(
                    completed.stderr,
                    end="",
                    file=sys.stderr,
                    flush=True,
                )

            success = completed.returncode == 0

            result = {
                "label": label,
                "module": module,
                "success": success,
                "returncode": completed.returncode,
                "stdout": completed.stdout or "",
                "stderr": completed.stderr or "",
            }

        except Exception as exc:
            success = False

            result = {
                "label": label,
                "module": module,
                "success": False,
                "returncode": 999,
                "stdout": "",
                "stderr": str(exc),
            }

            print(f"FAILED: {exc}", flush=True)

        result["runtime"] = round(
            time.time() - job_started,
            2,
        )

        results.append(result)

        status = "OK" if success else "FAILED"
        print(
            f"{status} | {label} | "
            f"{result['runtime']}s",
            flush=True,
        )

        if progress_callback:
            progress_callback(
                {
                    "event": "finish",
                    "index": index,
                    "total": total,
                    "label": label,
                    "module": module,
                    "success": success,
                    "runtime": result["runtime"],
                    "result": result,
                }
            )

    finished_at = time.time()

    summary = {
        "mode": mode,
        "total": total,
        "results": results,
        "runtime": round(
            finished_at - started_at,
            1,
        ),
    }

    summary["persistent_state"] = record_update_summary(
        summary
    )

    return summary


if __name__ == "__main__":
    summary = run_jobs("all")

    print("=" * 70)
    print("PULSE IQ DAILY UPDATE COMPLETE")
    print("=" * 70)

    for result in summary["results"]:
        status = "OK" if result["success"] else "FAILED"
        print(
            f"{status:<7}"
            f"{result['runtime']:>8}s   "
            f"{result['label']}"
        )

    print("-" * 70)
    print(f"Total runtime: {summary['runtime']}s")
    print(f"State file: {UPDATE_STATE_FILE}")
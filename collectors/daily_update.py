import subprocess
import sys
import time


JOBS = {
    "horses": [
        {
            "label": "Horse Racecards",
            "module": "collectors.real_horses",
        },
        {
            "label": "Clean Horse Racecards",
            "module": "collectors.clean_horse_racecards",
        },
        {
            "label": "Horse Scores",
            "module": "collectors.save_horse_scores",
        },
        {
            "label": "Trainer Rankings",
            "module": "collectors.trainer_rankings",
        },
        {
            "label": "Jockey Rankings",
            "module": "collectors.jockey_rankings",
        },
    ],

    "dogs": [
        {
            "label": "Dog Racecards",
            "module": "collectors.dogs",
        },
        {
            "label": "Dog Results",
            "module": "collectors.dog_results",
        },
                {
            "label": "Dog Runner Records",
            "module": "collectors.dog_runner_records",
        },
        {
            "label": "Dog History",
            "module": "collectors.build_dog_history",
        },
    ],

                "football": [
        {
            "label": "Football Fixtures",
            "module": "collectors.football",
        },
        {
            "label": "Football Results",
            "module": "collectors.football_results",
        },
        {
            "label": "Football Team History",
            "module": "collectors.build_team_history",
        },
        {
            "label": "Football IQ",
            "module": "collectors.football_iq",
        },
    ],
}


JOBS["all"] = (
    JOBS["horses"]
    + JOBS["dogs"]
    + JOBS["football"]
)


def get_jobs(mode):
    return JOBS.get(mode, [])


def run_jobs(mode, progress_callback=None):
    jobs = get_jobs(mode)
    total = len(jobs)
    results = []
    started_at = time.time()

    for index, job in enumerate(jobs, start=1):
        label = job["label"]
        module = job["module"]

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

            success = completed.returncode == 0

            result = {
                "label": label,
                "module": module,
                "success": success,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
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

        results.append(result)

        if progress_callback:
            progress_callback(
                {
                    "event": "finish",
                    "index": index,
                    "total": total,
                    "label": label,
                    "module": module,
                    "success": success,
                    "result": result,
                }
            )

    finished_at = time.time()

    return {
        "mode": mode,
        "total": total,
        "results": results,
        "runtime": round(finished_at - started_at, 1),
    }


if __name__ == "__main__":
    summary = run_jobs("all")

    print("=" * 70)
    print("PULSE IQ DAILY UPDATE COMPLETE")
    print("=" * 70)

    for result in summary["results"]:
        status = "OK" if result["success"] else "FAILED"
        print(f"{status} | {result['label']} | {result['module']}")

    print(f"Runtime: {summary['runtime']}s")
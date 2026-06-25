import subprocess
import sys


STEPS = [
    ("Fetch today's racecards", ["collectors.real_horses"]),
    ("Clean racecards into runner records", ["collectors.clean_horse_racecards"]),
    ("Save fresh Pulse scores", ["collectors.save_horse_scores"]),
]


def run_step(label, module):
    print("=" * 70)
    print(label)
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, "-m", module[0]],
        text=True,
    )

    if result.returncode != 0:
        print(f"FAILED: {label}")
        sys.exit(result.returncode)


def main():
    print("🐎 PULSE HORSES DAILY UPDATE")
    print("Fetching racecards, cleaning runners, and rebuilding scores.")

    for label, module in STEPS:
        run_step(label, module)

    print("=" * 70)
    print("✅ Pulse Horses daily update complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
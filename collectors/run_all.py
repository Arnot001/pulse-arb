from collectors.football import collect_football_fixtures
from collectors.real_horses import collect_real_horse_racecards
from collectors.clean_horse_racecards import clean_horse_racecards
from collectors.save_horse_scores import save_horse_scores
from collectors.trainer_rankings import build_trainer_rankings
from collectors.jockey_rankings import build_jockey_rankings
from collectors.dogs import collect_dog_racecards


def run_all_collectors():
    print("=" * 50)
    print("PULSE DATA CORE")
    print("=" * 50)

    collect_football_fixtures()

    collect_real_horse_racecards()
    clean_horse_racecards()
    save_horse_scores()
    build_trainer_rankings()
    build_jockey_rankings()

    collect_dog_racecards()

    print("=" * 50)
    print("COLLECTION COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_all_collectors()
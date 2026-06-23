from app.modules.horses.leaderboards import (
    get_top_trainers,
    get_top_jockeys,
)


def get_leaderboard_data():
    return {
        "trainers": get_top_trainers(),
        "jockeys": get_top_jockeys(),
    }
import asyncio
from core import database


def _run(coro):
    return asyncio.run(coro)


def _setup_db(tmp_path):
    _run(database.init_db(str(tmp_path / "test.db")))


def _record(user_id, score, guild_id=1, user_name=None):
    _run(database.record_score(
        guild_id, 100, user_id, user_name or f"user{user_id}",
        "question", "response", score,
    ))


def test_top_scores_uses_best_score_per_user(tmp_path):
    _setup_db(tmp_path)
    _record(1, 40.0)
    _record(1, 75.5)
    _record(2, 60.0)
    _record(3, 10.0)
    _record(1, 20.0)

    top = _run(database.get_top_scores(1))
    assert [(e["user_id"], e["score"]) for e in top] == [(1, 75.5), (2, 60.0), (3, 10.0)]


def test_top_scores_limit_and_guild_isolation(tmp_path):
    _setup_db(tmp_path)
    for user_id in range(1, 16):
        _record(user_id, float(user_id))
    _record(99, 100.0, guild_id=2)

    top = _run(database.get_top_scores(1, limit=10))
    assert len(top) == 10
    assert top[0]["user_id"] == 15
    assert top[-1]["user_id"] == 6
    assert all(e["user_id"] != 99 for e in top)


def test_top_scores_tie_goes_to_first(tmp_path):
    _setup_db(tmp_path)
    _record(1, 50.0)
    _record(2, 50.0)

    top = _run(database.get_top_scores(1))
    assert [e["user_id"] for e in top] == [1, 2]


def test_leaderboard_config(tmp_path):
    _setup_db(tmp_path)
    assert _run(database.get_leaderboard_config(1)) is None

    _run(database.set_leaderboard_channel(1, 500))
    _run(database.set_leaderboard_message(1, 900))
    assert _run(database.get_leaderboard_config(1)) == {"channel_id": 500, "message_id": 900}

    # Moving the leaderboard to a new channel forgets the old message
    _run(database.set_leaderboard_channel(1, 600))
    assert _run(database.get_leaderboard_config(1)) == {"channel_id": 600, "message_id": None}

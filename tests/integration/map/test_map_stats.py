"""Map stats and leaderboards.

Scope:
- Stats and leaderboards: seed guesses and assert ordering, ties, and the
  per-game leaderboard.

Local helpers build UserMapStats/MapStats/Guess rows directly via the ORM
(tests/integration/map/conftest.py is owned by another agent and is
deliberately empty right now), mirroring the shape api/admin's
scores/recalculate would produce rather than replaying full game sessions.
"""

import pytest

from models.db import db
from models.session import Guess
from models.stats import MapStats, UserMapStats
from tests.factories import make_base_rules, make_location, make_map, make_round, make_session, make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration

LEADERBOARD_URL = "/api/map/leaderboard"
LEADERBOARD_GAME_URL = "/api/map/leaderboard/game"
STATS_URL = "/api/map/stats"


def _seed_leaderboard_entry(game_map, user, base_rules, score, rounds=5, avg_time=10.0,
                             avg_distance=100.0, nmpz=False):
    """A UserMapStats row for `user` on `game_map`, backed by a real Session
    (high_session_id must be non-null for the leaderboard route to include
    the row at all)."""
    session = make_session(host=user, base_rules=base_rules)
    stats = UserMapStats(
        user_id=user.id, map_id=game_map.id, nmpz=nmpz,
        total_time=int(avg_time * rounds), total_score=score * rounds,
        total_distance=avg_distance * rounds, total_guesses=rounds,
        high_average_score=score, high_average_distance=avg_distance,
        high_average_time=avg_time, high_round_number=rounds,
        high_session_id=session.id,
    )
    db.session.add(stats)
    db.session.commit()
    return stats


def _build_session_with_guesses(game_map, user, base_rules, guesses):
    """A Session with one Round + Guess per entry in `guesses` (each a dict
    with round_lat/round_lng for the round's location and lat/lng/distance/
    score/time for the guess itself), in round order."""
    session = make_session(host=user, base_rules=base_rules)
    for i, g in enumerate(guesses, start=1):
        location = make_location(latitude=g["round_lat"], longitude=g["round_lng"])
        round_ = make_round(session=session, location=location, base_rules=base_rules, round_number=i)
        db.session.add(Guess(
            user_id=user.id, round_id=round_.id,
            latitude=g["lat"], longitude=g["lng"],
            distance=g["distance"], score=g["score"], time=g["time"],
        ))
    db.session.commit()
    return session


# ---------------------------------------------------------------------------
# Leaderboard ordering
# ---------------------------------------------------------------------------

def test_leaderboard_orders_seeded_guesses_by_score_descending(client):
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)

    low = make_user(username="low_scorer")
    mid = make_user(username="mid_scorer")
    high = make_user(username="high_scorer")
    _seed_leaderboard_entry(game_map, low, base_rules, score=1000)
    _seed_leaderboard_entry(game_map, mid, base_rules, score=3000)
    _seed_leaderboard_entry(game_map, high, base_rules, score=5000)

    response = client.get(LEADERBOARD_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    usernames = [entry["user"]["username"] for entry in body["data"]]
    assert usernames == ["high_scorer", "mid_scorer", "low_scorer"]
    assert [entry["rank"] for entry in body["data"]] == [1, 2, 3]
    assert [entry["average_score"] for entry in body["data"]] == [5000, 3000, 1000]
    assert body["pages"] == 1


def test_leaderboard_paginates(client):
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)
    for i in range(3):
        player = make_user(username=f"player_{i}")
        _seed_leaderboard_entry(game_map, player, base_rules, score=1000 * (i + 1))

    response = client.get(
        LEADERBOARD_URL, query_string={"id": game_map.uuid, "page": 1, "per_page": 2}, headers=auth_header(user)
    )

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]) == 2
    assert body["pages"] == 2
    assert [entry["rank"] for entry in body["data"]] == [1, 2]


# ---------------------------------------------------------------------------
# Leaderboard ties
# ---------------------------------------------------------------------------

def test_leaderboard_tie_on_score_breaks_on_round_number(client):
    """Equal high_average_score is broken by high_round_number descending -
    more rounds played at the same average score ranks higher."""
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)

    more_rounds = make_user(username="tied_more_rounds")
    fewer_rounds = make_user(username="tied_fewer_rounds")
    _seed_leaderboard_entry(game_map, more_rounds, base_rules, score=2000, rounds=10)
    _seed_leaderboard_entry(game_map, fewer_rounds, base_rules, score=2000, rounds=5)

    response = client.get(LEADERBOARD_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    usernames = [entry["user"]["username"] for entry in response.get_json()["data"]]
    assert usernames == ["tied_more_rounds", "tied_fewer_rounds"]


def test_leaderboard_tie_on_score_and_rounds_breaks_on_average_time(client):
    """Equal score and round count fall through to high_average_time, sorted
    ascending (no .desc()) - i.e. the faster player ranks higher."""
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)

    fast = make_user(username="tied_fast")
    slow = make_user(username="tied_slow")
    _seed_leaderboard_entry(game_map, fast, base_rules, score=2000, rounds=5, avg_time=8.0)
    _seed_leaderboard_entry(game_map, slow, base_rules, score=2000, rounds=5, avg_time=15.0)

    response = client.get(LEADERBOARD_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    usernames = [entry["user"]["username"] for entry in response.get_json()["data"]]
    assert usernames == ["tied_fast", "tied_slow"]


def test_leaderboard_excludes_rows_with_no_high_session(client):
    """A UserMapStats row with no completed high_session (high_session_id is
    NULL) is excluded from the leaderboard entirely."""
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)
    ranked = make_user(username="has_a_session")
    _seed_leaderboard_entry(game_map, ranked, base_rules, score=1000)

    unranked = make_user(username="no_session_yet")
    db.session.add(UserMapStats(
        user_id=unranked.id, map_id=game_map.id, nmpz=False,
        total_time=0, total_score=0, total_distance=0, total_guesses=0,
        high_average_score=9999, high_average_distance=0, high_average_time=0,
        high_round_number=0, high_session_id=None,
    ))
    db.session.commit()

    response = client.get(LEADERBOARD_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    usernames = [entry["user"]["username"] for entry in response.get_json()["data"]]
    assert usernames == ["has_a_session"]


# ---------------------------------------------------------------------------
# leaderboard/game
# ---------------------------------------------------------------------------

def test_leaderboard_game_returns_per_game_ranking(client):
    """leaderboard/game returns the rounds/guesses/aggregate score for one
    user's best recorded session on the map."""
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)

    guesses = [
        {"round_lat": 10.0, "round_lng": 20.0, "lat": 10.001, "lng": 20.001, "distance": 5.0, "score": 4800, "time": 12},
        {"round_lat": 11.0, "round_lng": 21.0, "lat": 11.002, "lng": 21.002, "distance": 8.0, "score": 4600, "time": 18},
    ]
    session = _build_session_with_guesses(game_map, user, base_rules, guesses)

    avg_score = sum(g["score"] for g in guesses) / len(guesses)
    avg_distance = sum(g["distance"] for g in guesses) / len(guesses)
    avg_time = sum(g["time"] for g in guesses) / len(guesses)
    db.session.add(UserMapStats(
        user_id=user.id, map_id=game_map.id, nmpz=False,
        total_time=sum(g["time"] for g in guesses), total_score=sum(g["score"] for g in guesses),
        total_distance=sum(g["distance"] for g in guesses), total_guesses=len(guesses),
        high_average_score=avg_score, high_average_distance=avg_distance, high_average_time=avg_time,
        high_round_number=len(guesses), high_session_id=session.id,
    ))
    db.session.commit()

    response = client.get(
        LEADERBOARD_GAME_URL, query_string={"id": game_map.uuid, "user": user.username}, headers=auth_header(user)
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["user"]["username"] == user.username
    assert body["rounds"] == [{"lat": 10.0, "lng": 20.0}, {"lat": 11.0, "lng": 21.0}]
    assert [g["score"] for g in body["guesses"]] == [4800, 4600]
    assert [g["distance"] for g in body["guesses"]] == [5.0, 8.0]
    assert body["score"] == pytest.approx(avg_score * len(guesses))
    assert body["distance"] == pytest.approx(avg_distance * len(guesses))
    assert body["time"] == pytest.approx(avg_time * len(guesses))


def test_leaderboard_game_defaults_to_the_logged_in_user(client):
    """Omitting the `user` query param falls back to the requester's own
    stats rather than requiring it."""
    user = make_user()
    game_map = make_map(creator=user)
    base_rules = make_base_rules(game_map=game_map)
    guesses = [{"round_lat": 1.0, "round_lng": 2.0, "lat": 1.0, "lng": 2.0, "distance": 0.0, "score": 5000, "time": 5}]
    session = _build_session_with_guesses(game_map, user, base_rules, guesses)
    db.session.add(UserMapStats(
        user_id=user.id, map_id=game_map.id, nmpz=False,
        total_time=5, total_score=5000, total_distance=0, total_guesses=1,
        high_average_score=5000, high_average_distance=0, high_average_time=5,
        high_round_number=1, high_session_id=session.id,
    ))
    db.session.commit()

    response = client.get(LEADERBOARD_GAME_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    assert response.get_json()["user"]["username"] == user.username


def test_leaderboard_game_user_with_no_completed_session_returns_400(client):
    user = make_user()
    game_map = make_map(creator=user)
    db.session.add(UserMapStats(
        user_id=user.id, map_id=game_map.id, nmpz=False,
        total_time=0, total_score=0, total_distance=0, total_guesses=0,
        high_average_score=0, high_average_distance=0, high_average_time=0,
        high_round_number=0, high_session_id=None,
    ))
    db.session.commit()

    response = client.get(
        LEADERBOARD_GAME_URL, query_string={"id": game_map.uuid, "user": user.username}, headers=auth_header(user)
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "User has not played the game"}


def test_leaderboard_game_unknown_user_returns_404(client):
    user = make_user()
    game_map = make_map(creator=user)

    response = client.get(
        LEADERBOARD_GAME_URL, query_string={"id": game_map.uuid, "user": "no-such-user"}, headers=auth_header(user)
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /stats shape
# ---------------------------------------------------------------------------

def test_stats_route_returns_expected_map_stats_shape(client):
    user = make_user()
    game_map = make_map(creator=user, max_distance=5000.0)
    base_rules = make_base_rules(game_map=game_map)
    session = make_session(host=user, base_rules=base_rules)

    db.session.add(MapStats(
        map_id=game_map.id, nmpz=False,
        total_time=100, total_score=27000, total_distance=200.0, total_guesses=6,
    ))
    db.session.add(UserMapStats(
        user_id=user.id, map_id=game_map.id, nmpz=False,
        total_time=100, total_score=27000, total_distance=200.0, total_guesses=6,
        high_average_score=4500.0, high_average_distance=33.3, high_average_time=16.7,
        high_round_number=6, high_session_id=session.id,
    ))
    db.session.commit()

    response = client.get(STATS_URL, query_string={"id": game_map.uuid}, headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == game_map.name
    assert body["id"] == game_map.uuid
    assert body["creator"] == user.username

    stats = body["map_stats"]
    assert stats["average_generation_time"] == 0  # no GenerationTime row
    assert stats["average_score"] == pytest.approx(4500.0)
    assert stats["average_distance"] == pytest.approx(200.0 / 6)
    assert stats["average_time"] == pytest.approx(100 / 6)
    assert stats["total_guesses"] == 6
    assert stats["max_distance"] == 5000.0

    user_stats = body["user_stats"]
    assert user_stats["average"]["score"] == pytest.approx(4500.0)
    assert user_stats["average"]["guesses"] == 6
    assert user_stats["high"]["score"] == pytest.approx(4500.0)
    assert user_stats["high"]["rounds"] == 6
    assert user_stats["high"]["session"] == session.uuid

    other = body["other"]
    assert other["top_guesses"] == {"user": user.username, "stat": pytest.approx(6.0)}
    assert other["5ks"] == 0
    assert "highest_score" not in other


def test_stats_route_demo_user_has_no_user_stats_section(client):
    """The `demo` user never gets a "user_stats" section, regardless of any
    UserMapStats rows that exist for it."""
    demo = make_user(username="demo")
    game_map = make_map(creator=demo)
    db.session.add(MapStats(map_id=game_map.id, nmpz=False, total_time=1, total_score=1, total_distance=1, total_guesses=1))
    db.session.commit()

    response = client.get(STATS_URL, query_string={"id": game_map.uuid}, headers=auth_header(demo))

    assert response.status_code == 200
    assert "user_stats" not in response.get_json()


def test_stats_route_missing_id_returns_400(client):
    user = make_user()

    response = client.get(STATS_URL, headers=auth_header(user))

    assert response.status_code == 400
    assert response.get_json() == {"error": "provided: id"}


def test_stats_route_unknown_map_returns_404(client):
    user = make_user()

    response = client.get(STATS_URL, query_string={"id": "does-not-exist"}, headers=auth_header(user))

    assert response.status_code == 404


def test_stats_route_with_nmpz_filter_and_no_matching_mapstats_documents_bug(client):
    """BUG: when `nmpz` is passed explicitly (true/false), map.py:get_stats
    takes the `MapStats.query.filter_by(map_id=..., nmpz=nmpz).first()`
    branch, which returns None if no MapStats row exists for that nmpz
    value. routes.py then reads `stats.total_score`/`stats.total_guesses`
    with no None-check, so the route raises AttributeError instead of
    returning a clean 4xx or a zeroed shape. Here only a nmpz=False MapStats
    row is seeded, so `nmpz=true` has nothing to find."""
    user = make_user()
    game_map = make_map(creator=user)
    db.session.add(MapStats(
        map_id=game_map.id, nmpz=False,
        total_time=10, total_score=100, total_distance=5.0, total_guesses=1,
    ))
    db.session.commit()

    with pytest.raises(AttributeError):
        client.get(STATS_URL, query_string={"id": game_map.uuid, "nmpz": "true"}, headers=auth_header(user))

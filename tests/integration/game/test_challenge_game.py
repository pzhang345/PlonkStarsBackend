"""End-to-end integration tests for the CHALLENGE game type, driven entirely
through the real HTTP API (`client`) against `app/api/game/routes.py` and
`app/api/game/games/challenge.py` (+ its base, `basegame.py`).

Route shapes exercised here (payload keys confirmed by reading the source,
not guessed):
  * POST /api/game/create  {"type","map_id","rounds","time","nmpz"} -> {"id": <session uuid>}
      - "map_id" must be the map's `uuid` field (GameMap.uuid), NOT its
        integer `id` - basegame.py's create() does
        `GameMap.query.filter_by(uuid=map_id)`.
      - "rounds"/"time"/"nmpz" map to BaseRules.max_rounds/time_limit/nmpz.
  * POST /api/game/play    {"id"} -> {"message":"session joined"}          (creates a Player row)
  * POST /api/game/next    {"id"} -> {"message":"round exists"}
  * GET  /api/game/round?id=..    -> {"round","lat","lng","nmpz","map_bounds", [+"time","time_limit","now" if timed]}
  * POST /api/game/guess   {"id","lat","lng"} -> {"message":"guess added"}
  * GET  /api/game/state?id=..    -> {"state": <NOT_STARTED|GUESSING|RESULTS|FINISHED>, ...}
  * GET  /api/game/results?id=..&round=&page=&per_page=  -> {"round","correct","this_user","users":[...]}
  * GET  /api/game/summary?id=..&page=&per_page=         -> {"this_user","users":[...],"rounds":[...]}
  * POST /api/game/plonk   {"id","lat","lng"} -> {"success": True}  (provisional marker, no body from the view itself)
  * GET  /api/game/rules/config?type=challenge -> [{"key","name","type","display",...,"default"}, ...]

CRITICAL config caveat (see basegame.py:11):
    map_id = data.get("map_id", int(Configs.get("GAME_DEFAULT_MAP_ID")))
`dict.get`'s default argument is evaluated *eagerly*, i.e. on every single
call regardless of whether "map_id" is actually present in the payload. So
`GAME_DEFAULT_MAP_ID` must exist in Configs for ANY /api/game/create call to
succeed, even when the request always supplies its own map_id explicitly.
Likewise `rules_config()`'s NMPZ default does
`Configs.get("GAME_DEFAULT_NMPZ").lower()` unconditionally, so that key must
exist too or every call blows up with AttributeError-on-None. See the
`game_configs` fixture below.
"""

import uuid as uuid_module

import pytest

from api.game.gameutils import caculate_score
from api.map.map import haversine
from models.configs import Configs
from models.db import db
from models.map import Bound, GameMap, MapBound
from models.session import BaseRules, GameStateTracker, Guess, Player, Session
from models.stats import RoundStats
from tests.factories import make_map, make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration

MAX_SCORE = 5000
LOCATION_LAT = 40.0
LOCATION_LNG = -74.0
MAX_DISTANCE = 1000.0  # km, matches make_map()'s default-ish scale


# ---------------------------------------------------------------------------
# Local fixtures/helpers (none of this touches tests/conftest.py etc. - it's
# scoped to this file only, per the task's hard rules).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    """Every test in this file eventually calls POST /api/game/next, which
    generates a round location via api.location.generate.generate_location.
    Apply the mock automatically so individual tests don't have to remember
    to request it (only the test that explicitly cares about the mock's
    return value still names it directly, for readability)."""
    return street_view_mock


@pytest.fixture()
def game_configs(db_session):
    """Seed every Configs key that BaseGame/ChallengeGame read for CHALLENGE
    (and LIVE, which reuses ChallengeGame.rules_config()). Values mirror the
    README's documented seed data."""
    values = {
        "GAME_DEFAULT_MAP_ID": "1",
        "GAME_DEFAULT_ROUNDS": "5",
        "GAME_DEFAULT_TIME_LIMIT": "60",
        "GAME_DEFAULT_NMPZ": "False",
    }
    for key, value in values.items():
        db.session.add(Configs(key=key, value=value))
    db.session.commit()
    return values


def make_bounded_map(creator=None, lat=LOCATION_LAT, lng=LOCATION_LNG, max_distance=MAX_DISTANCE):
    """make_map() alone leaves a map with no generatable locations:
    BaseGame.create() requires map.total_weight > 0, and
    api.location.generate.get_random_bounds() needs at least one MapBound
    row to pick from. This builds a single deterministic *point* Bound, so
    - combined with the street_view_mock fixture, which always returns the
    bound's start corner - every round's location is exactly (lat, lng).
    """
    game_map = make_map(creator=creator, max_distance=max_distance, total_weight=1)
    bound = Bound(start_latitude=lat, start_longitude=lng, end_latitude=lat, end_longitude=lng)
    db.session.add(bound)
    db.session.flush()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=1))
    db.session.commit()
    return game_map


def create_challenge(client, user, game_map, rounds=3, time=-1, nmpz=False, headers=None):
    return client.post(
        "/api/game/create",
        json={"type": "challenge", "map_id": game_map.uuid, "rounds": rounds, "time": time, "nmpz": nmpz},
        headers=headers if headers is not None else auth_header(user),
    )


def join(client, user, session_uuid):
    return client.post("/api/game/play", json={"id": session_uuid}, headers=auth_header(user))


def next_round(client, user, session_uuid):
    return client.post("/api/game/next", json={"id": session_uuid}, headers=auth_header(user))


def get_round(client, user, session_uuid):
    return client.get(f"/api/game/round?id={session_uuid}", headers=auth_header(user))


def submit_guess(client, user, session_uuid, lat, lng):
    return client.post("/api/game/guess", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def get_state(client, user, session_uuid):
    return client.get(f"/api/game/state?id={session_uuid}", headers=auth_header(user))


def get_results(client, user, session_uuid, **params):
    query = "&".join([f"id={session_uuid}"] + [f"{k}={v}" for k, v in params.items()])
    return client.get(f"/api/game/results?{query}", headers=auth_header(user))


def get_summary(client, user, session_uuid, **params):
    query = "&".join([f"id={session_uuid}"] + [f"{k}={v}" for k, v in params.items()])
    return client.get(f"/api/game/summary?{query}", headers=auth_header(user))


def do_plonk(client, user, session_uuid, lat, lng):
    return client.post("/api/game/plonk", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def expected_distance_and_score(guess_lat, guess_lng, loc_lat=LOCATION_LAT, loc_lng=LOCATION_LNG,
                                 max_distance=MAX_DISTANCE, max_score=MAX_SCORE):
    """Computed independently from the same haversine/caculate_score utility
    functions production code uses (api/map/map.py, api/game/gameutils.py),
    but NOT via create_guess() itself - this is the ground truth the
    persisted Guess row is checked against.

    NOTE: create_guess() feeds `max(0, distance - 0.05)` (a 50m tolerance
    buffer), not the raw distance, into caculate_score(). Replicated here on
    purpose - that's real, intentional-looking behavior, not a bug."""
    distance = haversine(guess_lat, guess_lng, loc_lat, loc_lng)
    score = caculate_score(max(0, distance - 0.05), max_distance, max_score)
    return distance, score


def start_and_join(client, host, game_map, rounds=5, time=-1, nmpz=False):
    response = create_challenge(client, host, game_map, rounds=rounds, time=time, nmpz=nmpz)
    assert response.status_code == 200, response.get_data(as_text=True)
    session_uuid = response.get_json()["id"]

    response = join(client, host, session_uuid)
    assert response.status_code == 200, response.get_data(as_text=True)

    return session_uuid


def play_all_rounds(client, user, session_uuid, rounds, lat=LOCATION_LAT, lng=LOCATION_LNG):
    """Advance through and guess (at a fixed point, perfect by default) in
    every round of a `rounds`-round game, driving it all the way to
    FINISHED. Returns the list of per-round Guess.score values actually
    persisted (read back from the DB)."""
    from models.session import Round

    scores = []
    session = Session.query.filter_by(uuid=session_uuid).first()
    for _ in range(rounds):
        response = next_round(client, user, session_uuid)
        assert response.status_code == 200, response.get_data(as_text=True)
        response = submit_guess(client, user, session_uuid, lat, lng)
        assert response.status_code == 200, response.get_data(as_text=True)
        # Look the round up by *this player's own* current_round, not the
        # session's highest round number - a later-joining player reuses
        # rounds another player already created (see
        # ChallengeGame.next(): a new Round is only created when
        # `player.current_round + 1 > session.current_round`).
        player = Player.query.filter_by(user_id=user.id, session_id=session.id).first()
        round_ = Round.query.filter_by(session_id=session.id, round_number=player.current_round).first()
        guess = Guess.query.filter_by(user_id=user.id, round_id=round_.id).first()
        scores.append(guess.score)
    return scores


# ---------------------------------------------------------------------------
# create / play
# ---------------------------------------------------------------------------

def test_create_persists_session_and_base_rules(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, rounds=7, time=45, nmpz=True)

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    session_uuid = body["id"]
    assert session_uuid

    session = Session.query.filter_by(uuid=session_uuid).first()
    assert session is not None
    assert session.host_id == host.id
    assert session.current_round == 0

    rules = session.base_rules
    assert rules.map_id == game_map.id
    assert rules.max_rounds == 7
    assert rules.time_limit == 45
    assert rules.nmpz is True


def test_play_creates_player_row(client, game_configs):
    host = make_user()
    joiner = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)

    response = join(client, joiner, session_uuid)

    assert response.status_code == 200
    assert response.get_json() == {"message": "session joined"}

    session = Session.query.filter_by(uuid=session_uuid).first()
    player = Player.query.filter_by(session_id=session.id, user_id=joiner.id).first()
    assert player is not None
    assert player.current_round == 0


def test_joining_same_session_twice_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)

    response = join(client, host, session_uuid)

    body = response.get_json()
    assert response.status_code == 403
    assert body == {"error": "already played this session"}


# ---------------------------------------------------------------------------
# round / street view mock
# ---------------------------------------------------------------------------

def test_round_returns_street_view_mock_location_not_google(client, game_configs, street_view_mock):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)

    response = next_round(client, host, session_uuid)
    assert response.status_code == 200, response.get_data(as_text=True)

    response = get_round(client, host, session_uuid)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()

    assert body["round"] == 1
    assert body["lat"] == pytest.approx(LOCATION_LAT)
    assert body["lng"] == pytest.approx(LOCATION_LNG)
    assert body["nmpz"] is False
    assert body["map_bounds"] == game_map.get_bounds()
    # time_limit == -1 (default from start_and_join) -> no timing keys at all
    assert "time" not in body
    assert "time_limit" not in body

    # The _no_network fixture would have raised RuntimeError had a real
    # Google call been attempted; on top of that, confirm the location that
    # actually got persisted is exactly the mock's deterministic point.
    from models.location import SVLocation
    assert SVLocation.query.filter_by(latitude=LOCATION_LAT, longitude=LOCATION_LNG).count() == 1


# ---------------------------------------------------------------------------
# guess / scoring - the highest-value assertions in this file
# ---------------------------------------------------------------------------

def test_guess_score_matches_caculate_score_computed_independently(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)
    next_round(client, host, session_uuid)

    guess_lat, guess_lng = 40.01, -74.02  # a few km off

    response = submit_guess(client, host, session_uuid, guess_lat, guess_lng)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == {"message": "guess added"}

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = session.rounds[0]
    guess = Guess.query.filter_by(user_id=host.id, round_id=round_.id).first()
    assert guess is not None

    expected_distance, expected_score = expected_distance_and_score(guess_lat, guess_lng)
    assert guess.distance == pytest.approx(expected_distance)
    # Guess.score is a DB Integer column despite caculate_score() being
    # continuous - Postgres applies an assignment cast (round-to-nearest,
    # ties-to-even) on INSERT. Documenting that precision loss explicitly
    # rather than silently laundering it through an approx() tolerance.
    assert guess.score == round(expected_score)


def test_perfect_guess_yields_max_score(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)
    next_round(client, host, session_uuid)

    response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)
    assert response.status_code == 200

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = session.rounds[0]
    guess = Guess.query.filter_by(user_id=host.id, round_id=round_.id).first()

    assert guess.distance == pytest.approx(0.0, abs=1e-9)
    assert guess.score == MAX_SCORE


def test_guess_twice_in_same_round_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)
    next_round(client, host, session_uuid)

    first = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)
    assert first.status_code == 200

    second = submit_guess(client, host, session_uuid, LOCATION_LAT + 1, LOCATION_LNG)
    assert second.status_code == 400
    # NOTE: create_guess()'s own "user has already guessed" dedup check
    # (gameutils.py:76) is actually unreachable through this route: as soon
    # as the first guess is persisted, ChallengeGame.get_state() (called at
    # the top of guess()) already sees a Guess row and reports RESULTS
    # instead of GUESSING, so guess() rejects the second call earlier with
    # this different, less specific message.
    assert second.get_json() == {"error": "Player is not in a playing state"}

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = session.rounds[0]
    assert Guess.query.filter_by(user_id=host.id, round_id=round_.id).count() == 1


def test_guess_before_starting_a_round_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)
    # No /next call yet -> player.current_round == 0 -> state NOT_STARTED.

    response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)

    assert response.status_code == 400
    assert response.get_json() == {"error": "Player is not in a playing state"}
    assert Guess.query.count() == 0


# ---------------------------------------------------------------------------
# full multi-round game -> results / state / summary
# ---------------------------------------------------------------------------

def test_full_game_state_transitions_and_summary_totals(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)

    guesses = [
        (40.001, -74.0),
        (LOCATION_LAT, LOCATION_LNG),
        (40.02, -74.03),
        (40.05, -74.0),
        (LOCATION_LAT, LOCATION_LNG),
    ]
    total_rounds = len(guesses)
    expected_scores = []

    for round_number, (lat, lng) in enumerate(guesses, start=1):
        state = get_state(client, host, session_uuid).get_json()
        if round_number == 1:
            assert state["state"] == "NOT_STARTED"
        else:
            # Between rounds 2-5: the previous round's guess was already
            # submitted (last thing the prior loop iteration did), so
            # get_state() reports RESULTS - it isn't NOT_STARTED again and
            # doesn't jump ahead to GUESSING until next_round() is called
            # below.
            assert state["state"] == "RESULTS"

        response = next_round(client, host, session_uuid)
        assert response.status_code == 200, response.get_data(as_text=True)

        state = get_state(client, host, session_uuid).get_json()
        assert state["state"] == "GUESSING"
        assert state["round"] == round_number

        round_response = get_round(client, host, session_uuid)
        assert round_response.get_json()["round"] == round_number

        response = submit_guess(client, host, session_uuid, lat, lng)
        assert response.status_code == 200, response.get_data(as_text=True)

        _, score = expected_distance_and_score(lat, lng)
        expected_scores.append(round(score))

        state = get_state(client, host, session_uuid).get_json()
        session = Session.query.filter_by(uuid=session_uuid).first()
        round_stats = RoundStats.query.filter_by(
            session_id=session.id, user_id=host.id, round=round_number
        ).first()
        assert round_stats.total_score == sum(expected_scores)

        if round_number < total_rounds:
            assert state["state"] == "RESULTS"
            # GET /api/game/results reports the same cumulative total
            # RoundStats already tracks (above), plus the round's correct
            # location and this player's ranked leaderboard entry.
            results_body = get_results(client, host, session_uuid, round=round_number).get_json()
            assert results_body["round"] == round_number
            assert results_body["correct"]["lat"] == pytest.approx(LOCATION_LAT)
            assert results_body["correct"]["lng"] == pytest.approx(LOCATION_LNG)
            assert results_body["this_user"] == host.username
            assert len(results_body["users"]) == 1  # solo game, no other players
            host_entry = results_body["users"][0]
            assert host_entry["user"] == host.to_json()
            assert host_entry["rank"] == 1
            assert host_entry["score"] == round_stats.total_score
            assert host_entry["guess"]["lat"] == pytest.approx(lat)
            assert host_entry["guess"]["lng"] == pytest.approx(lng)
        else:
            # Last round: get_state() jumps straight from GUESSING to
            # FINISHED, skipping RESULTS entirely (next_round == max_rounds+1
            # short-circuits before the RESULTS branch in
            # ChallengeGame.get_state()). Documenting this as real behavior.
            assert state["state"] == "FINISHED"

    # Can't advance further, and the session was never a party-game session
    # so no GameStateTracker row was ever created for it.
    session = Session.query.filter_by(uuid=session_uuid).first()
    assert GameStateTracker.query.filter_by(session_id=session.id).first() is None

    final_state = get_state(client, host, session_uuid).get_json()
    assert final_state["state"] == "FINISHED"

    # RoundStats is the ground truth "final totals equal the sum of the
    # per-round scores" check; confirm GET /api/game/summary reports exactly
    # the same numbers, plus every round's location and this player's
    # per-round guesses.
    final_stats = RoundStats.query.filter_by(session_id=session.id, user_id=host.id, round=total_rounds).first()
    assert final_stats.total_score == sum(expected_scores)

    summary_body = get_summary(client, host, session_uuid).get_json()
    assert summary_body["this_user"] == host.username
    assert len(summary_body["rounds"]) == total_rounds
    for round_entry in summary_body["rounds"]:
        assert round_entry["lat"] == pytest.approx(LOCATION_LAT)
        assert round_entry["lng"] == pytest.approx(LOCATION_LNG)

    assert len(summary_body["users"]) == 1  # solo game, no other players
    host_summary_entry = summary_body["users"][0]
    assert host_summary_entry["user"] == host.to_json()
    assert host_summary_entry["rank"] == 1
    assert host_summary_entry["score"] == sum(expected_scores)
    assert len(host_summary_entry["guesses"]) == total_rounds
    for guess_json, (guess_lat, guess_lng) in zip(host_summary_entry["guesses"], guesses):
        assert guess_json["lat"] == pytest.approx(guess_lat)
        assert guess_json["lng"] == pytest.approx(guess_lng)


def test_advance_past_max_rounds_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)

    play_all_rounds(client, host, session_uuid, rounds=5)

    state = get_state(client, host, session_uuid).get_json()
    assert state["state"] == "FINISHED"

    response = next_round(client, host, session_uuid)

    assert response.status_code == 400
    assert response.get_json() == {"error": "No more rounds are available"}


# ---------------------------------------------------------------------------
# plonk (provisional marker)
# ---------------------------------------------------------------------------

def test_plonk_then_guess_clears_provisional_marker(client, game_configs):
    from models.session import PlayerPlonk

    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)
    next_round(client, host, session_uuid)

    response = do_plonk(client, host, session_uuid, 40.005, -74.005)
    assert response.status_code == 200

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = session.rounds[0]
    plonk_row = PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).first()
    assert plonk_row is not None
    assert plonk_row.latitude == pytest.approx(40.005)

    state = get_state(client, host, session_uuid).get_json()
    assert state.get("lat") == pytest.approx(40.005)

    submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)

    assert PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).count() == 0


# ---------------------------------------------------------------------------
# GET /api/game/results and /api/game/summary
# ---------------------------------------------------------------------------

def test_results_endpoint_returns_leaderboard_and_this_users_guess(client, game_configs):
    """ChallengeGame.results() builds its leaderboard as:

        ranked_users = db.session.query(stats.c.user_id, ..., func.rank()...)
        ...
        leaderboard = ranked_users.paginate(page=page, per_page=per_page, error_out=False)

    `.paginate()` works because Flask-SQLAlchemy's session uses `db.Query`
    as its query class (mirrored by tests/conftest.py's `db_session`).
    Confirms GET /api/game/results
    returns 200 with the round's correct location, `this_user`, and a
    single-entry leaderboard (solo game) with this player's rank/score/
    distance/time/guess."""
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)
    next_round(client, host, session_uuid)
    submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)

    response = get_results(client, host, session_uuid, round=1)

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["round"] == 1
    assert body["correct"]["lat"] == pytest.approx(LOCATION_LAT)
    assert body["correct"]["lng"] == pytest.approx(LOCATION_LNG)
    assert body["this_user"] == host.username

    assert len(body["users"]) == 1  # solo game, no other players
    entry = body["users"][0]
    assert entry["user"] == host.to_json()
    assert entry["rank"] == 1
    assert entry["score"] == MAX_SCORE
    assert entry["distance"] == pytest.approx(0.0, abs=1e-9)
    assert entry["guess"]["score"] == MAX_SCORE
    assert entry["guess"]["lat"] == pytest.approx(LOCATION_LAT)
    assert entry["guess"]["lng"] == pytest.approx(LOCATION_LNG)


def test_summary_endpoint_returns_totals_and_all_round_locations(client, game_configs):
    """Same shape as results() (ChallengeGame.summary() also paginates a
    `db.session.query(...)` result), but aggregated across every round of a
    FINISHED game: `rounds` lists every round's correct location, and each
    leaderboard entry's `guesses` list has one entry per round."""
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)
    scores = play_all_rounds(client, host, session_uuid, rounds=5)
    assert scores == [MAX_SCORE] * 5  # perfect guesses throughout

    response = get_summary(client, host, session_uuid)

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["this_user"] == host.username
    assert len(body["rounds"]) == 5
    for round_entry in body["rounds"]:
        assert round_entry["lat"] == pytest.approx(LOCATION_LAT)
        assert round_entry["lng"] == pytest.approx(LOCATION_LNG)

    assert len(body["users"]) == 1  # solo game, no other players
    entry = body["users"][0]
    assert entry["user"] == host.to_json()
    assert entry["rank"] == 1
    assert entry["score"] == sum(scores)
    assert len(entry["guesses"]) == 5
    for guess_json in entry["guesses"]:
        assert guess_json["score"] == MAX_SCORE


# ---------------------------------------------------------------------------
# rules/config
# ---------------------------------------------------------------------------

def test_rules_config_endpoint_shape_for_challenge(client, game_configs):
    host = make_user()
    response = client.get("/api/game/rules/config?type=challenge", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    keys = {entry["key"] for entry in body}
    assert keys == {"rounds", "time", "nmpz"}

    by_key = {entry["key"]: entry for entry in body}
    assert by_key["rounds"]["min"] == 5
    assert by_key["rounds"]["max"] == 20
    assert by_key["time"]["infinity"] is True
    assert by_key["nmpz"]["type"] == "boolean"


# ---------------------------------------------------------------------------
# error / auth edge cases
# ---------------------------------------------------------------------------

def test_unknown_session_uuid_returns_404(client, game_configs):
    host = make_user()
    fake_uuid = str(uuid_module.uuid4())

    response = get_round(client, host, fake_uuid)

    assert response.status_code == 404
    assert b"Session not found" in response.data


def test_unauthenticated_request_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map)

    response = client.get(f"/api/game/round?id={session_uuid}")

    assert response.status_code == 403
    assert response.get_json() == {"error": "login required"}


def test_non_host_player_is_restricted_until_host_finishes(client, game_configs):
    """Discovered behavior: ChallengeGame.get_state() special-cases
    CHALLENGE-type sessions so that ANY user who isn't session.host_id gets
    back {"state": "RESTRICTED"} until the *host's own* run reaches FINISHED
    (challenge.py:99-103). So
    CHALLENGE is really "solo run now, friends can replay it once you're
    done" - not concurrent same-round multiplayer. (Player.join() itself
    doesn't actually enforce this - it computes get_state(host) which can
    never be RESTRICTED - so join() always succeeds; the gate is entirely
    in get_state()/guess()/get_round() for the *joining* user.)"""
    host = make_user()
    other = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)

    response = join(client, other, session_uuid)
    assert response.status_code == 200  # join() itself is unaffected

    next_round(client, host, session_uuid)  # host starts but does not finish

    state = get_state(client, other, session_uuid).get_json()
    assert state == {"state": "RESTRICTED"}

    response = submit_guess(client, other, session_uuid, LOCATION_LAT, LOCATION_LNG)
    assert response.status_code == 400
    assert response.get_json() == {"error": "Player is not in a playing state"}
    assert Guess.query.filter_by(user_id=other.id).count() == 0


def test_second_users_guess_does_not_leak_into_first_users_results(client, game_configs):
    # Per test_non_host_player_is_restricted_until_host_finishes above, a
    # non-host player can't actually guess until the host's own session is
    # FINISHED - so exercise the two users the way the app actually allows:
    # host plays the full game to completion first, then `other` joins and
    # plays it (independently) afterwards.
    host = make_user()
    other = make_user()
    game_map = make_bounded_map(creator=host)
    session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)

    host_scores = play_all_rounds(client, host, session_uuid, rounds=5)
    assert host_scores == [MAX_SCORE] * 5

    response = join(client, other, session_uuid)
    assert response.status_code == 200

    other_scores = play_all_rounds(
        client, other, session_uuid, rounds=5, lat=LOCATION_LAT + 10, lng=LOCATION_LNG + 10
    )
    assert all(score < MAX_SCORE for score in other_scores)

    session = Session.query.filter_by(uuid=session_uuid).first()
    host_stats = RoundStats.query.filter_by(session_id=session.id, user_id=host.id, round=5).first()
    other_stats = RoundStats.query.filter_by(session_id=session.id, user_id=other.id, round=5).first()

    # `other` playing (badly) afterwards must not have mutated host's
    # already-recorded totals.
    assert host_stats.total_score == MAX_SCORE * 5
    assert other_stats.total_score == sum(other_scores)
    assert other_stats.total_score < host_stats.total_score


def test_demo_user_can_play_challenge_end_to_end(client, game_configs):
    # ChallengeGame.allow_demo() returns True, and all /api/game/* routes are
    # @login_required(allow_demo=True), so the literal "demo" auth token
    # should work for the full flow as long as a "demo" user row exists.
    demo = make_user(username="demo")
    game_map = make_bounded_map(creator=demo)

    response = create_challenge(client, demo, game_map, rounds=5, time=-1, headers=demo_header())
    assert response.status_code == 200, response.get_data(as_text=True)
    session_uuid = response.get_json()["id"]

    response = client.post("/api/game/play", json={"id": session_uuid}, headers=demo_header())
    assert response.status_code == 200, response.get_data(as_text=True)

    response = client.post("/api/game/next", json={"id": session_uuid}, headers=demo_header())
    assert response.status_code == 200, response.get_data(as_text=True)

    response = client.post(
        "/api/game/guess",
        json={"id": session_uuid, "lat": LOCATION_LAT, "lng": LOCATION_LNG},
        headers=demo_header(),
    )
    assert response.status_code == 200, response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# BUG: default-map lookup filters the wrong column
# ---------------------------------------------------------------------------

def test_create_without_map_id_documents_broken_default_lookup(client, game_configs):
    """basegame.py's BaseGame.create():

        map_id = data.get("map_id", int(Configs.get("GAME_DEFAULT_MAP_ID")))
        map = GameMap.query.filter_by(uuid=map_id).first()

    GAME_DEFAULT_MAP_ID is documented (README) to hold a map's *numeric*
    primary key (e.g. "1"), but the fallback then filters GameMap by its
    `uuid` column (a String(36)), not `id`. So omitting "map_id" from the
    create payload can never resolve a real map, no matter what
    GAME_DEFAULT_MAP_ID is set to - it always ends up comparing an int
    against a uuid string column. Flagging this prominently; not fixing
    app code. This test documents whatever the route actually returns today.
    """
    host = make_user()
    make_bounded_map(creator=host)  # a real, playable map exists in the DB

    response = client.post(
        "/api/game/create",
        json={"type": "challenge", "rounds": 5, "time": 60, "nmpz": False},
        headers=auth_header(host),
    )

    assert response.status_code != 200, (
        "If this starts passing, GAME_DEFAULT_MAP_ID's uuid/id mismatch bug "
        f"in basegame.py:11 was fixed. Actual body: {response.get_data(as_text=True)}"
    )
    body = response.get_json()
    assert body is not None and "error" in body, response.get_data(as_text=True)

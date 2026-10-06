"""Integration tests for the rules/config schema and the CHALLENGE game
state machine (app/api/game/games/basegame.py, challenge.py, gameutils.py),
driven through the real HTTP API plus a couple of direct in-process calls
where the HTTP route genuinely can't reach the code path (see
test_duels_rounds_config_allows_infinity_sentinel_directly and
test_live_and_duels_types_not_creatable_via_create_route below).

Route shapes exercised (see test_challenge_game.py's module docstring for
the full rundown; repeated here only where relevant):
  * GET  /api/game/rules/config?type=<challenge|live|duels>
        -> [{"key","name","type","display","min"?,"max"?,"infinity"?,"default"}, ...]
  * POST /api/game/create {"type","map_id","rounds","time","nmpz"}
  * POST /api/game/ping {"id"} -> heartbeat/timeout resolution (no body)

Config keys read by these code paths (confirmed by reading basegame.py,
challenge.py, duels.py, live.py - not guessed):
  GAME_DEFAULT_MAP_ID, GAME_DEFAULT_ROUNDS, GAME_DEFAULT_TIME_LIMIT,
  GAME_DEFAULT_NMPZ (all required - GAME_DEFAULT_NMPZ and GAME_DEFAULT_MAP_ID
  are read unconditionally, see the "CRITICAL config caveat" docstring in
  test_challenge_game.py), and for DUELS additionally:
  DUELS_DEFAULT_ROUNDS, DUELS_DEFAULT_TIME_LIMIT, DUELS_DEFAULT_NMPZ,
  DUELS_DEFAULT_HP, DUELS_DEFAULT_GUESS_TIME_LIMIT,
  DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND, DUELS_DEFAULT_DAMAGE_MULTI_MULT,
  DUELS_DEFAULT_DAMAGE_MULTI_ADD, DUELS_DEFAULT_DAMAGE_MULTI_FREQ.
"""

import uuid as uuid_module
from datetime import datetime, timedelta

import pytest
import pytz
from freezegun import freeze_time

from api.game.gameutils import timed_out
from api.game.gametype import game_type
from models.configs import Configs
from models.db import db
from models.map import Bound, MapBound
from models.session import GameStateTracker, GameType, Guess, Player, PlayerPlonk, Round, Session
from models.stats import RoundStats
from tests.factories import make_map, make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration

LOCATION_LAT = 41.0
LOCATION_LNG = -73.0


# ---------------------------------------------------------------------------
# Local fixtures/helpers (this file's own, per the task's hard rules -
# tests/conftest.py, factories.py, helpers.py are not touched).
# ---------------------------------------------------------------------------

@pytest.fixture()
def game_configs(db_session):
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


@pytest.fixture()
def duels_configs(game_configs):
    values = {
        "DUELS_DEFAULT_ROUNDS": "-1",
        "DUELS_DEFAULT_TIME_LIMIT": "-1",
        "DUELS_DEFAULT_NMPZ": "False",
        "DUELS_DEFAULT_HP": "6000",
        "DUELS_DEFAULT_GUESS_TIME_LIMIT": "15",
        "DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND": "1",
        "DUELS_DEFAULT_DAMAGE_MULTI_MULT": "1",
        "DUELS_DEFAULT_DAMAGE_MULTI_ADD": "0",
        "DUELS_DEFAULT_DAMAGE_MULTI_FREQ": "1",
    }
    for key, value in values.items():
        db.session.add(Configs(key=key, value=value))
    db.session.commit()
    return {**game_configs, **values}


@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    return street_view_mock


def make_bounded_map(creator=None, lat=LOCATION_LAT, lng=LOCATION_LNG, max_distance=1000.0):
    game_map = make_map(creator=creator, max_distance=max_distance, total_weight=1)
    bound = Bound(start_latitude=lat, start_longitude=lng, end_latitude=lat, end_longitude=lng)
    db.session.add(bound)
    db.session.flush()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=1))
    db.session.commit()
    return game_map


def create_challenge(client, user, game_map, rounds=5, time=-1, nmpz=False, extra=None):
    payload = {"type": "challenge", "map_id": game_map.uuid, "rounds": rounds, "time": time, "nmpz": nmpz}
    if extra:
        payload.update(extra)
    return client.post("/api/game/create", json=payload, headers=auth_header(user))


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


def do_plonk(client, user, session_uuid, lat, lng):
    return client.post("/api/game/plonk", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def ping(client, user, session_uuid):
    return client.post("/api/game/ping", json={"id": session_uuid}, headers=auth_header(user))


def start_and_join(client, host, game_map, rounds=5, time=-1, nmpz=False):
    response = create_challenge(client, host, game_map, rounds=rounds, time=time, nmpz=nmpz)
    assert response.status_code == 200, response.get_data(as_text=True)
    session_uuid = response.get_json()["id"]
    response = join(client, host, session_uuid)
    assert response.status_code == 200, response.get_data(as_text=True)
    return session_uuid


# ---------------------------------------------------------------------------
# rules/config shape
# ---------------------------------------------------------------------------

def test_rules_config_shape_challenge_and_live_are_identical(client, game_configs):
    user = make_user()

    challenge_body = client.get("/api/game/rules/config?type=challenge", headers=auth_header(user)).get_json()
    live_body = client.get("/api/game/rules/config?type=live", headers=auth_header(user)).get_json()

    # LiveGame.rules_config() literally returns ChallengeGame().rules_config().
    assert challenge_body == live_body
    assert {e["key"] for e in challenge_body} == {"rounds", "time", "nmpz"}


def test_rules_config_shape_duels_has_extra_keys(client, duels_configs):
    user = make_user()

    response = client.get("/api/game/rules/config?type=duels", headers=auth_header(user))

    assert response.status_code == 200
    body = response.get_json()
    keys = {entry["key"] for entry in body}
    assert keys == {
        "rounds", "time", "nmpz", "hp", "guess_time",
        "multi_start", "multi_mult", "multi_add", "mult_freq",
    }
    by_key = {entry["key"]: entry for entry in body}
    # Duels overrides "rounds" to allow the -1 (infinite rounds) sentinel,
    # unlike CHALLENGE/LIVE.
    assert by_key["rounds"]["infinity"] is True
    assert by_key["hp"]["min"] == 1


def test_rules_config_invalid_type_rejected(client, game_configs):
    user = make_user()

    response = client.get("/api/game/rules/config?type=bogus", headers=auth_header(user))

    assert response.status_code == 400
    assert response.get_json() == {"error": "provided a correct type"}


# ---------------------------------------------------------------------------
# create() rule validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rounds,expected_error", [
    (4, "Value for Number of Rounds too low"),
    (21, "Value for Number of Rounds too high"),
])
def test_create_rounds_out_of_range_rejected(client, game_configs, rounds, expected_error):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, rounds=rounds)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


@pytest.mark.parametrize("rounds", [5, 20])
def test_create_rounds_at_boundaries_accepted(client, game_configs, rounds):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, rounds=rounds)

    assert response.status_code == 200, response.get_data(as_text=True)


def test_create_rounds_infinity_sentinel_rejected_for_challenge(client, game_configs):
    # Unlike "time", the "rounds" rule has no "infinity" flag for CHALLENGE,
    # so -1 is rejected (not treated as "unlimited rounds").
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, rounds=-1)

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid value for Number of Rounds"}


def test_duels_rounds_config_allows_infinity_sentinel_directly(db_session, duels_configs):
    # DUELS isn't creatable via POST /api/game/create at all (see
    # test_live_and_duels_types_not_creatable_via_create_route below), so
    # this specific "duels allows -1 rounds" comparison is exercised
    # in-process against the rule object rather than over HTTP.
    duels_game = game_type[GameType.DUELS]
    rules_config = duels_game.rules_config()

    assert rules_config["rounds"]["infinity"] is True
    duels_game.check_rule(rules_config["rounds"], -1)  # must not raise
    with pytest.raises(Exception):
        duels_game.check_rule(rules_config["rounds"], -2)


@pytest.mark.parametrize("time_limit,expected_error", [
    (4, "Value for Time Limit too low"),
    (301, "Value for Time Limit too high"),
])
def test_create_time_limit_out_of_range_rejected(client, game_configs, time_limit, expected_error):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, time=time_limit)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}


def test_create_time_limit_infinity_sentinel_accepted(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = create_challenge(client, host, game_map, time=-1)

    assert response.status_code == 200, response.get_data(as_text=True)
    session_uuid = response.get_json()["id"]
    session = Session.query.filter_by(uuid=session_uuid).first()
    assert session.base_rules.time_limit == -1


def test_create_nmpz_toggle_produces_distinct_base_rules(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    off = create_challenge(client, host, game_map, nmpz=False)
    on = create_challenge(client, host, game_map, nmpz=True)

    assert off.status_code == 200 and on.status_code == 200
    off_session = Session.query.filter_by(uuid=off.get_json()["id"]).first()
    on_session = Session.query.filter_by(uuid=on.get_json()["id"]).first()
    assert off_session.base_rules.nmpz is False
    assert on_session.base_rules.nmpz is True
    assert off_session.base_rule_id != on_session.base_rule_id


def test_create_nmpz_non_boolean_type_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    # JSON `1` decodes to a Python int, not a bool - isinstance(1, bool) is
    # False, so this correctly fails the "boolean" type check.
    response = create_challenge(client, host, game_map, nmpz=1)

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid value for NMPZ"}


# ---------------------------------------------------------------------------
# BUG: two of the three rule defaults are the wrong type, so omitting them
# from the create payload crashes instead of falling back cleanly.
# ---------------------------------------------------------------------------

def test_create_missing_rounds_field_hits_broken_string_default(client, game_configs):
    """BaseGame.rules_config()'s "rounds" default is
    `Configs.get("GAME_DEFAULT_ROUNDS")` - a raw *string* ("5"), never
    converted to int (contrast with "nmpz" below, whose default IS
    converted). check_rules() falls back to that string whenever "rounds"
    is absent from the payload, and check_rule() then rejects it because
    `isinstance("5", int)` is False. So omitting "rounds" always 400s, even
    though GAME_DEFAULT_ROUNDS is a perfectly sane default value. Same bug
    applies to "time" - see the next test. Documenting actual (broken)
    behavior; not fixing app code."""
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = client.post(
        "/api/game/create",
        json={"type": "challenge", "map_id": game_map.uuid, "time": 60, "nmpz": False},
        headers=auth_header(host),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid value for Number of Rounds"}


def test_create_missing_time_field_hits_broken_string_default(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = client.post(
        "/api/game/create",
        json={"type": "challenge", "map_id": game_map.uuid, "rounds": 5, "nmpz": False},
        headers=auth_header(host),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid value for Time Limit"}


def test_create_missing_nmpz_field_uses_working_bool_default(client, game_configs):
    # Contrast with the two tests above: "nmpz"'s default IS pre-converted
    # to a real bool in rules_config() (`Configs.get(...).lower() == "true"`),
    # so omitting it from the payload works correctly.
    host = make_user()
    game_map = make_bounded_map(creator=host)

    response = client.post(
        "/api/game/create",
        json={"type": "challenge", "map_id": game_map.uuid, "rounds": 5, "time": 60},
        headers=auth_header(host),
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    session = Session.query.filter_by(uuid=response.get_json()["id"]).first()
    assert session.base_rules.nmpz is False  # GAME_DEFAULT_NMPZ == "False"


def test_live_and_duels_types_not_creatable_via_create_route(client, game_configs):
    """/api/game/routes.py's create_game() always calls
    `game_type[type].create(data, user)` with exactly two args, but
    LiveGame.create()/DuelsGame.create() both require a third `party`
    argument (they're only ever constructed through the party-lobby flow,
    not directly). So POST /api/game/create with type=live or type=duels
    always raises a TypeError, caught by return_400_on_error into a 400.
    Documenting actual behavior; LIVE/DUELS are simply not reachable here."""
    host = make_user()
    game_map = make_bounded_map(creator=host)

    for game_type_name in ("live", "duels"):
        response = client.post(
            "/api/game/create",
            json={"type": game_type_name, "map_id": game_map.uuid, "rounds": 5, "time": 60, "nmpz": False},
            headers=auth_header(host),
        )
        assert response.status_code == 400
        body = response.get_json()
        assert "error" in body, response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# GameState transitions for a CHALLENGE session
# ---------------------------------------------------------------------------

def test_challenge_state_transitions_and_no_game_state_tracker_row(client, game_configs):
    """Drives NOT_STARTED -> GUESSING -> RESULTS (repeated) -> FINISHED via
    the real API for a full 5-round game (5 is the minimum allowed by the
    "rounds" rule - see basegame.py's rules_config(), min=5), and confirms
    the discovered fact that CHALLENGE sessions never populate
    GameStateTracker at all - only PartyGame.create() (used by LIVE/DUELS)
    does that (app/api/game/games/party_game.py:16-21).
    ChallengeGame.get_state() computes state on the fly from
    Player/Guess/RoundStats rows instead."""
    host = make_user()
    game_map = make_bounded_map(creator=host)
    rounds = 5
    session_uuid = start_and_join(client, host, game_map, rounds=rounds, time=-1)
    session = Session.query.filter_by(uuid=session_uuid).first()

    assert get_state(client, host, session_uuid).get_json()["state"] == "NOT_STARTED"
    assert GameStateTracker.query.filter_by(session_id=session.id).first() is None

    for round_number in range(1, rounds + 1):
        next_round(client, host, session_uuid)
        assert get_state(client, host, session_uuid).get_json()["state"] == "GUESSING"

        submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)
        state = get_state(client, host, session_uuid).get_json()["state"]
        if round_number < rounds:
            assert state == "RESULTS"
        else:
            # Last round: jumps straight to FINISHED, RESULTS is skipped.
            assert state == "FINISHED"

    assert GameStateTracker.query.filter_by(session_id=session.id).first() is None


# ---------------------------------------------------------------------------
# timed_out() in the context of a real timed session (freezegun)
# ---------------------------------------------------------------------------

def test_late_guess_after_time_limit_is_rejected(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    with freeze_time("2024-01-01 12:00:00"):
        session_uuid = start_and_join(client, host, game_map, rounds=5, time=5)
        next_round(client, host, session_uuid)

        round_response = get_round(client, host, session_uuid).get_json()
        assert round_response["time_limit"] == 5

    with freeze_time("2024-01-01 12:00:06"):  # 6s later, limit was 5s
        state = get_state(client, host, session_uuid).get_json()
        assert state["state"] in ("RESULTS", "FINISHED")

        response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)

        assert response.status_code == 400
        assert response.get_json() == {"error": "Player is not in a playing state"}

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = Round.query.filter_by(session_id=session.id, round_number=1).first()
    assert Guess.query.filter_by(user_id=host.id, round_id=round_.id).count() == 0


def test_guess_within_time_limit_is_accepted(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    with freeze_time("2024-01-01 12:00:00"):
        session_uuid = start_and_join(client, host, game_map, rounds=5, time=5)
        next_round(client, host, session_uuid)

    with freeze_time("2024-01-01 12:00:04"):  # 4s later, still within 5s
        response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)
        assert response.status_code == 200, response.get_data(as_text=True)


def test_infinity_time_limit_sentinel_never_times_out(client, game_configs):
    host = make_user()
    game_map = make_bounded_map(creator=host)

    with freeze_time("2024-01-01 12:00:00"):
        session_uuid = start_and_join(client, host, game_map, rounds=5, time=-1)
        next_round(client, host, session_uuid)

    with freeze_time("2024-01-31 12:00:00"):  # 30 days later
        state = get_state(client, host, session_uuid).get_json()
        assert state["state"] == "GUESSING"

        response = submit_guess(client, host, session_uuid, LOCATION_LAT, LOCATION_LNG)
        assert response.status_code == 200, response.get_data(as_text=True)


def test_timed_out_unit_level_sanity_check_for_negative_one_sentinel():
    # Direct sanity check of the utility function itself, matching
    # tests/unit/test_scoring.py's documentation of the same fact, just
    # re-confirmed here in the context of this file's timing tests.
    ancient_start = datetime(2000, 1, 1)
    assert timed_out(ancient_start, -1) is False


# ---------------------------------------------------------------------------
# POST /api/game/ping - heartbeat/timeout resolution
# ---------------------------------------------------------------------------

def test_ping_after_timeout_with_no_plonk_hits_signature_mismatch_documents_bug(client, game_configs):
    """Genuine production bug, not a fixture artifact: POST /api/game/ping's
    view (routes.py) always calls
    `game_type[session.type].ping(data, user, session)` - three positional
    args - but every ping() in the class hierarchy only accepts (user,
    session): BaseGame.ping(self, user, session) (basegame.py:71, inherited
    unchanged by PartyGame/LiveGame/DuelsGame, none of which override it)
    and ChallengeGame.ping(self, user, session) (challenge.py:319). So the
    route ALWAYS raises
    `TypeError: ...ping() takes 3 positional arguments but 4 were given`,
    turned into a 400 by return_400_on_error - for every game type, in every
    state. The "ping after timeout" scoring behavior this test was
    originally meant to exercise (create_guess_on_timeout() ->
    create_round_stats(), recording a zeroed-out RoundStats row for a
    no-show player) does happen elsewhere - e.g. ChallengeGame.next()/
    results()/summary() all call `self.ping(user, session)` internally with
    the correct 2-arg signature - but it can never be triggered through this
    HTTP endpoint itself. Documenting the endpoint's real, current
    behavior."""
    host = make_user()
    game_map = make_bounded_map(creator=host)

    with freeze_time("2024-01-01 12:00:00"):
        session_uuid = start_and_join(client, host, game_map, rounds=5, time=5)
        next_round(client, host, session_uuid)
        # No guess, no plonk placed.

    with freeze_time("2024-01-01 12:00:10"):
        response = ping(client, host, session_uuid)

    assert response.status_code == 400
    body = response.get_json()
    assert "ping()" in body["error"]
    assert "positional argument" in body["error"]

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = Round.query.filter_by(session_id=session.id, round_number=1).first()
    # Because ping() never actually executes through this route, no Guess or
    # RoundStats row is created at all - contrast with the "internal" ping
    # call path (inside next()/results()/summary()), which does work.
    assert Guess.query.filter_by(user_id=host.id, round_id=round_.id).count() == 0
    assert RoundStats.query.filter_by(session_id=session.id, user_id=host.id, round=1).first() is None


def test_ping_after_timeout_with_plonk_hits_signature_mismatch_documents_bug(client, game_configs):
    """Same root cause as
    test_ping_after_timeout_with_no_plonk_hits_signature_mismatch_documents_bug above -
    POST /api/game/ping's view/ping() signature mismatch means the route is
    broken for every game type/state. Here the player placed a provisional
    plonk before the timeout, so if the endpoint worked,
    create_guess_on_timeout() would have converted it into a real Guess and
    deleted the PlayerPlonk row. It never gets the chance: the TypeError
    fires before any of that runs, so the plonk is simply left untouched."""
    host = make_user()
    game_map = make_bounded_map(creator=host)

    plonk_lat, plonk_lng = 41.001, -73.001

    with freeze_time("2024-01-01 12:00:00"):
        session_uuid = start_and_join(client, host, game_map, rounds=5, time=5)
        next_round(client, host, session_uuid)
        response = do_plonk(client, host, session_uuid, plonk_lat, plonk_lng)
        assert response.status_code == 200

    session = Session.query.filter_by(uuid=session_uuid).first()
    round_ = Round.query.filter_by(session_id=session.id, round_number=1).first()
    assert PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).count() == 1

    with freeze_time("2024-01-01 12:00:10"):
        response = ping(client, host, session_uuid)

    assert response.status_code == 400
    body = response.get_json()
    assert "ping()" in body["error"]
    assert "positional argument" in body["error"]

    # The provisional plonk is left untouched - it never got converted.
    assert PlayerPlonk.query.filter_by(user_id=host.id, round_id=round_.id).count() == 1
    assert Guess.query.filter_by(user_id=host.id, round_id=round_.id).count() == 0

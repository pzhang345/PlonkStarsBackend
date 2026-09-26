"""Integration tests for the LIVE party game mode
(app/api/game/games/live.py, party_game.py, basegame.py), driven through the
real HTTP API: POST /api/party/create, /api/party/join, /api/party/game/start
and the generic /api/game/* routes (create/play/next/round/guess/state/
results are shared across game types - dispatch is `game_type[session.type]`,
see app/api/game/routes.py and app/api/party/game/routes.py).

Route shapes exercised here (confirmed by reading the source, not guessed):
  * POST /api/party/create               (no body) -> {"code": <4-char code>}
      - Also creates a default BaseRules + DuelRules row using several
        Configs keys (see _seed_live_configs below); ALL of them must exist
        for this route to succeed, even though this file never touches
        duels. PartyRules.type defaults to GameType.LIVE at the model level
        (models/party.py), so a freshly created party is already LIVE-typed
        - no /api/party/rules call is needed to get there.
  * POST /api/party/join      {"code"}    -> {"message": "joined party"}
      - Every PartyMember defaults to in_lobby=True (models/party.py), so
        joining alone is enough to be picked up as a Player when the game
        starts; no separate /api/party/lobby/join call is required.
  * POST /api/party/game/start {"code"}   -> {"message": "session started"}
      - Host only (403 otherwise). Internally: LiveGame.create() builds the
        Session + one Player per in-lobby PartyMember, then LiveGame.next()
        is called once immediately (with user=None -> resolved to
        session.host) to start round 1. party.session_id is set to the new
        session's id.
  * POST /api/game/play        {"id"}     -> {"message": "session joined"} (403 if already played)
  * POST /api/game/next        {"id"}     -> {"success": true} normally (LiveGame.next()
        returns None on most paths); host-only for LIVE (LiveGame.next()
        raises "You are not the host" for anyone else, checked before any
        state check).
  * GET  /api/game/round?id=..            -> same shape as CHALLENGE (test_challenge_game.py)
  * POST /api/game/guess       {"id","lat","lng"} -> {"message":"guess added"} (via
        ChallengeGame().guess(), then LiveGame.guess() checks whether every
        Player in the session now has a Guess row for the round; if so it
        calls stop_current_task(session) and flips the GameStateTracker to
        RESULTS)
  * GET  /api/game/state?id=..            -> {"state": ...} (LiveGame.get_state, tracker-driven)
  * GET  /api/game/results?id=..          -> only reachable once the tracker is in
        RESULTS (LiveGame.results() 400s with "not correct state" otherwise),
        and even then delegates to ChallengeGame().results(), which is
        independently broken by the query.paginate bug already pinned in
        tests/bugs.md ("Game and session" section) - see
        test_results_after_round_ends_still_hits_known_paginate_bug_documents_bug.

Celery: LiveGame.next()/guess() call `update_game_state`/`stop_current_task`,
imported by name into api.game.games.live (`from api.game.tasks import
stop_current_task, update_game_state`). Patched at that import site by the
autouse `mock_celery` fixture below so no Celery/redis is ever touched.
Note LiveGame.update_state() (the FINISHED-processing method on the class
itself) is a different thing entirely from the module-level
`update_game_state` Celery helper - finishing a game calls the former
directly/synchronously, never going through Celery at all.

Hard rule compliance: this file owns all of its own setup. It does not
import or depend on tests/integration/party/conftest.py or
tests/integration/game/conftest.py (both are being built out by another
agent in parallel) - party/live-game scaffolding lives in the private
helpers below (_make_live_party, _start_live_game, etc.), written so they
can later be lifted into tests/factories.py.
"""

from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from models.configs import Configs
from models.db import db
from models.map import Bound, MapBound
from models.party import Party
from models.session import GameState, GameStateTracker, GameType, Guess, Player, Round, Session
from tests.factories import make_map, make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration

LIVE_LAT = 12.0
LIVE_LNG = 34.0


# ---------------------------------------------------------------------------
# Local fixtures/helpers - scoped to this file only (hard rule: don't touch
# tests/conftest.py, tests/factories.py, or the party/game conftest.py files
# another agent owns).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    """Every test here eventually starts a round, which generates a
    location via api.location.generate.generate_location."""
    return street_view_mock


@pytest.fixture(autouse=True)
def mock_celery(monkeypatch):
    """Patch update_game_state/stop_current_task where LiveGame imports them
    (api.game.games.live), per the task's hard rule. Autouse so every test
    in this file is protected even if it doesn't inspect the mocks; tests
    that DO want to assert on calls just add `mock_celery` as a normal
    parameter - pytest fixture caching hands back the same instance."""
    update_mock = MagicMock(name="update_game_state")
    stop_mock = MagicMock(name="stop_current_task")
    monkeypatch.setattr("api.game.games.live.update_game_state", update_mock)
    monkeypatch.setattr("api.game.games.live.stop_current_task", stop_mock)
    return update_mock, stop_mock


def make_bounded_map(creator=None, lat=LIVE_LAT, lng=LIVE_LNG, max_distance=1000.0):
    """Same trick as test_challenge_game.py/test_game_rules_and_state.py: a
    single-point Bound so every generated round lands on exactly (lat, lng)
    (combined with the street_view_mock fixture)."""
    game_map = make_map(creator=creator, max_distance=max_distance, total_weight=1)
    bound = Bound(start_latitude=lat, start_longitude=lng, end_latitude=lat, end_longitude=lng)
    db.session.add(bound)
    db.session.flush()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=1))
    db.session.commit()
    return game_map


def _seed_live_configs(game_map, rounds=2, time_limit=-1, nmpz=False):
    """Configs read by POST /api/party/create (app/api/party/routes.py).
    None of the DUELS_* values are exercised by this file's LIVE-only
    scenarios, but create_party() reads them unconditionally to build a
    default DuelRules row regardless of the party's actual game type, so
    they must all exist too."""
    values = {
        "GAME_DEFAULT_MAP_ID": str(game_map.id),
        "GAME_DEFAULT_ROUNDS": str(rounds),
        "GAME_DEFAULT_TIME_LIMIT": str(time_limit),
        "GAME_DEFAULT_NMPZ": str(nmpz),
        "DUELS_DEFAULT_START_HP": "6000",
        "DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND": "1",
        "DUELS_DEFAULT_DAMAGE_MULTI_MULT": "1",
        "DUELS_DEFAULT_DAMAGE_MULTI_ADD": "0",
        "DUELS_DEFAULT_DAMAGE_MULTI_FREQ": "1",
        "DUELS_DEFAULT_GUESS_TIME_LIMIT": "15",
    }
    for key, value in values.items():
        db.session.add(Configs(key=key, value=value))
    db.session.commit()
    return values


def _make_live_party(client, host, members, rounds=2, time_limit=-1, lat=LIVE_LAT, lng=LIVE_LNG):
    """Build a LIVE-type party with `host` plus every user in `members`
    sitting in the lobby, ready for POST /api/party/game/start. Returns
    (code, game_map)."""
    game_map = make_bounded_map(creator=host, lat=lat, lng=lng)
    _seed_live_configs(game_map, rounds=rounds, time_limit=time_limit)

    response = client.post("/api/party/create", headers=auth_header(host))
    assert response.status_code == 200, response.get_data(as_text=True)
    code = response.get_json()["code"]

    for member in members:
        response = client.post("/api/party/join", json={"code": code}, headers=auth_header(member))
        assert response.status_code == 200, response.get_data(as_text=True)

    return code, game_map


def _start_live_game(client, host, code):
    return client.post("/api/party/game/start", json={"code": code}, headers=auth_header(host))


def _session_for_code(code):
    party = Party.query.filter_by(code=code).first()
    return party.session


def _play(client, user, session_uuid):
    return client.post("/api/game/play", json={"id": session_uuid}, headers=auth_header(user))


def _next(client, user, session_uuid):
    return client.post("/api/game/next", json={"id": session_uuid}, headers=auth_header(user))


def _round(client, user, session_uuid):
    return client.get(f"/api/game/round?id={session_uuid}", headers=auth_header(user))


def _guess(client, user, session_uuid, lat, lng):
    return client.post("/api/game/guess", json={"id": session_uuid, "lat": lat, "lng": lng}, headers=auth_header(user))


def _state(client, user, session_uuid):
    return client.get(f"/api/game/state?id={session_uuid}", headers=auth_header(user))


def _results(client, user, session_uuid, **params):
    query = "&".join([f"id={session_uuid}"] + [f"{k}={v}" for k, v in params.items()])
    return client.get(f"/api/game/results?{query}", headers=auth_header(user))


# ---------------------------------------------------------------------------
# start / join
# ---------------------------------------------------------------------------

def test_start_creates_live_session_and_all_lobby_members_become_players(client):
    host = make_user()
    member1 = make_user()
    member2 = make_user()
    code, _ = _make_live_party(client, host, [member1, member2])

    response = _start_live_game(client, host, code)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == {"message": "session started"}

    session = _session_for_code(code)
    assert session is not None
    assert session.type == GameType.LIVE
    assert session.host_id == host.id

    player_user_ids = {p.user_id for p in Player.query.filter_by(session_id=session.id).all()}
    assert player_user_ids == {host.id, member1.id, member2.id}

    # start_party() calls LiveGame.next() once immediately, so round 1 is
    # already under way by the time the response comes back.
    tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
    assert tracker.state == GameState.GUESSING
    assert Round.query.filter_by(session_id=session.id, round_number=1).count() == 1


def test_non_host_cannot_start_live_game(client):
    host = make_user()
    member = make_user()
    code, _ = _make_live_party(client, host, [member])

    response = client.post("/api/party/game/start", json={"code": code}, headers=auth_header(member))

    assert response.status_code == 403
    assert response.get_json() == {"error": "You are not the host of this party"}
    assert _session_for_code(code) is None


def test_joining_started_game_twice_is_rejected(client):
    host = make_user()
    member = make_user()
    code, _ = _make_live_party(client, host, [member])
    _start_live_game(client, host, code)
    session = _session_for_code(code)

    # `member` is already a Player (auto-joined from the lobby by start()).
    response = _play(client, member, session.uuid)

    assert response.status_code == 403
    assert response.get_json() == {"error": "already played this session"}


# ---------------------------------------------------------------------------
# guessing / round end
# ---------------------------------------------------------------------------

def test_multiple_players_guessing_ends_the_round_and_stops_the_celery_task(client, mock_celery):
    update_mock, stop_mock = mock_celery
    host = make_user()
    member1 = make_user()
    member2 = make_user()
    code, _ = _make_live_party(client, host, [member1, member2], rounds=5, time_limit=-1)
    _start_live_game(client, host, code)
    session = _session_for_code(code)

    round_1 = Round.query.filter_by(session_id=session.id, round_number=1).first()

    # Untimed round (time_limit == -1): next() never schedules the Celery
    # timeout at all.
    update_mock.assert_not_called()

    response = _guess(client, host, session.uuid, LIVE_LAT, LIVE_LNG)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.GUESSING
    stop_mock.assert_not_called()

    response = _guess(client, member1, session.uuid, LIVE_LAT, LIVE_LNG)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.GUESSING
    stop_mock.assert_not_called()

    # Last player to guess flips the round to RESULTS and stops the task.
    response = _guess(client, member2, session.uuid, LIVE_LAT, LIVE_LNG)
    assert response.status_code == 200, response.get_data(as_text=True)

    assert Guess.query.filter_by(round_id=round_1.id).count() == 3
    assert {g.user_id for g in Guess.query.filter_by(round_id=round_1.id).all()} == {host.id, member1.id, member2.id}
    stop_mock.assert_called_once()
    assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.RESULTS


def test_results_hidden_while_round_is_still_guessing(client):
    host = make_user()
    member = make_user()
    code, _ = _make_live_party(client, host, [member])
    _start_live_game(client, host, code)
    session = _session_for_code(code)

    # Nobody has guessed yet - tracker is still GUESSING.
    response = _results(client, host, session.uuid, round=1)

    assert response.status_code == 400
    assert response.get_json() == {"error": "not correct state"}


def test_results_after_round_ends_still_hits_known_paginate_bug_documents_bug(client):
    """Once the round genuinely reaches RESULTS, LiveGame.results()'s own
    gate (`state.state != GameState.RESULTS`) opens - but it then delegates
    straight to ChallengeGame().results(), which is independently broken by
    the query.paginate bug already pinned in tests/bugs.md ("Game and
    session" -> query.paginate doesn't exist, pinned by
    test_challenge_game.py::test_results_endpoint_is_broken_by_query_paginate_bug,
    whose docstring already notes "This affects LIVE too"). So results are
    never actually visible through this route today, in either state -
    just with a different error message. Documenting actual behavior, not
    fixing app code."""
    host = make_user()
    member = make_user()
    code, _ = _make_live_party(client, host, [member])
    _start_live_game(client, host, code)
    session = _session_for_code(code)

    _guess(client, host, session.uuid, LIVE_LAT, LIVE_LNG)
    _guess(client, member, session.uuid, LIVE_LAT, LIVE_LNG)
    assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.RESULTS

    response = _results(client, host, session.uuid, round=1)

    assert response.status_code == 400
    body = response.get_json()
    assert "paginate" in body["error"]


# ---------------------------------------------------------------------------
# next() authorization + full round-advance/finish flow
# ---------------------------------------------------------------------------

def test_non_host_next_rejected_host_advances_and_game_finishes_after_max_rounds(client, mock_celery):
    update_mock, stop_mock = mock_celery
    host = make_user()
    member = make_user()

    with freeze_time("2024-06-01 12:00:00"):
        code, _ = _make_live_party(client, host, [member], rounds=2, time_limit=60)
        _start_live_game(client, host, code)
        session = _session_for_code(code)
        session_uuid = session.uuid

        # Round 1 started with a positive time_limit -> the Celery timeout
        # was scheduled once.
        assert update_mock.call_count == 1
        args, _kwargs = update_mock.call_args
        assert args[0] == {"state": GameState.RESULTS}
        assert args[1].id == session.id
        assert args[2] == 61  # time_limit(60) + 1

        # A non-host calling next() mid-round is rejected outright - the
        # host check runs before any state check.
        response = _next(client, member, session_uuid)
        assert response.status_code == 400
        assert response.get_json() == {"error": "You are not the host"}
        assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.GUESSING

        _guess(client, host, session_uuid, LIVE_LAT, LIVE_LNG)
        _guess(client, member, session_uuid, LIVE_LAT, LIVE_LNG)
        assert stop_mock.call_count == 1
        assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.RESULTS

        # Host advances to round 2.
        response = _next(client, host, session_uuid)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.GUESSING
        assert Round.query.filter_by(session_id=session.id, round_number=2).count() == 1
        for player in Player.query.filter_by(session_id=session.id).all():
            assert player.current_round == 2
        assert update_mock.call_count == 2  # round 2's timeout scheduled too

        # Non-host next() is rejected again, mid round 2.
        response = _next(client, member, session_uuid)
        assert response.status_code == 400
        assert response.get_json() == {"error": "You are not the host"}

        round_2 = Round.query.filter_by(session_id=session.id, round_number=2).first()
        _guess(client, host, session_uuid, LIVE_LAT, LIVE_LNG)
        _guess(client, member, session_uuid, LIVE_LAT, LIVE_LNG)
        assert Guess.query.filter_by(round_id=round_2.id).count() == 2
        assert stop_mock.call_count == 2
        assert GameStateTracker.query.filter_by(session_id=session.id).first().state == GameState.RESULTS

        # Round 2 was the last round (max_rounds == 2): next() finishes the
        # game instead of starting a round 3. Finishing goes through
        # LiveGame.update_state() directly/synchronously - NOT through the
        # Celery-mocked update_game_state helper, so the call counts above
        # don't change.
        response = _next(client, host, session_uuid)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert update_mock.call_count == 2
        assert stop_mock.call_count == 2

        assert GameStateTracker.query.filter_by(session_id=session.id).first() is None
        finished_session = Session.query.filter_by(id=session.id).first()
        assert finished_session.type == GameType.CHALLENGE  # LiveGame.update_state() resets this on FINISHED
        assert Party.query.filter_by(code=code).first().session_id is None

        response = _state(client, host, session_uuid)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["state"] == "FINISHED"

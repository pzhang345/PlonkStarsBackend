"""Integration tests for app/api/session/routes.py and app/api/session/session.py.

Covers every route in the session blueprint (info, daily, default, host) plus
the two helper functions in api/session/session.py (get_session_info and
clean_demo_sessions) exercised directly where that gives a more precise
assertion than going through HTTP.
"""

from datetime import datetime, timedelta

import pytest
import pytz

from api.session.session import clean_demo_sessions, get_session_info
from models.configs import Configs
from models.db import db
from models.map import Bound, MapBound
from models.session import DailyChallenge, GameType, Player, Session
from tests.factories import make_base_rules, make_map, make_session, make_user
from tests.helpers import assert_json_error, auth_header, demo_header

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Local helpers (not shared scaffolding - candidates for promotion, see report)
# ---------------------------------------------------------------------------

def _seed_configs(**pairs):
    """Insert Configs rows from kwargs, stringifying values (Configs.value is
    a plain String(50) column; every reader does int(...)/str(...).lower())."""
    for key, value in pairs.items():
        db.session.add(Configs(key=key, value=str(value)))
    db.session.commit()


def _attach_point_bound(game_map):
    """Give a map a single-point Bound/MapBound pair so
    api.location.generate.get_random_bounds()/generate_location() can resolve
    a bound for it. A "point" bound (start == end) is what makes
    generate_location call check_multiple_street_views(bound, 1) - matching
    exactly what the street_view_mock fixture fakes.
    """
    weight = game_map.total_weight or 1
    bound = Bound(
        start_latitude=1.0, start_longitude=2.0,
        end_latitude=1.0, end_longitude=2.0,
    )
    db.session.add(bound)
    db.session.commit()
    db.session.add(MapBound(bound_id=bound.id, map_id=game_map.id, weight=weight))
    db.session.commit()
    return bound


def _seed_daily_config(rounds=2, time_limit=-1, nmpz=False, host_username="daily_host"):
    host = make_user(username=host_username)
    game_map = make_map(creator=host, name="Daily Map " + host_username)
    _attach_point_bound(game_map)
    rules = make_base_rules(game_map=game_map, time_limit=time_limit, max_rounds=rounds, nmpz=nmpz)
    _seed_configs(
        DAILY_DEFAULT_ROUNDS=rounds,
        DAILY_DEFAULT_TIME_LIMIT=time_limit,
        DAILY_DEFAULT_NMPZ=str(nmpz),
        DAILY_DEFAULT_MAP_ID=game_map.id,
        DAILY_DEFAULT_HOST_ID=host.id,
    )
    return host, game_map, rules


# ---------------------------------------------------------------------------
# GET /api/session/info
# ---------------------------------------------------------------------------

def test_session_info_happy_path_returns_seeded_data(client):
    host = make_user(username="info_host")
    game_map = make_map(creator=host, name="Info Map")
    rules = make_base_rules(game_map=game_map, time_limit=30, max_rounds=7, nmpz=True)
    session = make_session(host=host, base_rules=rules)

    response = client.get(f"/api/session/info?id={session.uuid}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    assert body["host"] == "info_host"
    assert body["rules"] == {"NMPZ": True, "time": 30, "rounds": 7}
    assert body["map"]["name"] == "Info Map"
    assert body["map"]["id"] == game_map.uuid
    assert body["map"]["creator"] == "info_host"
    # No MapStats row exists yet for this map -> average_score/total_guesses
    # both fall back to 0, and no GenerationTime row exists either.
    assert body["map"]["average_score"] == 0
    assert body["map"]["total_guesses"] == 0
    assert body["map"]["average_generation_time"] == 0
    # Host has no Player row on their own session yet.
    assert body["state"] == "NOT_STARTED"


def test_session_info_unknown_uuid_returns_404(client):
    user = make_user()

    response = client.get("/api/session/info?id=does-not-exist", headers=auth_header(user))

    body = assert_json_error(response, 404)
    assert body["error"] == "Session not found"


def test_session_info_missing_id_param_returns_404(client):
    user = make_user()

    response = client.get("/api/session/info", headers=auth_header(user))

    body = assert_json_error(response, 404)
    assert body["error"] == "Session not found"


def test_session_info_non_host_before_host_finished_returns_400(client):
    """The route has no explicit "are you a participant of this session?"
    check. What actually gates a non-host caller out is a side effect of
    ChallengeGame.get_state's RESTRICTED branch: any non-host user on a
    non-daily session where the host hasn't finished all rounds hits this,
    surfaced as a 400 (not 403/404). Documenting actual behavior.
    """
    host = make_user(username="restricted_host")
    outsider = make_user(username="outsider")
    session = make_session(host=host)

    response = client.get(f"/api/session/info?id={session.uuid}", headers=auth_header(outsider))

    body = assert_json_error(response, 400)
    assert body["error"] == "host has not finished game"


def test_session_info_demo_host_session_rejected(client):
    demo = make_user(username="demo")
    session = make_session(host=demo)
    caller = make_user()

    response = client.get(f"/api/session/info?id={session.uuid}", headers=auth_header(caller))

    body = assert_json_error(response, 400)
    assert body["error"] == "Cannot play a demo session"


def test_session_info_requires_auth(client):
    session = make_session()

    response = client.get(f"/api/session/info?id={session.uuid}")

    assert_json_error(response, 403)


# ---------------------------------------------------------------------------
# get_session_info() / clean_demo_sessions() called directly
# ---------------------------------------------------------------------------

def test_get_session_info_function_directly_matches_seeded_data(db_session):
    host = make_user(username="direct_host")
    game_map = make_map(creator=host, name="Direct Map")
    rules = make_base_rules(game_map=game_map, time_limit=-1, max_rounds=3, nmpz=False)
    session = make_session(host=host, base_rules=rules)

    info = get_session_info(session, host)

    assert info["host"] == "direct_host"
    assert info["rules"] == {"NMPZ": False, "time": -1, "rounds": 3}
    assert info["state"] == "NOT_STARTED"


def test_get_session_info_raises_for_non_challenge_session(db_session):
    session = make_session(game_type=GameType.LIVE)

    with pytest.raises(Exception, match="not a challenge session"):
        get_session_info(session, session.host)


def test_clean_demo_sessions_removes_old_but_keeps_recent_and_non_demo(db_session):
    demo = make_user(username="demo")
    other_host = make_user(username="not_demo_host")

    old_session = make_session(host=demo)
    recent_session = make_session(host=demo)
    non_demo_session = make_session(host=other_host)

    old_player_user = make_user(username="old_demo_player")
    recent_player_user = make_user(username="recent_demo_player")

    old_time = datetime.now(tz=pytz.utc) - timedelta(days=2)
    recent_time = datetime.now(tz=pytz.utc) - timedelta(hours=1)

    db.session.add(Player(session_id=old_session.id, user_id=old_player_user.id, start_time=old_time))
    db.session.add(Player(session_id=recent_session.id, user_id=recent_player_user.id, start_time=recent_time))
    db.session.commit()

    # Capture ids up front: clean_demo_sessions() commits internally, which
    # expires these ORM instances - and old_session's row won't exist anymore
    # afterward, so accessing old_session.id post-commit would itself raise
    # ObjectDeletedError while trying to auto-refresh a deleted row.
    old_session_id = old_session.id
    recent_session_id = recent_session.id
    non_demo_session_id = non_demo_session.id

    clean_demo_sessions()

    assert db.session.get(Session, old_session_id) is None
    assert db.session.get(Session, recent_session_id) is not None
    assert db.session.get(Session, non_demo_session_id) is not None


# ---------------------------------------------------------------------------
# GET /api/session/daily
# ---------------------------------------------------------------------------

def test_daily_challenge_created_and_idempotent(client, street_view_mock):
    _seed_daily_config(rounds=2, host_username="daily_host_idem")
    caller = make_user(username="daily_caller")

    first = client.get("/api/session/daily", headers=auth_header(caller))
    assert first.status_code == 200
    first_body = first.get_json()
    assert "id" in first_body
    assert "next" in first_body
    assert "now" in first_body

    second = client.get("/api/session/daily", headers=auth_header(caller))
    assert second.status_code == 200
    second_body = second.get_json()

    # Idempotent: same underlying session both times.
    assert first_body["id"] == second_body["id"]

    today = datetime.now(tz=pytz.utc).date()
    dailies = DailyChallenge.query.filter_by(date=today).all()
    assert len(dailies) == 1
    assert dailies[0].session.uuid == first_body["id"]


def test_daily_challenge_works_with_demo_token(client, street_view_mock):
    _seed_daily_config(rounds=2, host_username="daily_host_demo")
    make_user(username="demo")

    response = client.get("/api/session/daily", headers=demo_header())

    assert response.status_code == 200
    body = response.get_json()
    assert "id" in body


# ---------------------------------------------------------------------------
# GET /api/session/default
# ---------------------------------------------------------------------------

def test_session_default_reflects_seeded_configs(client):
    game_map = make_map(name="Default Map")
    _seed_configs(
        GAME_DEFAULT_ROUNDS=5,
        GAME_DEFAULT_TIME_LIMIT=60,
        GAME_DEFAULT_NMPZ="true",
        GAME_DEFAULT_MAP_ID=game_map.id,
    )

    response = client.get("/api/session/default")

    assert response.status_code == 200
    assert response.get_json() == {
        "mapName": "Default Map",
        "map_id": game_map.uuid,
        "time": 60,
        "rounds": 5,
        "nmpz": True,
    }


def test_session_default_missing_configs_raises_unhandled_typeerror(client):
    """BUG: GET /api/session/default does not guard against missing Configs
    rows. Configs.get() returns None when a key is absent, and
    int(Configs.get("GAME_DEFAULT_ROUNDS")) then raises TypeError with no
    try/except anywhere in the call path. There is no error handler
    registered on the Flask app (see app/factory.py), so in production this
    would surface to the client as a bare 500 with no JSON body (not the
    {"error": ...} shape every other route in this file uses). Under
    TESTING=True, Flask propagates the exception instead of turning it into
    a response, which is what this test observes directly.
    """
    with pytest.raises(TypeError):
        client.get("/api/session/default")


# ---------------------------------------------------------------------------
# GET /api/session/host
# ---------------------------------------------------------------------------

def test_is_host_true_for_host(client):
    host = make_user(username="host_true")
    session = make_session(host=host)

    response = client.get(f"/api/session/host?id={session.uuid}", headers=auth_header(host))

    assert response.status_code == 200
    assert response.get_json() == {"is_host": True}


def test_is_host_false_for_non_host(client):
    host = make_user(username="host_false_host")
    other = make_user(username="host_false_rando")
    session = make_session(host=host)

    response = client.get(f"/api/session/host?id={session.uuid}", headers=auth_header(other))

    assert response.status_code == 200
    assert response.get_json() == {"is_host": False}


def test_is_host_unknown_session_returns_non_json_404(client):
    """FINDING (API inconsistency, not fixed here): unlike /api/session/info
    (which returns jsonify({"error": ...}), 404), this route uses
    Session.query...first_or_404("Session not found"), which aborts with
    werkzeug's default HTML error page - there is no JSON error handler
    registered anywhere in app/factory.py. So this 404's body is NOT the
    {"error": ...} shape the rest of the session API uses.
    """
    user = make_user()

    response = client.get("/api/session/host?id=missing-uuid", headers=auth_header(user))

    assert response.status_code == 404
    assert response.content_type != "application/json"
    body = response.get_json(silent=True)
    assert body is None


def test_is_host_requires_auth(client):
    session = make_session()

    response = client.get(f"/api/session/host?id={session.uuid}")

    assert_json_error(response, 403)

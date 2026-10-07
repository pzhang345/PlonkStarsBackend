"""Party game start/join/state routes.

Scope: start/join/state. The full duel flow through these routes is
covered end-to-end in integration/game/test_duels_game.py - so these stubs
cover the party-side game routes in isolation.

Route shapes confirmed by reading app/api/party/game/routes.py:
  * POST /start: host-only (403 otherwise); 400 if "code" missing; 404 for
    an unknown code; delegates to game_type[party.rules.type].create(), so
    for a DUELS party with < 2 teams it 400s ("Not enough teams"). On
    success it synchronously calls .next(...) too, so round 1 is already
    GUESSING by the time the response comes back (see
    integration/game/test_duels_game.py for the full flow).
  * POST /join: 404 if the party has no session yet; otherwise delegates to
    game_type[session.type].join(). DuelsGame.join() is a no-op (`pass`),
    so for a DUELS session this always "succeeds" (return_400_on_error's
    `if not ret: return jsonify(success=True), 200` branch) without
    creating any Player row or doing anything else - it does NOT add
    anyone to a team; team membership only comes from /party/teams/join.
  * GET  /state: {"state": "lobby"} if the party has no session; otherwise
    {"state": "playing", "id", "type", "joined"} where "joined" reflects a
    `Player` row for (user, session) - which DUELS sessions never create,
    so `joined` is always False for a DUELS party even for players who are
    actively on a team and guessing.
"""

import pytest
from freezegun import freeze_time

from models.db import db
from models.session import GameState, GameStateTracker, GameType, Session
from tests.factories import make_base_rules, make_bounded_map, make_duel_rules, make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration

LOCATION_LAT = 10.0
LOCATION_LNG = 20.0


@pytest.fixture(autouse=True)
def _mock_celery(monkeypatch):
    monkeypatch.setattr("api.game.games.duels.update_game_state", lambda *a, **k: None)
    monkeypatch.setattr("api.game.games.duels.stop_current_task", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _mock_street_view_for_every_test(street_view_mock):
    return street_view_mock


def configure_duels_party(party, time_limit=-1):
    """two_team_party's default rules point at a blank, unbounded map - swap
    in a bounded one so DuelsGame.create()/.next() can actually generate a
    round via street_view_mock (mirrors the helper in
    integration/game/test_duels_game.py)."""
    game_map = make_bounded_map(lat=LOCATION_LAT, lng=LOCATION_LNG)
    base_rules = make_base_rules(game_map=game_map, time_limit=time_limit, max_rounds=-1, nmpz=False)
    duel_rules = make_duel_rules(start_hp=6000, guess_time_limit=5)
    party.rules.base_rule_id = base_rules.id
    party.rules.duel_rules_id = duel_rules.id
    db.session.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/party/game/start", {"code": "AAAA"}),
    ("post", "/api/party/game/join", {"code": "AAAA"}),
    ("get", "/api/party/game/state?code=AAAA", None),
])
def test_game_routes_reject_anonymous_and_demo_callers_with_403(client, method, path, body):
    call = getattr(client, method)
    kwargs = {} if body is None else {"json": body}

    assert call(path, **kwargs).status_code == 403
    assert call(path, headers=demo_header(), **kwargs).status_code == 403


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

def test_game_start_creates_a_game_for_the_party(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    configure_duels_party(party)

    with freeze_time("2024-01-01 12:00:00"):
        response = client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 200
    session = Session.query.filter_by(host_id=host.id, type=GameType.DUELS).order_by(Session.id.desc()).first()
    assert session is not None
    db.session.refresh(party)
    assert party.session_id == session.id
    tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
    assert tracker.state == GameState.GUESSING  # start_party() folds in the first next() call


def test_game_start_requires_host(client, two_team_party):
    party = two_team_party["party"]
    configure_duels_party(party)
    non_host = two_team_party["team_b_users"][0]

    response = client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(non_host))

    assert response.status_code == 403


def test_game_start_missing_code_returns_400(client):
    user = make_user()

    response = client.post("/api/party/game/start", json={}, headers=auth_header(user))

    assert response.status_code == 400


def test_game_start_unknown_code_returns_404(client):
    user = make_user()

    response = client.post("/api/party/game/start", json={"code": "ZZZZ"}, headers=auth_header(user))

    assert response.status_code == 404


def test_game_start_with_fewer_than_two_teams_is_rejected(client, party_with_members):
    party, host, members = party_with_members
    configure_duels_party(party)

    response = client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 400
    assert response.get_json() == {"error": "Not enough teams"}
    db.session.refresh(party)
    assert party.session_id is None


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------

def test_game_join_without_started_session_returns_404(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]

    response = client.post("/api/party/game/join", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 404


def test_game_join_is_a_success_noop_for_duels(client, two_team_party):
    """DuelsGame.join() is `pass` - the route reports success regardless of
    who calls it or whether they're even on a team, and it creates no
    Player row (DUELS never uses the Player model at all)."""
    party = two_team_party["party"]
    host = two_team_party["host"]
    configure_duels_party(party)
    with freeze_time("2024-01-01 12:00:00"):
        client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(host))

    stranger = make_user()  # not even a party member
    response = client.post("/api/party/game/join", json={"code": party.code}, headers=auth_header(stranger))

    assert response.status_code == 200
    assert response.get_json() == {"success": True}


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

def test_game_state_returns_lobby_when_no_session(client, party_with_host):
    party, host = party_with_host

    response = client.get(f"/api/party/game/state?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    assert response.get_json() == {"state": "lobby"}


def test_game_state_returns_playing_once_started(client, two_team_party):
    party = two_team_party["party"]
    host = two_team_party["host"]
    configure_duels_party(party)
    with freeze_time("2024-01-01 12:00:00"):
        client.post("/api/party/game/start", json={"code": party.code}, headers=auth_header(host))

    response = client.get(f"/api/party/game/state?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    assert body["state"] == "playing"
    assert body["type"] == "DUELS"
    # DUELS sessions never create a Player row, so `joined` is always False
    # here even though `host` is actively on a team in this session.
    assert body["joined"] is False


def test_game_state_unknown_code_returns_404(client):
    user = make_user()

    response = client.get("/api/party/game/state?code=ZZZZ", headers=auth_header(user))

    assert response.status_code == 404

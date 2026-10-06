"""Party create/join/leave/delete/lobby routes.

Scope:
- Routes: create, join by code, leave, and delete. Only the host can delete.
  An unknown code returns 404. Joining twice is idempotent.
- Lobby join and leave. The host leaving either transfers or deletes the
  party; document which one happens.

Route shapes confirmed by reading app/api/party/routes.py:
  * login_required() (no allow_demo=True anywhere in this file) means every
    route here rejects both an absent token AND the literal "demo" token
    with the SAME 403 {"error": "login required"} - never a 401.
  * POST /create reads several Configs.* keys directly (not through a game
    fixture), so it needs the `game_configs` fixture from this dir's
    conftest.py.
"""

import pytest

from models.configs import Configs
from models.db import db
from models.party import Party, PartyMember, PartyRules
from models.session import GameType
from tests.factories import make_map, make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Auth: every route here is login_required() with no allow_demo, so an
# anonymous or "demo" caller is rejected the same way (403, not 401).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/party/create", {}),
    ("post", "/api/party/join", {"code": "AAAA"}),
    ("get", "/api/party/host?code=AAAA", None),
    ("post", "/api/party/leave", {"code": "AAAA"}),
    ("post", "/api/party/delete", {"code": "AAAA"}),
    ("post", "/api/party/lobby/join", {"code": "AAAA"}),
    ("post", "/api/party/lobby/leave", {"code": "AAAA"}),
])
def test_routes_reject_anonymous_and_demo_callers_with_403(client, method, path, body):
    """Every party route here is login_required() without allow_demo, so a
    missing Authorization header AND the literal "demo" token both get
    403 {"error": "login required"} - never 401."""
    call = getattr(client, method)
    kwargs = {} if body is None else {"json": body}

    anon_response = call(path, **kwargs)
    assert anon_response.status_code == 403
    assert anon_response.get_json() == {"error": "login required"}

    demo_response = call(path, headers=demo_header(), **kwargs)
    assert demo_response.status_code == 403
    assert demo_response.get_json() == {"error": "login required"}


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def test_create_party_creates_a_party_with_the_caller_as_host(client, game_configs):
    user = make_user()
    # GAME_DEFAULT_MAP_ID from configs_default.json is a fixed literal ("1")
    # that doesn't correspond to any map created by this test's own
    # transaction (map ids keep climbing across the whole suite since
    # Postgres SERIAL sequences aren't rolled back by a SAVEPOINT) - point
    # it at a real map so create_party's BaseRules insert doesn't violate
    # the base_rules_map_id_fkey constraint.
    game_map = make_map()
    Configs.query.filter_by(key="GAME_DEFAULT_MAP_ID").update({"value": str(game_map.id)})
    db.session.commit()

    response = client.post("/api/party/create", headers=auth_header(user))

    assert response.status_code == 200
    code = response.get_json()["code"]

    party = Party.query.filter_by(code=code).first()
    assert party is not None
    assert party.host_id == user.id
    assert PartyMember.query.filter_by(party_id=party.id, user_id=user.id).count() == 1

    # PartyRules is built directly (see api/party/routes.py:create_party)
    # without ever setting `type`, so it keeps the model column default -
    # GameType.LIVE - even though tests.factories.make_party defaults to
    # DUELS for its own convenience.
    rules = PartyRules.query.filter_by(party_id=party.id).first()
    assert rules.type == GameType.LIVE


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------

def test_join_by_code_adds_the_user_to_the_party(client, party_with_host):
    party, host = party_with_host
    joiner = make_user()

    response = client.post("/api/party/join", json={"code": party.code}, headers=auth_header(joiner))

    assert response.status_code == 200
    assert PartyMember.query.filter_by(party_id=party.id, user_id=joiner.id).count() == 1


def test_join_with_unknown_code_returns_404(client):
    user = make_user()

    response = client.post("/api/party/join", json={"code": "ZZZZ"}, headers=auth_header(user))

    assert response.status_code == 404


def test_join_without_code_returns_400(client):
    user = make_user()

    response = client.post("/api/party/join", json={}, headers=auth_header(user))

    assert response.status_code == 400
    assert response.get_json() == {"error": "provided: code"}


def test_joining_twice_returns_403_without_duplicate_membership(client, party_with_host):
    """Actual behavior: a second join for an existing member is rejected
    with 403 (not silently accepted) - "idempotent" in the sense that no
    duplicate PartyMember row is ever created, but it is NOT a 200."""
    party, host = party_with_host
    joiner = make_user()
    first = client.post("/api/party/join", json={"code": party.code}, headers=auth_header(joiner))
    assert first.status_code == 200

    second = client.post("/api/party/join", json={"code": party.code}, headers=auth_header(joiner))

    assert second.status_code == 403
    assert second.get_json() == {"error": "You are already in this party"}
    assert PartyMember.query.filter_by(party_id=party.id, user_id=joiner.id).count() == 1


# ---------------------------------------------------------------------------
# host
# ---------------------------------------------------------------------------

def test_is_host_reports_true_for_the_host_and_false_for_a_member(client, party_with_members):
    party, host, members = party_with_members

    host_response = client.get(f"/api/party/host?code={party.code}", headers=auth_header(host))
    member_response = client.get(f"/api/party/host?code={party.code}", headers=auth_header(members[0]))

    assert host_response.get_json() == {"is_host": True}
    assert member_response.get_json() == {"is_host": False}


# ---------------------------------------------------------------------------
# leave
# ---------------------------------------------------------------------------

def test_leave_removes_the_user_from_the_party(client, party_with_members):
    party, host, members = party_with_members
    leaver = members[0]

    response = client.post("/api/party/leave", json={"code": party.code}, headers=auth_header(leaver))

    assert response.status_code == 200
    assert PartyMember.query.filter_by(party_id=party.id, user_id=leaver.id).count() == 0


def test_leave_unknown_code_returns_404(client):
    user = make_user()

    response = client.post("/api/party/leave", json={"code": "ZZZZ"}, headers=auth_header(user))

    assert response.status_code == 404


def test_host_leaving_the_party_is_rejected_documents_bug(client, party_with_host):
    """Documents which of "transfer" or "delete" happens when the host
    leaves via POST /party/leave: NEITHER. remove_user_from_party() raises
    "Cannot remove the host" for the host_id case, and leave_party() has no
    special-case for it, so the request 400s and the party (and the host's
    own membership) is left completely untouched. BUG: a host has no way to
    hand off or abandon a party except by deleting it outright via
    POST /party/delete (which destroys it for everyone, not just leaves)."""
    party, host = party_with_host

    response = client.post("/api/party/leave", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 400
    assert response.get_json() == {"error": "Cannot remove the host"}
    assert Party.query.filter_by(code=party.code).count() == 1
    assert PartyMember.query.filter_by(party_id=party.id, user_id=host.id).count() == 1


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_only_host_can_delete_the_party(client, party_with_members):
    party, host, members = party_with_members

    response = client.post("/api/party/delete", json={"code": party.code}, headers=auth_header(members[0]))

    assert response.status_code == 403
    assert Party.query.filter_by(code=party.code).count() == 1


def test_host_can_delete_the_party(client, party_with_host):
    party, host = party_with_host

    response = client.post("/api/party/delete", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 200
    assert Party.query.filter_by(code=party.code).count() == 0


def test_delete_unknown_code_returns_404(client):
    user = make_user()

    response = client.post("/api/party/delete", json={"code": "ZZZZ"}, headers=auth_header(user))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# lobby join/leave
# ---------------------------------------------------------------------------

def test_lobby_join_places_user_in_the_lobby(client, party_with_members):
    party, host, members = party_with_members
    member = members[0]
    pm = PartyMember.query.filter_by(party_id=party.id, user_id=member.id).first()
    pm.in_lobby = False
    db.session.commit()

    response = client.post("/api/party/lobby/join", json={"code": party.code}, headers=auth_header(member))

    assert response.status_code == 200
    db.session.refresh(pm)
    assert pm.in_lobby is True


def test_lobby_leave_removes_user_from_the_lobby(client, party_with_members):
    party, host, members = party_with_members
    member = members[0]
    pm = PartyMember.query.filter_by(party_id=party.id, user_id=member.id).first()
    assert pm.in_lobby is True  # make_party_member defaults in_lobby=True

    response = client.post("/api/party/lobby/leave", json={"code": party.code}, headers=auth_header(member))

    assert response.status_code == 200
    db.session.refresh(pm)
    assert pm.in_lobby is False


def test_lobby_join_for_non_member_returns_404(client, party_with_host):
    party, host = party_with_host
    stranger = make_user()

    response = client.post("/api/party/lobby/join", json={"code": party.code}, headers=auth_header(stranger))

    assert response.status_code == 404

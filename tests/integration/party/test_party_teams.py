"""Party team management: create/update/delete/join/leave/kick.

Scope:
- Teams: create, update, delete, join, leave, and kick. Only the host can
  kick. A user can't be on two teams.

Route shapes confirmed by reading app/api/party/teams/routes.py and
app/api/party/teams/teams.py:
  * POST /create: caller must be a party member; builds a solo team led by
    the caller, named "{username}'s Team" by default; calls
    remove_from_team() first, so it silently moves the caller off any team
    they were already on.
  * POST /update: only the team's leader OR the party host may edit it.
  * POST /delete: only the team's leader OR the party host may delete it.
  * POST /join: caller must be a party member; add_to_team() calls
    remove_from_team() first - joining a second team MOVES the caller
    rather than rejecting the request, so "a user can't be on two teams" is
    enforced by relocation, not refusal.
  * POST /leave: remove_from_team(); a no-op if the caller isn't on a team
    (no error either way).
  * POST /kick: allowed for the party host OR the KICKED user's OWN team
    leader (not "host-only") - otherwise 400.
"""

import pytest

from models.db import db
from models.duels import TeamPlayer
from models.party import PartyTeam
from tests.factories import make_team, make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration


def _team_user_ids(party_team):
    return {tp.user_id for tp in TeamPlayer.query.filter_by(team_id=party_team.team_id).all()}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/party/teams?code=AAAA", None),
    ("post", "/api/party/teams/create", {"code": "AAAA"}),
    ("post", "/api/party/teams/update", {"id": "x"}),
    ("post", "/api/party/teams/delete", {"code": "AAAA", "id": "x"}),
    ("post", "/api/party/teams/leave", {"code": "AAAA"}),
    ("post", "/api/party/teams/join", {"code": "AAAA", "id": "x"}),
    ("post", "/api/party/teams/kick", {"code": "AAAA", "username": "x"}),
])
def test_team_routes_reject_anonymous_and_demo_callers_with_403(client, method, path, body):
    call = getattr(client, method)
    kwargs = {} if body is None else {"json": body}

    assert call(path, **kwargs).status_code == 403
    assert call(path, headers=demo_header(), **kwargs).status_code == 403


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def test_create_team_adds_a_new_team_to_the_party(client, party_with_members):
    party, host, members = party_with_members
    creator = members[0]

    response = client.post("/api/party/teams/create", json={"code": party.code}, headers=auth_header(creator))

    assert response.status_code == 200
    team = PartyTeam.query.filter_by(party_id=party.id, leader_id=creator.id).first()
    assert team is not None
    assert team.name == f"{creator.username}'s Team"
    assert _team_user_ids(team) == {creator.id}


def test_create_team_with_custom_name(client, party_with_members):
    party, host, members = party_with_members
    creator = members[0]

    response = client.post(
        "/api/party/teams/create",
        json={"code": party.code, "name": "Custom Name"},
        headers=auth_header(creator),
    )

    assert response.status_code == 200
    team = PartyTeam.query.filter_by(party_id=party.id, leader_id=creator.id).first()
    assert team.name == "Custom Name"


def test_create_team_without_membership_returns_200_documents_bug(client, party_with_host):
    """BUG: create_team()'s "not in party" branch returns
    `jsonify({"error":"not in party"})` with NO status code, so Flask
    defaults to 200 - a caller checking response.status_code (as every other
    error path in this codebase expects) will treat this as success."""
    party, host = party_with_host
    stranger = make_user()

    response = client.post("/api/party/teams/create", json={"code": party.code}, headers=auth_header(stranger))

    assert response.status_code == 200
    assert response.get_json() == {"error": "not in party"}
    assert PartyTeam.query.filter_by(party_id=party.id, leader_id=stranger.id).count() == 0


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

def test_update_team_changes_team_attributes(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0], name="Old Name")

    response = client.post(
        "/api/party/teams/update",
        json={"id": team.uuid, "name": "New Name", "color": 42},
        headers=auth_header(members[0]),
    )

    assert response.status_code == 200
    db.session.refresh(team)
    assert team.name == "New Name"
    assert team.color == 42


def test_update_team_allowed_for_host_even_if_not_leader(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0])

    response = client.post(
        "/api/party/teams/update",
        json={"id": team.uuid, "name": "Host Renamed"},
        headers=auth_header(host),
    )

    assert response.status_code == 200


def test_update_team_rejected_for_non_leader_non_host(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0])

    response = client.post(
        "/api/party/teams/update",
        json={"id": team.uuid, "name": "Nope"},
        headers=auth_header(members[1]),
    )

    assert response.status_code == 403


def test_update_unknown_team_returns_404(client, party_with_host):
    party, host = party_with_host

    response = client.post(
        "/api/party/teams/update",
        json={"id": "not-a-real-uuid", "name": "Nope"},
        headers=auth_header(host),
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_team_removes_the_team(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0])
    team_uuid = team.uuid

    response = client.post(
        "/api/party/teams/delete",
        json={"code": party.code, "id": team_uuid},
        headers=auth_header(members[0]),
    )

    assert response.status_code == 200
    assert PartyTeam.query.filter_by(uuid=team_uuid).count() == 0


def test_delete_team_rejected_for_non_leader_non_host(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0])

    response = client.post(
        "/api/party/teams/delete",
        json={"code": party.code, "id": team.uuid},
        headers=auth_header(members[1]),
    )

    assert response.status_code == 403
    assert PartyTeam.query.filter_by(uuid=team.uuid).count() == 1


# ---------------------------------------------------------------------------
# join / leave
# ---------------------------------------------------------------------------

def test_join_team_adds_the_user_to_that_team(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0]], leader=members[0])
    joiner = members[1]

    response = client.post(
        "/api/party/teams/join",
        json={"code": party.code, "id": team.uuid},
        headers=auth_header(joiner),
    )

    assert response.status_code == 200
    db.session.refresh(team)
    assert joiner.id in _team_user_ids(team)


def test_join_team_requires_membership(client, party_with_host):
    party, host = party_with_host
    team = make_team(party, users=[host], leader=host)
    stranger = make_user()

    response = client.post(
        "/api/party/teams/join",
        json={"code": party.code, "id": team.uuid},
        headers=auth_header(stranger),
    )

    assert response.status_code == 400


def test_join_unknown_team_returns_404(client, party_with_host):
    party, host = party_with_host

    response = client.post(
        "/api/party/teams/join",
        json={"code": party.code, "id": "not-a-real-uuid"},
        headers=auth_header(host),
    )

    assert response.status_code == 404


def test_joining_a_second_team_moves_the_user(client, party_with_members):
    """Documents how "a user can't be on two teams" is actually enforced:
    add_to_team() unconditionally calls remove_from_team() first, so joining
    team B while on team A just relocates the user - there is no rejection
    and no way to end up on two teams at once. Since `mover` was team A's
    only member, remove_from_team() deletes the now-empty PartyTeam row
    entirely rather than leaving an empty team behind."""
    party, host, members = party_with_members
    mover = members[0]
    team_a = make_team(party, users=[mover], leader=mover, name="A")
    team_a_uuid = team_a.uuid
    team_b = make_team(party, users=[members[1]], leader=members[1], name="B")

    response = client.post(
        "/api/party/teams/join",
        json={"code": party.code, "id": team_b.uuid},
        headers=auth_header(mover),
    )

    assert response.status_code == 200
    assert PartyTeam.query.filter_by(uuid=team_a_uuid).count() == 0
    db.session.refresh(team_b)
    assert mover.id in _team_user_ids(team_b)


def test_leave_team_removes_the_user_from_their_team(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[host, members[0]], leader=host)

    response = client.post(
        "/api/party/teams/leave",
        json={"code": party.code},
        headers=auth_header(members[0]),
    )

    assert response.status_code == 200
    db.session.refresh(team)
    assert members[0].id not in _team_user_ids(team)


def test_leave_team_when_not_on_any_team_is_a_noop(client, party_with_host):
    party, host = party_with_host

    response = client.post("/api/party/teams/leave", json={"code": party.code}, headers=auth_header(host))

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# kick
# ---------------------------------------------------------------------------

def test_kick_rejected_for_non_host_non_leader(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0], members[1]], leader=members[0])
    bystander = members[2]

    response = client.post(
        "/api/party/teams/kick",
        json={"code": party.code, "username": members[1].username},
        headers=auth_header(bystander),
    )

    assert response.status_code == 400
    db.session.refresh(team)
    assert members[1].id in _team_user_ids(team)


def test_host_can_kick_any_team_member(client, party_with_members):
    party, host, members = party_with_members
    team = make_team(party, users=[members[0], members[1]], leader=members[0])

    response = client.post(
        "/api/party/teams/kick",
        json={"code": party.code, "username": members[1].username},
        headers=auth_header(host),
    )

    assert response.status_code == 200
    db.session.refresh(team)
    assert members[1].id not in _team_user_ids(team)


def test_team_leader_can_also_kick_their_own_teammate(client, party_with_members):
    """Documents that kicking is NOT host-exclusive: a team's own leader can
    kick a teammate off that same team too (see the `kick_player > 0` branch
    of api/party/teams/routes.py:kick_player)."""
    party, host, members = party_with_members
    leader = members[0]
    team = make_team(party, users=[leader, members[1]], leader=leader)

    response = client.post(
        "/api/party/teams/kick",
        json={"code": party.code, "username": members[1].username},
        headers=auth_header(leader),
    )

    assert response.status_code == 200
    db.session.refresh(team)
    assert members[1].id not in _team_user_ids(team)


def test_kick_unknown_username_returns_404(client, party_with_host):
    party, host = party_with_host

    response = client.post(
        "/api/party/teams/kick",
        json={"code": party.code, "username": "nobody-at-all"},
        headers=auth_header(host),
    )

    assert response.status_code == 404

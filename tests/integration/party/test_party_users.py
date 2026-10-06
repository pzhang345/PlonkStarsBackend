"""Party user listing and removal.

Scope:
- Users: listing works and remove is host-only.

Route shapes confirmed by reading app/api/party/users/routes.py and
app/api/party/users/users.py:
  * GET  ""      -> {"members":[{...user, "in_lobby":bool}], "host":username,
                     "this":caller_username}
  * POST /remove -> host-only (403 otherwise); 404 for an unknown username;
                     delegates to remove_user_from_party(), which raises
                     "Cannot remove the host" (-> 400) if the target is the
                     host - including when the host tries to "remove"
                     themself.
"""

import pytest

from models.party import PartyMember
from tests.factories import make_user
from tests.helpers import auth_header, demo_header

pytestmark = pytest.mark.integration


def test_list_users_returns_every_party_member(client, party_with_members):
    party, host, members = party_with_members

    response = client.get(f"/api/party/users?code={party.code}", headers=auth_header(host))

    assert response.status_code == 200
    body = response.get_json()
    assert body["host"] == host.username
    assert body["this"] == host.username
    usernames = {m["username"] for m in body["members"]}
    assert usernames == {host.username, *(m.username for m in members)}
    assert all("in_lobby" in m for m in body["members"])


def test_list_users_requires_auth(client, party_with_host):
    party, host = party_with_host

    anon_response = client.get(f"/api/party/users?code={party.code}")
    demo_response = client.get(f"/api/party/users?code={party.code}", headers=demo_header())

    assert anon_response.status_code == 403
    assert demo_response.status_code == 403


def test_list_users_unknown_code_returns_404(client):
    user = make_user()

    response = client.get("/api/party/users?code=ZZZZ", headers=auth_header(user))

    assert response.status_code == 404


def test_only_host_can_remove_a_user(client, party_with_members):
    party, host, members = party_with_members
    caller, target = members[0], members[1]

    response = client.post(
        "/api/party/users/remove",
        json={"code": party.code, "username": target.username},
        headers=auth_header(caller),
    )

    assert response.status_code == 403
    assert PartyMember.query.filter_by(party_id=party.id, user_id=target.id).count() == 1


def test_host_removes_a_member(client, party_with_members):
    party, host, members = party_with_members
    target = members[0]

    response = client.post(
        "/api/party/users/remove",
        json={"code": party.code, "username": target.username},
        headers=auth_header(host),
    )

    assert response.status_code == 200
    assert PartyMember.query.filter_by(party_id=party.id, user_id=target.id).count() == 0


def test_remove_unknown_username_returns_404(client, party_with_host):
    party, host = party_with_host

    response = client.post(
        "/api/party/users/remove",
        json={"code": party.code, "username": "nobody-at-all"},
        headers=auth_header(host),
    )

    assert response.status_code == 404


def test_host_removing_self_is_rejected_documents_bug(client, party_with_host):
    """The host is themself the only PartyMember here, so this exercises
    remove_user_from_party()'s "Cannot remove the host" guard: even the host
    can't remove themself this way (400, no membership change). Documents
    that /users/remove is not usable as a "leave" substitute for the host,
    consistent with /party/leave's own host restriction
    (test_party_routes.py::test_host_leaving_the_party_is_rejected_documents_bug)."""
    party, host = party_with_host

    response = client.post(
        "/api/party/users/remove",
        json={"code": party.code, "username": host.username},
        headers=auth_header(host),
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Cannot remove the host"}
    assert PartyMember.query.filter_by(party_id=party.id, user_id=host.id).count() == 1

"""Socket.IO /socket/party namespace.

Scope (TESTING_PLAN.md section 3 Phase 3):
- Socket /socket/party: connect with and without auth, and join places the
  client in a room. With two socketio_client() instances, the second
  receives broadcasts when a user joins, leaves, or rules change.

Broadcasts for "user joins"/"user leaves"/"rules change" are not emitted by
the socket handlers themselves (app/api/party/socket.py only handles
`connect`/`join`) - they are emitted by the HTTP routes that make those
changes (see app/api/party/routes.py:join_party, app/api/party/users/users.py
:remove_user_from_party, app/api/party/rules/routes.py:set_rules, all of
which call `socketio.emit(..., room=party.code)`). So each of those tests
joins two socketio_client()s to the party's room, performs the state change
through the HTTP `client`, and asserts the *second* socket client (an
observer who didn't initiate the change) receives the broadcast.
"""

import pytest

from api.account.auth import generate_token
from tests.factories import make_party, make_party_member, make_user
from tests.helpers import auth_header

pytestmark = pytest.mark.integration


def _connect(socketio_client, user):
    """Connect a socketio_client to /socket/party as `user` and drain the
    initial "connected" message so later get_received() calls only see
    events from the action under test."""
    token = generate_token(user)
    sio = socketio_client(namespace="/socket/party", auth={"token": token})
    sio.get_received("/socket/party")
    return sio, token


def _join_room(sio, code, token):
    sio.emit("join", {"code": code, "token": token}, namespace="/socket/party")
    return sio.get_received("/socket/party")


def test_connect_with_auth_succeeds(socketio_client):
    user = make_user()
    sio, _ = _connect(socketio_client, user)
    assert sio.is_connected("/socket/party")


def test_connect_with_invalid_token_is_rejected(socketio_client):
    """A *present* but invalid token is rejected cleanly: get_user_from_token
    returns None, so handle_connect calls disconnect() and returns False."""
    sio = socketio_client(namespace="/socket/party", auth={"token": "garbage"})
    assert sio.is_connected("/socket/party") is False


def test_connect_without_auth_documents_bug(socketio_client):
    """Connecting with no auth payload at all crashes instead of being
    rejected cleanly.

    BUG: handle_connect(data) in app/api/party/socket.py does
    `data.get("token")` with no None-check. python-socketio calls the
    connect handler with `data=None` whenever the client passes no (or an
    empty) `auth` dict - it does NOT skip the call. That raises an unhandled
    AttributeError ('NoneType' object has no attribute 'get') instead of the
    intended disconnect()/return False rejection that a *present-but-wrong*
    token gets (see test_connect_with_invalid_token_is_rejected). The
    exception propagates all the way out of the connect call - there is no
    way to observe a clean rejection here, so this test pins the crash
    itself as the current (buggy) behavior.
    """
    with pytest.raises(AttributeError):
        socketio_client(namespace="/socket/party")


def test_join_places_the_client_in_the_party_room(socketio_client, db_session):
    from fsocket import socketio as sio_server

    host = make_user()
    party = make_party(host=host)
    sio, token = _connect(socketio_client, host)

    received = _join_room(sio, party.code, token)
    assert any(
        event["name"] == "message" and event["args"] == {"message": "joined party"}
        for event in received
    )

    # Confirm room membership directly against the Socket.IO server's room
    # manager - the most reliable observable signal that `join` actually put
    # this client's sid in the party's room.
    real_sid = sio_server.server.manager.sid_from_eio_sid(sio.eio_sid, "/socket/party")
    participant_sids = [
        sid for sid, _eio_sid in sio_server.server.manager.get_participants("/socket/party", party.code)
    ]
    assert real_sid in participant_sids


def test_second_client_receives_broadcast_when_a_user_joins(socketio_client, client, db_session):
    host = make_user()
    party = make_party(host=host)

    sio_1, token_1 = _connect(socketio_client, host)
    _join_room(sio_1, party.code, token_1)

    bystander = make_user()
    make_party_member(party, bystander)
    sio_2, token_2 = _connect(socketio_client, bystander)
    _join_room(sio_2, party.code, token_2)

    joiner = make_user()
    resp = client.post("/api/party/join", json={"code": party.code}, headers=auth_header(joiner))
    assert resp.status_code == 200

    received = sio_2.get_received("/socket/party")
    assert any(
        event["name"] == "add_user" and event["args"][0]["username"] == joiner.username
        for event in received
    )


def test_second_client_receives_broadcast_when_a_user_leaves(socketio_client, client, db_session):
    host = make_user()
    party = make_party(host=host)
    leaver = make_user()
    make_party_member(party, leaver)

    sio_1, token_1 = _connect(socketio_client, host)
    _join_room(sio_1, party.code, token_1)

    bystander = make_user()
    make_party_member(party, bystander)
    sio_2, token_2 = _connect(socketio_client, bystander)
    _join_room(sio_2, party.code, token_2)

    resp = client.post("/api/party/leave", json={"code": party.code}, headers=auth_header(leaver))
    assert resp.status_code == 200

    received = sio_2.get_received("/socket/party")
    assert any(
        event["name"] == "remove_user" and event["args"][0]["username"] == leaver.username
        for event in received
    )


def test_second_client_receives_broadcast_when_rules_change(socketio_client, client, db_session, game_configs):
    host = make_user()
    party = make_party(host=host)

    sio_1, token_1 = _connect(socketio_client, host)
    _join_room(sio_1, party.code, token_1)

    bystander = make_user()
    make_party_member(party, bystander)
    sio_2, token_2 = _connect(socketio_client, bystander)
    _join_room(sio_2, party.code, token_2)

    # "type" must be passed explicitly here: when it's omitted, set_rules
    # (app/api/party/rules/routes.py:40) evaluates `base_rules.type`, but
    # BaseRules has no `type` column - that's a separate bug outside this
    # file's scope (party rules routes, not the socket), so it's sidestepped
    # here by always sending the party's current type.
    resp = client.post(
        "/api/party/rules",
        json={"code": party.code, "type": "duels", "hp": 4000},
        headers=auth_header(host),
    )
    assert resp.status_code == 200

    received = sio_2.get_received("/socket/party")
    assert any(
        event["name"] == "update_rules" and event["args"][0]["hp"] == 4000
        for event in received
    )

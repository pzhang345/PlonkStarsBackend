"""Socket.IO /socket/map/edit namespace.

Scope:
- Socket /socket/map/edit: an editor can join the room and a non-editor
  can't.

app/api/map/edit/socket.py:handle_join_room checks api.map.edit.mapedit
.can_edit(user, map) (nonzero for the map's creator, an admin, or a row in
MapEditor) before calling join_room(). A user who fails that check gets an
"error" event and is never added to the room. tests/integration/map/conftest.py
is deliberately empty (owned by another agent, not yet implemented), so this
file builds its own map/editor rows directly via tests.factories +
models.map.MapEditor rather than relying on a shared fixture.
"""

import pytest

from api.account.auth import generate_token
from models.db import db
from models.map import MapEditor
from tests.factories import make_map, make_user

pytestmark = pytest.mark.integration


def _connect(socketio_client, user):
    token = generate_token(user)
    sio = socketio_client(namespace="/socket/map/edit", auth={"token": token})
    sio.get_received("/socket/map/edit")  # drain the initial "connected" message
    return sio, token


def test_editor_can_join_the_map_edit_room(socketio_client, db_session):
    from fsocket import socketio as sio_server

    creator = make_user()
    game_map = make_map(creator=creator)
    editor = make_user()
    db.session.add(MapEditor(user_id=editor.id, map_id=game_map.id, permission_level=1))
    db.session.commit()

    sio, token = _connect(socketio_client, editor)
    sio.emit("join", {"id": game_map.uuid, "token": token}, namespace="/socket/map/edit")

    received = sio.get_received("/socket/map/edit")
    assert not any(event["name"] == "error" for event in received)

    real_sid = sio_server.server.manager.sid_from_eio_sid(sio.eio_sid, "/socket/map/edit")
    participant_sids = [
        sid for sid, _eio_sid in sio_server.server.manager.get_participants("/socket/map/edit", game_map.uuid)
    ]
    assert real_sid in participant_sids


def test_non_editor_cannot_join_the_map_edit_room(socketio_client, db_session):
    from fsocket import socketio as sio_server

    creator = make_user()
    game_map = make_map(creator=creator)
    stranger = make_user()

    sio, token = _connect(socketio_client, stranger)
    sio.emit("join", {"id": game_map.uuid, "token": token}, namespace="/socket/map/edit")

    received = sio.get_received("/socket/map/edit")
    assert any(
        event["name"] == "error" and event["args"][0] == {"error": "Don't have access to the map"}
        for event in received
    )

    participants = list(sio_server.server.manager.get_participants("/socket/map/edit", game_map.uuid))
    assert participants == []

from fsocket import socketio
from flask_socketio import disconnect, emit, join_room

from api.auth.auth import get_user_from_token
from api.map.edit.mapedit import can_edit
from models.map import GameMap


@socketio.on("connect",namespace="/socket/map/edit")
def handle_connect(auth):
    user = get_user_from_token(auth.get("token"))
    if not user:
        disconnect()
        return False
    
    emit("message",{"message":"connected"})
    return True

@socketio.on("join",namespace="/socket/map/edit")
def handle_join_room(data):
    room = data.get('id')
    user = get_user_from_token(data.get("token"))
    map = GameMap.query.filter_by(uuid=room).first_or_404("Cannot find map")
    
    if not can_edit(user,map):
        emit("error",{"error":"Don't have access to the map"})
        return
    join_room(room)
    
@socketio.on("disconnect",namespace="/socket/map/edit")
def handle_disconnect():
    print("Client disconnected")

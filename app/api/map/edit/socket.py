from api.auth.auth import login_required
from fsocket import socketio
from flask_socketio import emit, join_room, leave_room, close_room

@socketio.on("connect", namespace="/map/edit")
@login_required(socket=True)
def connect(user):
    emit("message", {"message": "connected"})
    

@socketio.on("join", namespace="/map/edit")
def join_map(data):
    room = data['id']
    join_room(room)
    
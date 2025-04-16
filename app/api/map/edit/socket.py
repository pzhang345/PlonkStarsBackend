from fsocket import socketio
from flask_socketio import emit, join_room


@socketio.on("connect",namespace="/socket/map/edit")
def handle_connect():
    emit("message",{"message":"connected"})
    return True

@socketio.on("join",namespace="/socket/map/edit")
def handle_join_room(data):
    room = data.get('id')
    join_room(room)
    
@socketio.on("disconnect",namespace="/socket/map/edit")
def handle_disconnect():
    print("Client disconnected")

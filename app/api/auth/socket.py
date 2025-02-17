from flask_socketio import SocketIO, join_room, leave_room
from api.auth.auth import login_required

socketio = SocketIO()

@socketio.on('connect')
@login_required
def handle_connect(user):
    join_room(user.id)
    socketio.emit('response', {'data': 'Welcome to the server!'})
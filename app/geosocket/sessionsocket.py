from geosocket.socket import socketio
from api.auth.auth import login_required
from flask_socketio import join_room

@socketio.on('connect')
@login_required
def handle_connect(user): 
    join_room()
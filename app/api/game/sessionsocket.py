from gsocket import socketio
from flask_socketio import emit,join_room

from models import Session
from api.auth.auth import login_required
from api.game.gametype import game_type

@socketio.on("connect",namespace="/session")
@login_required
def connect(user):
    emit("message",{"message":"connected"})
    
@socketio.on("join",namespace="/session")
@login_required
def join(user,data):
    id = data.get("id")
    if not id or Session.query.filter_by(uuid=id).count() == 0:
        emit("error",{"error":"could not find Session"})
        return
    session = Session.query.filter_by(uuid=id).first()
    if(game_type[session.type].socket_join(data,user,session)):
        join_room(id)
        emit("message",{"message":"joined room"})
    else:
        emit("error",{"error":"join not permitted"})
    
def close_room(room):
    socketio.emit("message",{"message":"room closing"},room=room)
    socketio.close_room(room,namespace="/session")
    
        
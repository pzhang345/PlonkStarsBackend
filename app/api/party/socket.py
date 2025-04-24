from flask import request
from flask_socketio import disconnect, emit, join_room
from api.account.auth import get_user_from_token

from models.db import db
from models.party import Party, PartyMember

def register_party_socket(socketio,namespace):
    @socketio.on("connect",namespace=namespace)
    def handle_connect(data):
        user = get_user_from_token(data.get("token"))
        if not user:
            disconnect()
            return False
        
        emit("message",{"message":"connected"})
        return True

    @socketio.on("join",namespace=namespace)
    def handle_join_room(data):
        room = data.get('code')
        user = get_user_from_token(data.get("token"))
        party = Party.query.filter_by(code=room).first_or_404("Cannot find map")
        
        member = PartyMember.query.filter_by(party_id=party.id,user_id=user.id).first()
        if member:
            member.sid = request.sid
            db.session.commit()
        else:
            member = PartyMember(user_id=user.id,party_id=party.id,sid=request.sid)
            db.session.add(member)
            db.session.commit()
            emit("new_user",{"user":user.to_json()},namespace=namespace,room=room)
        join_room(room)
        
        emit("joined",{"message":"joined party"})
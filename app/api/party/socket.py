from datetime import datetime
from flask_socketio import disconnect, emit, join_room
import pytz
from api.account.auth import get_user_from_token

from api.game.gametype import game_type
from models.db import db
from models.party import Party, PartyMember
from models.session import Session

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
        session = data.get('id')
        user = get_user_from_token(data.get("token"))
        party = Party.query.filter_by(code=room).first_or_404("Cannot find party")
        party.last_activity = datetime.now(tz=pytz.utc)
        db.session.commit()
        
        member = PartyMember.query.filter_by(party_id=party.id,user_id=user.id).first()
        if not member:
            emit("error",{"error":"join through the RESTAPI first"})
            return
        socketio.emit("leave",{"reason":"joined new party"},namespace=namespace,room=f"{user.id}_{room}")
        join_room(f"{user.id}_{room}")
        join_room(room)
        if session:
            session = Session.query.filter_by(uuid=session).first_or_404("Cannot find session")
            game_type[session.type].join_socket(session,user)
        
        emit("message",{"message":"joined party"})
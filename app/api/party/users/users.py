from api.party.teams.teams import remove_from_team
from fsocket import socketio
from models.db import db
from models.party import PartyMember
from models.user import User


def remove_user_from_party(party,user, reason="Removed from party"):
    if user.id == party.host_id:
        raise Exception("Cannot remove the host")
    
    member = PartyMember.query.filter_by(party_id=party.id, user_id=user.id).first()
    if not member:
        raise Exception("User is not in the party")
    
    remove_from_team(party,user)
    
    db.session.delete(member)
    db.session.commit()
    
    socketio.emit("leave",{"reason":reason},namespace="/socket/party", room=f"{member.user_id}_{party.code}")
    socketio.emit("remove_user", {"username": member.user.username}, namespace="/socket/party", room=party.code)
    
    
    
    
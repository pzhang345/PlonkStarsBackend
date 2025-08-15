from sqlalchemy import exists, not_

from fsocket import socketio
from models.db import db
from models.duels import GameTeam, GameTeamLinker, TeamPlayer
from models.party import PartyTeam
from models.user import User


def get_team(ids):
    hash = ",".join([str(i) for i in sorted(ids)])
    
    if GameTeam.query.filter_by(hash=hash).count() > 0:
        return GameTeam.query.filter_by(hash=hash).first()
    
    team = GameTeam(hash=hash)
    db.session.add(team)
    db.session.flush()
    
    for id in ids:
        team_player = TeamPlayer(user_id=id, team_id=team.id)
        db.session.add(team_player)
    
    db.session.commit()
    return team

def set_team_settings(team, data, socket_emit=True):
    team.name = data.get("name", team.name)
    team.color = data.get("color", team.color)
    db.session.commit()
    if socket_emit:
        socketio.emit("update_team", {"id":team.uuid,**{k: data[k] for k in ["color", "name"] if k in data}}, namespace="/socket/party", room=team.party.code)
    
    
def add_to_team(party ,user, party_team):
    remove_from_team(party,user)
    team_hash = party_team.team.hash
    ids = [int(i) for i in team_hash.split(",")] + [user.id]
    team = get_team(ids)
    party_team.team_id = team.id
    delete_orphaned_teams()
    db.session.commit()
    socketio.emit("add_team_user", {"id":party_team.uuid, "username": user.username}, namespace="/socket/party", room=party.code)
    
    
def remove_from_team(party,user):
    team = PartyTeam.query.filter_by(party_id=party.id).join(GameTeam).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first()
    if team:
        ids = [int(i) for i in team.team.hash.split(",") if int(i) != user.id]
        if ids == []:
            db.session.delete(team)
            socketio.emit("delete_team", {"id":team.uuid}, namespace="/socket/party", room=party.code)
        else:
            new_team = get_team(ids)
            team.team_id = new_team.id
            socketio.emit("remove_team_user", {"id": team.uuid,"username":user.username},namespace="/socket/party",room=party.code)
            if team.leader_id == user.id:
                team.leader_id = ids[0] if ids[0] != user.id else ids[1]
                team_leader = User.query.filter_by(id=team.leader_id).first()
                socketio.emit("update_team", {"id": team.uuid,"leader":team_leader.username},namespace="/socket/party",room=party.code)
        
        delete_orphaned_teams()
        db.session.commit()

def delete_orphaned_teams():
    orphaned_teams = (
        GameTeam.query
        .filter(
            not_(exists().where(GameTeamLinker.team_id == GameTeam.id)),
            not_(exists().where(PartyTeam.team_id == GameTeam.id))
        )
    )
    
    orphaned_teams.delete(synchronize_session=False)
    db.session.commit()
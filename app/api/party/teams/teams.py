from sqlalchemy import exists, not_

from fsocket import socketio
from models.db import db
from models.duels import GameTeam, GameTeamLinker, TeamPlayer
from models.party import PartyMember, PartyTeam
from models.user import User


def get_team(ids):
    hash = ",".join([str(i) for i in sorted([ids])])
    
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

def add_to_team(party ,user, party_team):
    remove_from_team(party,user)
    team_hash = party_team.team.hash
    ids = [int(i) for i in team_hash.split(",")] + [user.id]
    team = get_team(ids)
    party_team.team_id = team.id
    delete_orphaned_teams()
    db.session.commit()
    
    
def remove_from_team(party,user):
    team = PartyTeam.query.filter_by(party_id=party.id).join(GameTeam).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first()
    if team:
        ids = [int(i) for i in team.team.hash.split(",") if int(i) != user.id]
        if ids == []:
            db.session.remove(team)
            socketio.emit("delete_team", {"id":team.uuid}, namespace="/socket/party", room=party.code)
        else:
            new_team = get_team(ids)
            team.team_id = new_team.id
            socketio.emit("remove_team_user", {"id": team.uuid,"user":user.username},namespace="/socket/party",room=party.code)
            if team.leader_id == user.id:
                team.leader_id == new_team[0]
                team_leader = User.query.filter_by(id=new_team[0]).first()
                socketio.emit("team_leader", {"id": team.uuid,"leader":team_leader.username},namespace="/socket/party",room=party.code)
        
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
    

def teams_to_json(party):
    party_teams = {"teams": []}
    teams = party.teams
    for team in teams:
        party_teams["teams"] += [
            team.to_json() for team in teams
        ]
    
    spectators = (PartyMember.query
        .outerjoin(TeamPlayer, TeamPlayer.user_id == PartyMember.user_id)
        .filter(
            PartyMember.party_id == party.id,
            TeamPlayer.user_id == None
        )
    )
    party_teams["spectators"] = [member.user.username for member in spectators]
    return party_teams
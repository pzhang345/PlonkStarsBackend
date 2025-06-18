from sqlalchemy import exists, not_
from models.db import db
from models.duels import GameTeam, GameTeamLinker, TeamPlayer
from models.party import PartyMember, PartyTeams


def get_team(users):
    hash = ",".join(sorted([user.id for user in users]))
    
    if GameTeam.query.filter_by(hash=hash).count() > 0:
        return GameTeam.query.filter_by(hash=hash).first()
    
    team = GameTeam(hash=hash)
    db.session.add(team)
    db.session.flush()
    
    for user in users:
        team_player = TeamPlayer(user_id=user.id, team_id=team.id)
        db.session.add(team_player)
    
    db.session.commit()
    return team

def delete_orphaned_teams():
    orphaned_teams = (
        GameTeam.query
        .filter(
            not_(exists().where(GameTeamLinker.team_id == GameTeam.id)),
            not_(exists().where(PartyTeams.team_id == GameTeam.id))
        )
    )
    
    orphaned_teams.delete(synchronize_session=False)
    db.session.commit()
    

def teams_to_json(party):
    party_teams = {"teams": []}
    teams = party.teams
    for team in teams:
        party_teams["teams"] += [
            {
                "team_leader": team.leader.username,
                "color": team.color,
                "members": [member.user.username for member in TeamPlayer.query.filter_by(team_id=team.team_id).all()]
            } for team in teams
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
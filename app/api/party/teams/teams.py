from sqlalchemy import exists, not_
from models.db import db
from models.duels import GameTeam, GameTeamLinker, TeamPlayer
from models.party import PartyTeams


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
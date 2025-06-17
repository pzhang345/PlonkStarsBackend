from flask import jsonify
from api.game.gametype import game_type
from models.db import db
from models.duels import GameTeam, TeamPlayer
from models.party import PartyMember,PartyTeams


def get_users(party):
    return [member.user.to_json() for member in party.members]
        
def get_teams(party):
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
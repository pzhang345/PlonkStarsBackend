from flask import jsonify
from api.game.gametype import game_type
from models.db import db
from models.duels import GameTeam, TeamPlayer
from models.party import PartyMember,PartyTeams


def get_users(party):
    return [member.user.to_json() for member in party.members]
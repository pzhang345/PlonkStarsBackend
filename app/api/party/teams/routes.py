from flask import Blueprint, jsonify, request

from api.account.auth import login_required
from api.party.teams.teams import teams_to_json
from models.party import Party
party_teams_bp =  Blueprint("party_teams_bp", __name__, url_prefix="/party/teams")

@party_teams_bp.route("", methods=["GET"])
@login_required
def get_teams_route(user):
    data = request.args
    code = data.get("code")

    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    teams = teams_to_json(party)
    return jsonify(teams), 200
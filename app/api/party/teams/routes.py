from flask import Blueprint, jsonify, request

from api.account.auth import login_required
from api.party.teams.teams import add_to_team, remove_from_team, teams_to_json
from fsocket import socketio
from models.duels import GameTeam, TeamPlayer
from models.party import Party, PartyMember, PartyTeam
from models.user import User

party_teams_bp =  Blueprint("party_teams_bp", __name__, url_prefix="/party/teams")

@party_teams_bp.route("", methods=["GET"])
@login_required
def get_teams(user):
    data = request.args
    code = data.get("code")

    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    teams = teams_to_json(party)
    return jsonify(teams), 200

@party_teams_bp.route("/create", methods=["POST"])
@login_required
def create_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if PartyMember.query.filter_by(user_id=user.id, party_id=party.id).count() == 0:
        return jsonify({"error":"not in party"})
    
    
    team = get_teams([user.id])
    party_team = PartyTeam(team_id=team.id,party_id=party.id,leader_id=user.id)
    socketio.emit("new_team", party_team.to_json() ,namespace="/socket/party",room=code)
    return jsonify({"message":"team created"}),200

@party_teams_bp.route("/leave",method=["POST"])
@login_required
def leave_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    remove_from_team(party,user)

    return jsonify({"message":"team left"}),200

@party_teams_bp.route("/join", method=["POST"])
@login_required
def join_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if PartyMember.query.filter_by(user_id=user.id, party_id=party.id).count() == 0:
        return jsonify({"error":"not in party"})
    
    team_uuid = data.get("id")
    party_team = PartyTeam.query.filter_by(uuid=team_uuid).first_or_404("Cannot find team")
    
    add_to_team(party,user,party_team)
    
    return({"message":"team joined"}),200

@party_teams_bp.route("/kick", method=["POST"])
@login_required
def kick_player(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")    
    kick_user = User.query.filter_by(username=data.get("username"))
    kick_player = (
        TeamPlayer.query
        .filter_by(user_id=kick_user.id)
        .join(GameTeam)
        .join(PartyTeam)
        .filter(PartyTeam.leader_id==user.id, PartyTeam.party_id==party.id)
    ).count()
    
    if kick_player > 0:
        remove_from_team(party,kick_user)
        return jsonify({"message":"user kicked"}),200
    else:
        return jsonify({"error":"user not in your team"}),400
     
    


    
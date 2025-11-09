from flask import Blueprint, jsonify, request

from api.account.auth import login_required
from api.party.teams.teams import delete_orphaned_teams, get_team, add_to_team, remove_from_team, set_team_settings
from fsocket import socketio
from models.db import db
from models.duels import GameTeam, TeamPlayer
from models.party import Party, PartyMember, PartyTeam
from models.user import User
from utils import return_400_on_error

party_teams_bp =  Blueprint("party_teams_bp", __name__)

@party_teams_bp.route("", methods=["GET"])
@login_required()
def get_teams(user):
    data = request.args
    code = data.get("code")

    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    return jsonify([team.to_json() for team in party.teams]), 200

@party_teams_bp.route("/create", methods=["POST"])
@login_required()
def create_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if PartyMember.query.filter_by(user_id=user.id, party_id=party.id).count() == 0:
        return jsonify({"error":"not in party"})
    
    remove_from_team(party, user)
    team = get_team([user.id])
    party_team = PartyTeam(team_id=team.id,party_id=party.id,leader_id=user.id)
    db.session.add(party_team)
    db.session.commit()
    
    if not data.get("name"):
        data["name"] = f"{user.username}'s Team"
    
    set_team_settings(party_team, data,socket_emit=False)
    socketio.emit("add_team", party_team.to_json() ,namespace="/socket/party",room=code)
    return jsonify({"message":"team created"}),200

@party_teams_bp.route("/update", methods=["POST"])
@login_required()
def edit_team(user):
    data = request.get_json()
    team = PartyTeam.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find team")
    if team.leader_id != user.id and team.party.host_id != user.id:
        return jsonify({"error":"You cannot edit the team"}), 403
    
    set_team_settings(team, data)
    
    return jsonify({"message":"team updated"}), 200
    

@party_teams_bp.route("/delete", methods=["POST"])
@login_required()
def delete_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    team_uuid = data.get("id")
    party_team = PartyTeam.query.filter_by(uuid=team_uuid).first_or_404("Cannot find team")
    
    if party_team.leader_id != user.id and party.host_id != user.id:
        return jsonify({"error":"You cannot delete the team"}), 403
    
    db.session.delete(party_team)
    delete_orphaned_teams()
    db.session.commit()
    
    socketio.emit("delete_team", {"id":party_team.uuid}, namespace="/socket/party", room=party.code)
    
    return jsonify({"message":"team deleted"}),200

@party_teams_bp.route("/leave",methods=["POST"])
@login_required()
def leave_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    remove_from_team(party,user)

    return jsonify({"message":"team left"}),200

@party_teams_bp.route("/join", methods=["POST"])
@login_required()
def join_team(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if PartyMember.query.filter_by(user_id=user.id, party_id=party.id).count() == 0:
        return jsonify({"error":"not in party"}), 400
    
    team_uuid = data.get("id")
    party_team = PartyTeam.query.filter_by(uuid=team_uuid).first_or_404("Cannot find team")
    
    return return_400_on_error(add_to_team,party,user,party_team)


@party_teams_bp.route("/kick", methods=["POST"])
@login_required()
def kick_player(user):
    data = request.get_json()
    code = data.get("code")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")    
    kick_user = User.query.filter_by(username=data.get("username")).first_or_404("Cannot find user")
    kick_player = (
        TeamPlayer.query
        .filter_by(user_id=kick_user.id)
        .join(GameTeam)
        .join(PartyTeam)
        .filter(PartyTeam.leader_id==user.id, PartyTeam.party_id==party.id)
    ).count()
    
    if kick_player > 0 or party.host_id == user.id:
        remove_from_team(party,kick_user)
        return jsonify({"message":"user kicked"}),200
    else:
        return jsonify({"error":"user not in your team"}),400
     
    


    
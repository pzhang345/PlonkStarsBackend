from flask import Blueprint, jsonify, request

from api.account.auth import login_required
from api.party.users.users import remove_user_from_party
from models.party import Party
from models.user import User
from utils import return_400_on_error


party_users_bp =  Blueprint("party_users_bp", __name__)

@party_users_bp.route("", methods=["GET"])
@login_required()
def get_users_(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if not party:
        return jsonify({"error": "No session yet"}), 404
    
    members = [{**member.user.to_json(), "in_lobby": member.in_lobby} for member in party.members]
    
    return jsonify({"members": members,"host":party.host.username,"this":user.username}), 200

@party_users_bp.route("/remove", methods=["POST"])
@login_required()
def remove_user(user):
    data = request.get_json()
    code = data.get("code")
    username = data.get("username")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    remove_user = User.query.filter_by(username=username).first_or_404("Cannot find user")
    return return_400_on_error(remove_user_from_party, party, remove_user, reason="Kicked from party")
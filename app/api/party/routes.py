from flask import Blueprint, request, jsonify

from api.account.auth import login_required
from api.game.gametype import str_to_type_socket,game_type
from models.db import db
from models.party import Party, PartyMember
from models.user import User
from utils import return_400_on_error

from fsocket import socketio

party_bp = Blueprint("party_bp", __name__)

@party_bp.route("/create", methods=["POST"])
@login_required
def create_party(user):
    party = Party(host_id=user.id)
    db.session.add(party)
    db.session.flush()
    member = PartyMember(user_id=user.id, party_id=party.id)
    db.session.add(member)
    db.session.commit()
    
    return jsonify({"code": party.code}), 200

@party_bp.route("/start", methods=["POST"])
@login_required
def start_party(user):
    data = request.get_json()
    code = data.get("code")
    
    if not code:
        return jsonify({"error": "provided: code"}), 400
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    type = str_to_type_socket.get((data.get("type") if data.get("type") else "live").lower())
    if not type:
        return jsonify({"error": "provided a correct type"}), 400
    
    ret = return_400_on_error(game_type[type].create, data, user)
    if ret[1] != 200:
        return ret
    
    session = ret[2]
    
    for member in party.members:
        return_400_on_error(game_type[type].join, data, member.user, session)
    
    socketio.emit("start", {"id": session.uuid}, namespace="/socket/party", room=party.code)

    return jsonify({"message": "session started"}), 200

@party_bp.route("/join", methods=["POST"])
@login_required
def join_party(user):
    data = request.get_json()
    code = data.get("code")
    
    if not code:
        return jsonify({"error": "provided: code"}), 400
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    member = PartyMember.query.filter_by(party_id=party.id, user_id=user.id).first()
    
    if member:
        return jsonify({"error": "You are already in this party"}), 403
    
    member = PartyMember(user_id=user.id, party_id=party.id)
    db.session.add(member)
    db.session.commit()
    
    socketio.emit("add_user", user.to_json(), namespace="/socket/party", room=code)
    
    return jsonify({"message": "joined party"}), 200

@party_bp.route("/game/join", methods=["POST"])
@login_required
def start_game(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    session = party.session
    if not session:
        return jsonify({"error": "No session yet"}), 404
    
    return return_400_on_error(game_type[session.type].join, data, user, session)

@party_bp.route("host", methods=["GET"])
@login_required
def is_host(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    return jsonify({"is_host":party.host_id==user.id}), 200

@party_bp.route("/game/state", methods=["GET"])
@login_required
def get_game_state(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    session = party.session
    
    if not session:
        return jsonify({"state": "lobby"}), 200
    
    else:
        return {"state":"playing","id": session.uuid}, 200
    
@party_bp.route("/users", methods=["GET"])
@login_required
def get_users(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if not party:
        return jsonify({"error": "No session yet"}), 404
    
    members = [member.user.to_json() for member in party.members]
    
    return jsonify({"members": members,"host":party.host.username,"this":user.username}), 200

@party_bp.route("/users/remove", methods=["POST"])
@login_required
def remove_user(user):
    data = request.get_json()
    code = data.get("code")
    username = data.get("username")
    reason = data.get("reason") if data.get("reason") else "removed from party"
    
    remove_user = User.query.filter_by(username=username).first_or_404("Cannot find user")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    if remove_user.user_id == party.host_id:
        return jsonify({"error": "You cannot remove the host"}), 403
    
    member = PartyMember.query.filter_by(party_id=party.id, user_id=remove_user.id).first_or_404("Cannot find member")
    db.session.delete(member)
    db.session.commit()
    
    socketio.emit("leave",{"reason":reason},namespace="/socket/party", room=f"{member.user_id}_{code}")
    socketio.emit("remove_user", {"username": member.user.username}, namespace="/socket/party", room=code)
    
    return jsonify({"message": "removed user"}), 200

@party_bp.route("/leave", methods=["POST"])
@login_required
def leave_party(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    member = PartyMember.query.filter_by(party_id=party.id,user_id=user.id).first_or_404("Cannot find member")
    db.session.delete(member)
    db.session.commit()
    
    socketio.emit("leave",namespace="/socket/party", room=f"{member.user_id}_{code}")
    socketio.emit("remove_user", {"username": user.username}, namespace="/socket/party", room=code)
    
    return jsonify({"message": "left party"}), 200

@party_bp.route("/delete", methods=["POST"])
@login_required
def delete_party(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    db.session.delete(party)
    db.session.commit()
    
    socketio.emit("leave", {"reason": "party disbanded"}, namespace="/socket/party", room=code)
    
    return jsonify({"message": "deleted party"}), 200
    
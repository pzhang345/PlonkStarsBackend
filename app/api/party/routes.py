from flask import Blueprint, request, jsonify

from api.account.auth import login_required
from api.game.gametype import str_to_type_socket,game_type
from models.db import db
from models.party import Party
from utils import return_400_on_error

from fsocket import socketio

party_bp = Blueprint("party_bp", __name__)

@party_bp.route("/create", methods=["POST"])
@login_required
def create_party(user):
    party = Party(host_id=user.id)
    db.session.add(party)
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


@party_bp.route("/game/join", methods=["POST"])
@login_required
def start_game(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    session = party.session
    if not session:
        return jsonify({"error": "No session yet"}), 404
    
    return return_400_on_error(game_type[type].join, data, user, session)

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
        return 
    
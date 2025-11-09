from flask import Blueprint, jsonify, request


from api.account.auth import login_required
from api.game.gametype import game_type
from fsocket import socketio
from models.db import db
from models.party import Party
from models.session import Player
from utils import return_400_on_error


party_game_bp = Blueprint("party_game_bp", __name__)

@party_game_bp.route("/start", methods=["POST"])
@login_required()
def start_party(user):
    data = request.get_json()
    code = data.get("code")
    
    if not code:
        return jsonify({"error": "provided: code"}), 400
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    type = party.rules.type
    ret = return_400_on_error(game_type[type].create, data, user, party)
    if ret[1] != 200:
        return ret
    
    session = ret[2]
    party.session_id = session.id
    db.session.commit()
    
    return_400_on_error(game_type[type].next, data, None, session)
    
    socketio.emit("start", {"id": session.uuid,"type":session.type.name}, namespace="/socket/party", room=party.code)

    return jsonify({"message": "session started"}), 200

@party_game_bp.route("/join", methods=["POST"])
@login_required()
def join_game(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    session = party.session
    if not session:
        return jsonify({"error": "No session yet"}), 404
    
    return return_400_on_error(game_type[session.type].join, data, user, session)

@party_game_bp.route("/state", methods=["GET"])
@login_required()
def get_game_state(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    session = party.session
    
    if not session:
        return jsonify({"state": "lobby"}), 200
    
    else:
        player = Player.query.filter_by(user_id=user.id, session_id=session.id).first()
        return {"state":"playing","id": session.uuid,"type":session.type.name,"joined":not not player}, 200
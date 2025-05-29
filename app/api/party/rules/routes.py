from flask import Blueprint, jsonify, request

from api.account.auth import login_required
from api.game.gametype import game_type
from fsocket import socketio
from models.party import Party
from models.session import GameType
from utils import return_400_on_error

party_rules_bp = Blueprint("party_rules_bp", __name__)


@party_rules_bp.route("", methods=["GET"])
@login_required
def get_rules(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    type = party.rules.type
    
    if not party:
        return jsonify({"error": "No session yet"}), 404
    
    return return_400_on_error(game_type[type].get_rules, party, data)
    
@party_rules_bp.route("", methods=["POST"])
@login_required
def set_rules(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    base_rules = party.rules.base_rules
    type = GameType[data.get("type").upper()] if data.get("type") else base_rules.type
    
    if type != party.rules.type:
        party.rules.type = type
        ret = return_400_on_error(game_type[type].set_default_rules, party, data)
    else:
        ret = return_400_on_error(game_type[type].set_rules, party, data)
    
    if ret[1] != 200:
        return ret
    rules = game_type[type].get_rules(party,data)
    socketio.emit("update_rules", rules, namespace="/socket/party", room=party.code)
    
    return jsonify({"message": "rules updated"}), 200

@party_rules_bp.route("/config", methods=["GET"])
@login_required
def rules_config(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    type = party.rules.type
    return return_400_on_error(game_type[type].rules_config_list)
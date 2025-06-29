from flask import Blueprint, request, jsonify

from api.account.auth import login_required
from api.game.gameutils import delete_orphaned_rules
from api.party.game.routes import party_game_bp
from api.party.rules.routes import party_rules_bp
from api.party.teams.routes import party_teams_bp
from models.db import db
from models.duels import DuelRules
from models.party import Party, PartyMember, PartyRules
from models.session import BaseRules
from models.user import User
from models.configs import Configs

from fsocket import socketio

party_bp = Blueprint("party_bp", __name__)
party_bp.register_blueprint(party_game_bp, url_prefix="/game")
party_bp.register_blueprint(party_rules_bp, url_prefix="/rules")
party_bp.register_blueprint(party_teams_bp, url_prefix="/teams")

@party_bp.route("/create", methods=["POST"])
@login_required
def create_party(user):
    party = Party(host_id=user.id)
    db.session.add(party)
    db.session.flush()
    ROUND_NUMBER = int(Configs.get("GAME_DEFAULT_ROUNDS"))
    TIME_LIMIT =  int(Configs.get("GAME_DEFAULT_TIME_LIMIT"))
    NMPZ = Configs.get("GAME_DEFAULT_NMPZ").lower() == "true"
    MAP_ID = int(Configs.get("GAME_DEFAULT_MAP_ID"))
    DUELS_START_HP = int(Configs.get("DUELS_DEFAULT_START_HP"))
    DUELS_DAMAGE_MULTI_START_ROUND = int(Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND"))
    DUELS_DAMAGE_MULTI_MULT = int(Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_MULT"))
    DUELS_DAMAGE_MULTI_ADD = int(Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_ADD"))
    DUELS_DAMAGE_MULTI_FREQ = int(Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_FREQ"))
    DUELS_GUESS_TIME_LIMIT = int(Configs.get("DUELS_DEFAULT_GUESS_TIME_LIMIT"))
    
    rules = BaseRules.query.filter_by(
        map_id=MAP_ID,
        time_limit=TIME_LIMIT,
        max_rounds=ROUND_NUMBER,
        nmpz=NMPZ
    ).first()
    if not rules:
        rules = BaseRules(
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            nmpz=NMPZ
        )
        db.session.add(rules)
        db.session.flush()
    
    duel_rules = DuelRules.query.filter_by(
        start_hp=DUELS_START_HP,
        damage_multi_start_round=DUELS_DAMAGE_MULTI_START_ROUND,
        damage_multi_mult=DUELS_DAMAGE_MULTI_MULT,
        damage_multi_add=DUELS_DAMAGE_MULTI_ADD,
        damage_multi_freq=DUELS_DAMAGE_MULTI_FREQ,
        guess_time_limit=DUELS_GUESS_TIME_LIMIT
    ).first()
    
    if not duel_rules:
        duel_rules = DuelRules(
            start_hp=DUELS_START_HP,
            damage_multi_start_round=DUELS_DAMAGE_MULTI_START_ROUND,
            damage_multi_mult=DUELS_DAMAGE_MULTI_MULT,
            damage_multi_add=DUELS_DAMAGE_MULTI_ADD,
            damage_multi_freq=DUELS_DAMAGE_MULTI_FREQ,
            guess_time_limit=DUELS_GUESS_TIME_LIMIT
        )
        db.session.add(duel_rules)
        db.session.flush()
    
    party_rules = PartyRules(
        party_id=party.id,
        base_rule_id=rules.id,
        duel_rules_id=duel_rules.id
    )
    db.session.add(party_rules)
    member = PartyMember(user_id=user.id, party_id=party.id)
    
    db.session.add(member)
    db.session.commit()
    
    return jsonify({"code": party.code}), 200

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

@party_bp.route("/host", methods=["GET"])
@login_required
def is_host(user):
    data = request.args
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    return jsonify({"is_host":party.host_id==user.id}), 200
    
@party_bp.route("/users", methods=["GET"])
@login_required
def get_users_(user):
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
    
    remove_user = User.query.filter_by(username=username).first_or_404("Cannot find user")
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    
    if party.host_id != user.id:
        return jsonify({"error": "You are not the host of this party"}), 403
    
    if remove_user.id == party.host_id:
        return jsonify({"error": "You cannot remove the host"}), 403
    
    member = PartyMember.query.filter_by(party_id=party.id, user_id=remove_user.id).first_or_404("Cannot find member")
    db.session.delete(member)
    db.session.commit()
    
    socketio.emit("leave",{"reason":"Kicked from party"},namespace="/socket/party", room=f"{member.user_id}_{code}")
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
    delete_orphaned_rules()
    db.session.commit()
    
    socketio.emit("leave", {"reason": "Party disbanded"}, namespace="/socket/party", room=code)
    
    return jsonify({"message": "deleted party"}), 200

@party_bp.route("/lobby/join", methods=["POST"])
@login_required
def join_lobby(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    member = PartyMember.query.filter_by(party_id=party.id, user_id=user.id).first_or_404("Cannot find member")
    member.in_lobby = True
    db.session.commit()
        
    return jsonify({"message": "joined lobby"}), 200

@party_bp.route("/lobby/leave", methods=["POST"])
@login_required
def leave_lobby(user):
    data = request.get_json()
    code = data.get("code")
    
    party = Party.query.filter_by(code=code).first_or_404("Cannot find party")
    member = PartyMember.query.filter_by(party_id=party.id, user_id=user.id).first_or_404("Cannot find member")
    member.in_lobby = False
    db.session.commit()
        
    return jsonify({"message": "left lobby"}), 200
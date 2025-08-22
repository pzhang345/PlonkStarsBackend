from flask import Blueprint,jsonify,request

from utils import return_400_on_error
from api.account.auth import login_required
from api.game.gametype import game_type
from models.session import GameType, Session,Player


game_bp = Blueprint("game",__name__)

@game_bp.route("/create",methods=["POST"])
@login_required
def create_game(user):
    if request.is_json:
        data = request.get_json()
    else:
        data = {}
    type = GameType[data.get("type").upper()] if data.get("type") else GameType.CHALLENGE
    
    if not type:
        return jsonify({"error":"provided a correct type"}),400
    return return_400_on_error(game_type[type].create,data,user)[0:2]


@game_bp.route("/play",methods=["POST"])
@login_required
def play(user):
    data = request.get_json()
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    
    if Player.query.filter_by(session_id=session.id,user_id=user.id).count() > 0:
        return jsonify({"error":"already played this session"}),403
    return return_400_on_error(game_type[session.type].join,data,user,session)[0:2]
    
@game_bp.route("/next",methods=["POST"])
@login_required
def next_round(user):
    data = request.get_json()
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].next,data,user,session)[0:2]

@game_bp.route("/round",methods=["GET"])
@login_required
def get_round(user):
    data = request.args
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].get_round,data,user,session)[0:2]
    
@game_bp.route("/guess",methods=["POST"])
@login_required
def submit_guess(user):
    data = request.get_json()
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].guess,data,user,session)[0:2]

@game_bp.route("/state",methods=["GET"])
@login_required
def get_state(user):
    data = request.args
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].get_state_,data,user,session)[0:2]
    
@game_bp.route("/results",methods=["GET"])
@login_required
def get_result(user):
    data = request.args
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].results,data,user,session)[0:2]

@game_bp.route("/summary",methods=["GET"])
@login_required
def get_summary(user):
    data = request.args
    session_id = data.get("session")
    
    if not session_id:
        return jsonify({"error":"provided bad session id"}), 400
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].summary,data,user,session)[0:2]

@game_bp.route("/ping",methods=["POST"])
@login_required
def ping(user):
    data = request.get_json()
    session_id = data.get("id")
    
    if not session_id:
        return jsonify({"error":"provided bad session id"}), 400
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].ping,data,user,session)[0:2]

@game_bp.route("/plonk",methods=["POST"])
@login_required
def plonk(user):
    data = request.get_json()
    session_id = data.get("id")
    
    if not session_id:
        return jsonify({"error":"provided bad session id"}), 400
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    return return_400_on_error(game_type[session.type].plonk,data,user,session)[0:2]

@game_bp.route("/rules/config",methods=["GET"])
@login_required
def get_rules_range(user):
    data = request.args
    if not data.get("type") or not data.get("type").upper() in GameType.__members__:
        return jsonify({"error":"provided a correct type"}),400
    
    type = GameType[data.get("type").upper()]
    
    return return_400_on_error(game_type[type].rules_config_list)[0:2]
    
     
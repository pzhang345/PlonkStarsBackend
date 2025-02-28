from datetime import datetime,timedelta
from flask import Blueprint,jsonify,request

from api.auth.auth import login_required
from api.game.gametype import game_type
from models import Session,Player,GameType

game_bp = Blueprint("game",__name__)

str_to_type = {"challenge":GameType.CHALLENGE}

@game_bp.route("/create",methods=["POST"])
@login_required
def create_game(user):
    if request.is_json:
        data = request.get_json()
    else:
        data = {}
    type = str_to_type.get((data.get("type") if data.get("type") else "challenge").lower())
    if not type:
        type = GameType.CHALLENGE
    
    try:
        ret = game_type[type].create(data,user)
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify(ret[0]),ret[1]

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
    
    
    try:
        ret = game_type[session.type].join(data,user,session)
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify(ret[0]),ret[1]
    

@game_bp.route("/next",methods=["GET"])
@login_required
def next_round(user):
    data = request.args
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    
    try:
        ret = game_type[session.type].next(data,user,session)
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify(ret[0]),ret[1]


@game_bp.route("/guess",methods=["POST"])
@login_required
def submit_guess(user):
    data = request.get_json()
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=data["id"]).first_or_404("Session not found")
    
    try:
        ret = game_type[session.type].guess(data,user,session)
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    return jsonify(ret[0]),ret[1]
    
    
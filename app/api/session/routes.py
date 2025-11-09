from datetime import datetime, timedelta
from flask import Blueprint,request, jsonify
import pytz

from api.account.auth import login_required
from api.session.daily import create_daily
from api.session.session import get_session_info
from models.configs import Configs
from models.map import GameMap
from models.session import DailyChallenge, Session
from utils import return_400_on_error

session_bp = Blueprint("session_bp", __name__)

@session_bp.route("/info", methods=["GET"])
@login_required()
def get_session(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first()
    if not session:
        return jsonify({"error":"Session not found"}),404
    if session.host.username == "demo":
        return jsonify({"error":"Cannot play a demo session"}),400
    return return_400_on_error(get_session_info, session, user)

@session_bp.route("/daily", methods=["GET"])
@login_required(allow_demo=True)
def get_daily(user):
    now = datetime.now(tz=pytz.utc)
    today = now.date()
    daily = DailyChallenge.query.filter_by(date=today).first()
    
    if not daily:
        daily = create_daily(today)
    
    info = return_400_on_error(get_session_info, daily.session, user, json=True)
    
    if isinstance(info, tuple):
        return info
    
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(),tzinfo=now.tzinfo)
    info["next"] = tomorrow
    info["now"] = now
    
    info["id"] = daily.session.uuid
    return jsonify(info), 200

@session_bp.route("/default", methods=["GET"])
def get_default():
    ROUND_NUMBER = int(Configs.get("GAME_DEFAULT_ROUNDS"))
    TIME_LIMIT =  int(Configs.get("GAME_DEFAULT_TIME_LIMIT"))
    NMPZ = Configs.get("GAME_DEFAULT_NMPZ").lower() == "true"
    MAP_ID = int(Configs.get("GAME_DEFAULT_MAP_ID"))
    
    map = GameMap.query.filter_by(id=MAP_ID).first_or_404("Map not found")
    return jsonify({
        "mapName":map.name, 
        "map_id":map.uuid, 
        "time":TIME_LIMIT, 
        "rounds":ROUND_NUMBER, 
        "nmpz":NMPZ,
    }),200
    
@session_bp.route("/host", methods=["GET"])
@login_required()
def is_host(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    return jsonify({"is_host":session.host_id == user.id}),200
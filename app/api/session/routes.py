from datetime import datetime, timedelta
from flask import Blueprint,request, jsonify
import pytz

from api.account.auth import login_required
from api.session.session import get_session_info
from models.db import db
from models.configs import Configs
from models.map import GameMap
from models.session import BaseRules, DailyChallenge, GameType, Session

session_bp = Blueprint("session_bp", __name__)

@session_bp.route("/info", methods=["GET"])
@login_required
def get_session(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    session_info = get_session_info(session, user)
    return jsonify(session_info[0]), session_info[1]

@session_bp.route("/daily", methods=["GET"])
@login_required
def get_daily(user):
    now = datetime.now(tz=pytz.utc)
    today = now.date()
    daily = DailyChallenge.query.filter_by(date=today).first()
    
    if not daily:
        ROUND_NUMBER = int(Configs.get("DAILY_DEFAULT_ROUNDS"))
        TIME_LIMIT =  int(Configs.get("DAILY_DEFAULT_TIME_LIMIT"))
        NMPZ = Configs.get("DAILY_DEFAULT_NMPZ").lower() == "true"
        MAP_ID = int(Configs.get("DAILY_DEFAULT_MAP_ID"))
        HOST_ID = int(Configs.get("DAILY_DEFAULT_HOST_ID"))
        rules = BaseRules.query.filter_by(
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            nmpz=NMPZ
        ).first()
        
        session = Session(
            host_id=HOST_ID,
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            type=GameType.CHALLENGE, 
            nmpz=NMPZ,
            base_rule_id=rules.id,
        )
        db.session.add(session)
        db.session.flush()
        
        daily = DailyChallenge(date=today, session_id=session.id)
        db.session.add(daily)
        db.session.commit()    
    
    info = get_session_info(daily.session, user)[0]
    
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(),tzinfo=now.tzinfo)
    info["next"] = tomorrow
    
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
        "mapId":map.uuid, 
        "seconds":TIME_LIMIT, 
        "rounds":ROUND_NUMBER, 
        "NMPZ":NMPZ,
    }),200
    
@session_bp.route("/host", methods=["GET"])
@login_required
def is_host(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    return jsonify({"is_host":session.host_id == user.id}),200
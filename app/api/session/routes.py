from datetime import datetime, timedelta
from flask import Blueprint,request, jsonify
import pytz

from api.account.auth import login_required
from api.session.session import get_session_info
from models.db import db
from models.configs import Configs
from models.session import DailyChallenge, GameType, Session

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
        ROUND_NUMBER = int(Configs.query.filter_by(key="DAILY_DEFAULT_ROUNDS").first().value)
        TIME_LIMIT = int(Configs.query.filter_by(key="DAILY_DEFAULT_TIME_LIMIT").first().value)
        NMPZ = Configs.query.filter_by(key="DAILY_DEFAULT_NMPZ").first().value.lower() == "true"
        MAP_ID = int(Configs.query.filter_by(key="DAILY_DEFAULT_MAP_ID").first().value)
        HOST_ID = int(Configs.query.filter_by(key="DAILY_DEFAULT_HOST_ID").first().value)
        
        session = Session(
            host_id=HOST_ID,
            map_id=MAP_ID,
            time_limit=TIME_LIMIT,
            max_rounds=ROUND_NUMBER,
            type=GameType.CHALLENGE, 
            nmpz=NMPZ
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
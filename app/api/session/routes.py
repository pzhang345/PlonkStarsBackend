from flask import Blueprint,request, jsonify

from api.auth.auth import login_required
from models import Session, GameType

session_bp = Blueprint("session_bp", __name__)

@session_bp.route("/info", methods=["GET"])
@login_required
def get_session_info(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    if session.type != GameType.CHALLENGE:
        return jsonify({"error":"not a challenge session"}),400
    
    return jsonify({
        "map":session.map.to_json(),
        "user":session.host.to_json(),
        "rules":{
            "NMPZ":session.nmpz,
            "time":session.time_limit,
            "rounds":session.max_rounds,
        }
    }),200

from flask import Blueprint,request, jsonify

from api.auth.auth import login_required
from api.game.gameutils import timed_out
from models.session import Guess, Player, Round, Session, GameType

session_bp = Blueprint("session_bp", __name__)

@session_bp.route("/info", methods=["GET"])
@login_required()
def get_session_info(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    if session.type != GameType.CHALLENGE:
        return jsonify({"error":"not a challenge session"}),400
    
    player = Player.query.filter_by(session_id=session.id,user_id=user.id).first()
    
    last_round = Round.query.filter_by(session_id=session.id,round_number=session.max_rounds).first()
    finished = player.current_round == session.max_rounds and (Guess.query.filter_by(user_id=user.id,round_id=last_round.id).count() > 0 or timed_out(player, last_round.time_limit)) if player else False
    
    return jsonify({
        "map":session.map.to_json(),
        "user":session.host.to_json(),
        "rules":{
            "NMPZ":session.nmpz,
            "time":session.time_limit,
            "rounds":session.max_rounds,
        },
        "playing": False if not player else True,
        "finished": finished,
    }),200

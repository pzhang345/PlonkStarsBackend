from flask import Blueprint,request, jsonify
from sqlalchemy import func

from api.account.auth import login_required
from api.game.gameutils import timed_out
from models.db import db
from models.map import GameMap
from models.session import Guess, Player, Round, Session, GameType
from models.stats import MapStats

session_bp = Blueprint("session_bp", __name__)

@session_bp.route("/info", methods=["GET"])
@login_required
def get_session_info(user):
    data = request.args
    session = Session.query.filter_by(uuid=data.get("id")).first_or_404("Session not found")
    if session.type != GameType.CHALLENGE:
        return jsonify({"error":"not a challenge session"}),400
    
    player = Player.query.filter_by(session_id=session.id,user_id=user.id).first()
    
    last_round = Round.query.filter_by(session_id=session.id,round_number=session.max_rounds).first()
    finished = player.current_round == session.max_rounds and (Guess.query.filter_by(user_id=user.id,round_id=last_round.id).count() > 0 or timed_out(player, last_round.time_limit)) if player else False
    
    map,score,guess = (db.session.query(
        GameMap,
        func.sum(MapStats.total_score).label("total_score"),
        func.sum(MapStats.total_guesses).label("total_guesses"),
    )
    .outerjoin(MapStats, GameMap.id == MapStats.map_id)
    ).group_by(GameMap.id).filter(GameMap.id == session.map_id).first()
        
    return jsonify({
        "map":{
            "name":map.name,
            "id":map.uuid,
            "creator":map.creator.to_json(),
            "average_score":score/guess if guess != None or guess == 0 else 0,
            "average_generation_time": map.generation.total_generation_time/map.generation.total_loads if map.generation != None and map.generation.total_loads != 0 else 0,
            "total_guesses": guess if guess != None else 0,
        },
        "user":session.host.to_json(),
        "rules":{
            "NMPZ":session.nmpz,
            "time":session.time_limit,
            "rounds":session.max_rounds,
        },
        "playing": False if not player else True,
        "finished": finished,
    }),200

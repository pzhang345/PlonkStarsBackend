from flask import jsonify
from sqlalchemy import func

from api.game.games.challenge import ChallengeGame
from api.game.gameutils import timed_out
from models.db import db
from models.map import GameMap
from models.session import GameType, Guess, Player, Round
from models.stats import MapStats


def get_session_info(session,user):
    if session.type != GameType.CHALLENGE:
        raise Exception("not a challenge session")
    
    if ChallengeGame().get_state({},session.host,session) == "unfinished":
        raise Exception("host has not finished game")
    
    player = Player.query.filter_by(session_id=session.id,user_id=user.id).first()
    
    last_round = Round.query.filter_by(session_id=session.id,round_number=session.base_rules.max_rounds).first()
    finished = player.current_round == session.base_rules.max_rounds and (Guess.query.filter_by(user_id=user.id,round_id=last_round.id).count() > 0 or timed_out(player.start_time, last_round.base_rules.time_limit)) if player else False
    
    map,score,guess = (db.session.query(
        GameMap,
        func.sum(MapStats.total_score).label("total_score"),
        func.sum(MapStats.total_guesses).label("total_guesses"),
    )
    .outerjoin(MapStats, GameMap.id == MapStats.map_id)
    ).group_by(GameMap.id).filter(GameMap.id == session.base_rules.map_id).first()
        
    return {
        "map":{
            "name":map.name,
            "id":map.uuid,
            "creator":map.creator.to_json(),
            "average_score":score/guess if guess != None or guess == 0 else 0,
            "average_generation_time": map.generation.total_generation_time/map.generation.total_loads if map.generation != None and map.generation.total_loads != 0 else 0,
            "total_guesses": guess if guess != None else 0,
        },
        "host":session.host.to_json(),
        "rules":{
            "NMPZ":session.base_rules.nmpz,
            "time":session.base_rules.time_limit,
            "rounds":session.base_rules.max_rounds,
        },
        "playing": False if not player else True,
        "finished": finished,
    }
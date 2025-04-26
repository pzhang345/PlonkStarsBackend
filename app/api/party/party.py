
from sqlalchemy import func
from models.db import db
from models.map import GameMap
from models.stats import MapStats


def get_party_rule(party):
    rules = party.rules
    map,score,guess = (db.session.query(
        GameMap,
        func.sum(MapStats.total_score).label("total_score"),
        func.sum(MapStats.total_guesses).label("total_guesses"),
    )
    .outerjoin(MapStats, GameMap.id == MapStats.map_id)
    ).group_by(GameMap.id).filter(GameMap.id == rules.map_id).first()
    
    ret = {
        "map": {
            "name": map.name,
            "id": map.uuid,
            "creator": map.creator.to_json(),
            "average_score": float(score / guess) if guess != None or guess == 0 else 0,
            "average_generation_time": float(map.generation.total_generation_time / map.generation.total_loads) if map.generation != None and map.generation.total_loads != 0 else 0,
            "total_guesses": float(guess) if guess != None else 0,
        },
        "rounds": rules.max_rounds,
        "time": rules.time_limit,
        "type": rules.type.name,
        "nmpz": rules.nmpz,
    }
    
    return ret
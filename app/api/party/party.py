
from sqlalchemy import func
from models.configs import Configs
from models.db import db
from models.map import GameMap
from models.session import BaseRules
from models.stats import MapStats


def get_party_rule(party):
    rules = party.rules.base_rules
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
        "type": party.rules.type.name,
        "nmpz": rules.nmpz,
    }
    
    return ret

def set_party_rules(party,data):
    map = GameMap.query.filter_by(uuid=data.get("map_id")).first()
    base_rules = party.rules.base_rules
    map_id = map.id if map else base_rules.map_id
    time_limit = data.get("time") if data.get("time") else base_rules.time_limit
    max_rounds = data.get("rounds") if data.get("rounds") else base_rules.max_rounds
    nmpz = data.get("nmpz") if data.get("nmpz") != None else base_rules.nmpz
    if max_rounds <= 0 and max_rounds != -1:
        raise Exception("Invalid number of rounds")

    if time_limit <= 0 and time_limit != -1:
        raise Exception("Invalid time limit")
    
    if map and map.total_weight <= 0:
        raise Exception("Map has no locations")
    
    base_rule = BaseRules.query.filter_by(map_id=map_id, time_limit=time_limit, max_rounds=max_rounds, nmpz=nmpz).first()
    if not base_rule:
        base_rule = BaseRules(
            map_id=map_id,
            time_limit=time_limit,
            max_rounds=max_rounds,
            nmpz=nmpz
        )
        db.session.add(base_rule)
        db.session.flush()
    
    party.rules.base_rule_id = base_rule.id
    db.session.commit()
        
def set_default(party,type):
    rules = party.rules
    prefix = rules.type.name.upper() if Configs.in_(f"{type.name.upper()}_DEFAULT_ROUNDS") else "GAME"
    party.rules.type = type
    
    rounds = int(Configs.get("{prefix}_DEFAULT_ROUNDS"))
    time = int(Configs.get("{prefix}_DEFAULT_TIME_LIMIT"))
    nmpz = Configs.get(f"{prefix}_DEFAULT_NMPZ").lower() == "true"
    map_id = int(Configs.get(f"{prefix}_DEFAULT_MAP_ID"))
    
    base_rules = BaseRules.query.filter_by(
        map_id=map_id,
        time_limit=time,
        max_rounds=rounds,
        nmpz=nmpz
    ).first()
    
    if not base_rules:
        base_rules = BaseRules(
            map_id=map_id,
            time_limit=time,
            max_rounds=rounds,
            nmpz=nmpz
        )
        db.session.add(base_rules)
        db.session.flush()
    
    party.rules.base_rule_id = base_rules.id
    db.session.commit()
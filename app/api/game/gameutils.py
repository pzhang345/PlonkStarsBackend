import math
from models import GameMap,Guess

def find_map(map):
    query = GameMap.query
    map_name = map.get("name")
    if map_name:
        query = query.filter_by(name=map_name)
    
    map_id = map.get("id")
    if map_id:
        query = query.filter_by(uuid=map_id)
    
    map_creator = map.get("creator")
    if map_creator:
        query = query.filter_by(uuid=map_creator)
    
    return query.first()
    

def caculate_score(distance, max_distance, max_score):
    return max_score * math.e ** (-10*distance/max_distance)


def guess_to_json(user,round):
    guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
    if not guess:
        return {
            "score": 0,
            "correctLat": round.location.latitude,
            "correctLng": round.location.longitude,
        }

    return {
        "distance":guess.distance,
        "score": guess.score,
        "time": guess.time,
        "userLat": guess.latitude,
        "userLng": guess.longitude,
        "correctLat": guess.round.location.latitude,
        "correctLng": guess.round.location.longitude
    }
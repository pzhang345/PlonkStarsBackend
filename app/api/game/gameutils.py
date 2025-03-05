import math

from models import db,GameMap,Guess,Round,RoundStats
from api.location.generate import generate_location,get_random_bounds,db_location
from api.map.map import haversine

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

def create_round(session,time_limit):
    map = session.map
    location = generate_location(map)
    for _ in range(100):
        if Round.query.filter_by(session_id=session.id,location_id=location.id).count() == 0:
            break
        bound = get_random_bounds(map)
        location = db_location(bound)
        
    round = Round(
        location_id=location.id,
        session_id=session.id,
        round_number=session.current_round + 1,
        time_limit=time_limit
    )
    session.current_round += 1

    db.session.add(round)
    db.session.commit()

    return round

def create_guess(lat,lng,user,round,time):
    if Guess.query.filter_by(user_id=user.id,round_id=round.id).count() > 0:
        raise Exception("user has already guessed")
    
    location = round.location
    distance = haversine(lat,lng,location.latitude,location.longitude)
    guess = Guess(
        user_id=user.id,
        round_id=round.id,
        latitude=lat,
        longitude=lng,
        distance=distance,
        score=caculate_score(float(distance),float(round.session.map.max_distance),5000),
        time = time
    )
    return guess

def create_round_stats(user,session,guess):
    prevRoundStats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=guess.round.round_number-1).first()
        
    if not prevRoundStats:
        round_stats = RoundStats(
            user_id=user.id,
            session_id=session.id,
            round=guess.round.round_number,
            total_time=guess.time,
            total_score=guess.score,
            total_distance=guess.distance
        )
    else:
        round_stats = RoundStats(
            user_id=user.id,
            session_id=session.id,
            round=guess.round.round_number,
            total_time=prevRoundStats.total_time + guess.time,
            total_score=prevRoundStats.total_score + guess.score,
            total_distance=float(prevRoundStats.total_distance) + guess.distance
        )
    return round_stats
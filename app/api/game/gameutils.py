import math
from datetime import datetime
import pytz

from models import db,GameMap,Guess,Round,RoundStats,UserMapStats
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
    #stats = RoundStats.query.filter_by(user_id=user.id,session_id=round.session.id,round=round.round_number).first()
    
    if not guess:
        return {
            "score": 0,
        }

    return {
        "distance":guess.distance,
        "score": guess.score,
        "time": guess.time,
        "lat": guess.latitude,
        "lng": guess.longitude
    }

def create_round(session,time_limit):
    new_round_number = session.current_round + 1
    map = session.map
    stats = map.stats
    before = datetime.now(tz=pytz.utc)
    
    location = generate_location(map)
    for _ in range(100):
        if Round.query.filter_by(session_id=session.id,location_id=location.id).count() == 0:
            break
        bound = get_random_bounds(map)
        location = db_location(bound)
        
    stats.total_generation_time += (datetime.now(tz=pytz.utc) - before).total_seconds()
    stats.total_loads += 1
    db.session.commit()
    
    if session.current_round >= new_round_number:
        return Round.query.filter_by(session_id=session.id,round_number=new_round_number).first()
    
    round = Round(
        location_id=location.id,
        session_id=session.id,
        round_number=session.current_round + 1,
        time_limit=time_limit,
        NMPZ=session.NMPZ
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
        score=caculate_score(max(0,distance-0.05),round.session.map.max_distance,5000),
        time=time
    )
    
    stats = round.session.map.stats
    stats.total_distance = stats.total_distance + distance
    stats.total_score += guess.score
    stats.total_time += time
    stats.total_guesses += 1
    db.session.commit()
    
    return guess

def create_round_stats(user,session,round_num = None,guess=None):
    if round_num == None:
        round_num = guess.round.round_number
    prev_round_stats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=round_num-1).first()
    if not guess:
        guess = Guess(
            user_id=0,
            round_id=0,
            latitude=0,
            longitude=0,
            distance=0,
            score=0,
            time=0
        )
    
    if not prev_round_stats:
        round_stats = RoundStats(
            user_id=user.id,
            session_id=session.id,
            round=round_num,
            total_time=guess.time,
            total_score=guess.score,
            total_distance=guess.distance
        )
    else:
        round_stats = RoundStats(
            user_id=user.id,
            session_id=session.id,
            round=round_num,
            total_time=prev_round_stats.total_time + guess.time,
            total_score=prev_round_stats.total_score + guess.score,
            total_distance=prev_round_stats.total_distance + guess.distance
        )
    
    user_stat = UserMapStats.query.filter_by(user_id=user.id,map_id=session.map_id, NMPZ=session.NMPZ).first()
    if not user_stat:
        user_stat = UserMapStats(user_id=user.id,map_id=session.map_id, NMPZ=session.NMPZ)
        db.session.add(user_stat)
        db.session.flush()
    
    user_stat.total_time += guess.time
    user_stat.total_distance += guess.distance
    user_stat.total_score += guess.score
    user_stat.total_guesses += 1
    db.session.commit()
    return round_stats
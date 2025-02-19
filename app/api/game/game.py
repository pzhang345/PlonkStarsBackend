import math

from models import db,Round,GameMap,Guess
from api.location.generate import generate_location
from api.map.map import haversine

def find_map(map):
    query = GameMap.query
    map_name = map.get("name")
    if map_name:
        query.filter_by(name=map_name)
    
    map_id = map.get("id")
    if map_id:
        query.filter_by(uuid=map_id)
    
    map_creator = map.get("creator")
    if map_creator:
        query.filter_by(uuid=map_creator)
    map = query.first("No maps found")
    

def create_round(session,time_limit):
    map = session.map
    location = generate_location(map)
    count = 0
    while Round.query.filter_by(session_id=session.id,location_id=location.id).count() > 0:
        if count == 100:
            raise Exception("Cannot find new location")
        location = generate_location(map)
        count += 1
        
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


def add_guess(user_id,lat,lng,round_id):
    round = Round.query.filter_by(uuid=round_id).first_or_404("Round not found")
    if Guess.query.filter_by(user_id=user_id,round_id=round.id).count() > 0:
        raise Exception("user has already guessed")
    
    location = round.location
    distance = haversine(lat,lng,location.latitude,location.longitude)
    print(distance)
    guess = Guess(
        user_id=user_id,
        round_id=round.id,
        latitude=lat,
        longitude=lng,
        distance=distance,
        score=caculate_score(float(distance),float(round.session.map.max_distance),5000)
    )
    db.session.add(guess)
    db.session.commit()
    return guess


def caculate_score(distance, max_distance, max_score):
    return max_score * math.e ** (-10*distance/max_distance)
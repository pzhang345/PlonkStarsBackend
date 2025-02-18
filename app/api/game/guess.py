from models import db, Round, Guess
from api.map.map import haversine
import math

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
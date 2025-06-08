import math
from datetime import datetime, timedelta
import pytz
from sqlalchemy import exists, not_

from models.db import db
from models.duels import DuelRules, DuelRulesLinker
from models.party import PartyRules
from models.session import BaseRules, Guess,Round, Session
from models.map import GenerationTime
from models.stats import MapStats, RoundStats,UserMapStats
from api.location.generate import generate_location,get_random_bounds,db_location
from api.map.map import haversine
from models.user import User
from fsocket import socketio

def caculate_score(distance, max_distance, max_score):
    return max_score * math.e ** (-10*distance/max_distance)


def guess_to_json(user,round):
    guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
    
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

def create_round(session,base_rules):
    new_round_number = session.current_round + 1
    map = base_rules.map
    generation = map.generation
    before = datetime.now(tz=pytz.utc)
    
    location = generate_location(map)
    for _ in range(100):
        if Round.query.filter_by(session_id=session.id,location_id=location.id).count() == 0:
            break
        bound = get_random_bounds(map)
        location = db_location(bound)
    
    if generation == None:
        generation = GenerationTime(
            map_id=map.id,
        )
        db.session.add(generation)
        db.session.flush()
        
    generation.total_generation_time += (datetime.now(tz=pytz.utc) - before).total_seconds()
    generation.total_loads += 1
    db.session.commit()
    
    if session.current_round >= new_round_number:
        return Round.query.filter_by(session_id=session.id,round_number=new_round_number).first()
    
    round = Round(
        location_id=location.id,
        session_id=session.id,
        round_number=session.current_round + 1,
        base_rule_id=base_rules.id,
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
    rules = round.base_rules
    guess = Guess(
        user_id=user.id,
        round_id=round.id,
        latitude=lat,
        longitude=lng,
        distance=distance,
        score=caculate_score(max(0,distance-0.05),rules.map.max_distance,5000),
        time=min(time,rules.time_limit) if rules.time_limit != -1 else time
    )
    
    stats = MapStats.query.filter_by(map_id=rules.map.id,nmpz=rules.nmpz).first()
    if not stats:
        stats = MapStats(
            map_id=rules.map.id,
            nmpz=rules.nmpz
        )
        db.session.add(stats)
        db.session.flush()
    
    stats.total_distance = stats.total_distance + distance
    stats.total_score += guess.score
    stats.total_time += time
    stats.total_guesses += 1
    db.session.commit()
    
    user_stat = UserMapStats.query.filter_by(user_id=user.id,map_id=rules.map_id, nmpz=rules.nmpz).first()
    if not user_stat:
        user_stat = UserMapStats(user_id=user.id,map_id=rules.map_id, nmpz=rules.nmpz)
        db.session.add(user_stat)
        db.session.flush()
    
    user_stat.total_time += guess.time
    user_stat.total_distance += guess.distance
    user_stat.total_score += guess.score
    user_stat.total_guesses += 1
    db.session.commit()
    
    db.session.add(guess)
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
    
    db.session.add(round_stats)
    db.session.commit()
    return round_stats

def timed_out(start_time,time_limit):
    return time_limit != -1 and pytz.utc.localize(start_time) + timedelta(seconds=time_limit) < datetime.now(tz=pytz.utc)
    
def delete_orphaned_rules():
    orphan_base_rules = (
        BaseRules.query
        .filter(
            not_(exists().where(PartyRules.base_rule_id == BaseRules.id)),
            not_(exists().where(Session.base_rule_id == BaseRules.id)),
            not_(exists().where(Round.base_rule_id == BaseRules.id)),
        )
    )
    
    orphan_duel_rules = (
        DuelRules.query
        .filter(
            not_(exists().where(DuelRulesLinker.rules_id == DuelRules.id)),
            not_(exists().where(PartyRules.duel_rules_id == DuelRules.id))
        )
    )

    orphan_base_rules.delete(synchronize_session=False)
    orphan_duel_rules.delete(synchronize_session=False)
    db.session.commit()
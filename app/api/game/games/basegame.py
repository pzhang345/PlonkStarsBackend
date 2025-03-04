import math
from abc import ABC,abstractmethod

from models import db,Round,GameMap,Guess,Session,Player
from api.location.generate import generate_location,get_random_bounds,db_location
from api.map.map import haversine

class BaseGame(ABC):
    def create(self,data,type,user):
        map_data = data.get("map")
        time_limit = data.get("time") if data.get("time") else -1
        num_rounds = data.get("rounds") if data.get("rounds") else 5

        
        map = find_map(map_data) if map_data else GameMap.query.first()
        if not map:
            raise Exception("Map not found")
            
        session = Session(host_id=user.id,map_id=map.id,time_limit=time_limit,max_rounds=num_rounds,type=type)
        return {"session":session},200,session

    def join(self,data,user,session):
        return {"error":"RESTAPI join is not supported"},400
    
    def socket_join(self,data,user,session):
        return False
    
    @abstractmethod
    def get_round(self,data,user,session):
        pass
    
    @abstractmethod
    def guess(self,data,user,session):
        pass
    
    @abstractmethod
    def results(self,data,user,session):
        pass
    
    def create_round(self,session,time_limit):
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
    
    def add_guess(self,lat,lng,user,round):
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
            score=caculate_score(float(distance),float(round.session.map.max_distance),5000)
        )
        db.session.add(guess)
        db.session.commit()
        return guess
    
    def get_player(self,user,session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player:
            raise Exception("player not found")
        return player
    
    def get_round(self,player,session):
        round = Round.query.filter_by(session_id=session.id,round_number=player.current_round).first()
        if not round:
            raise Exception("Round not found")
        return round
    
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
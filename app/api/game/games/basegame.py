from abc import ABC,abstractmethod

from models.session import Round,Session,Player
from models.map import GameMap
class BaseGame(ABC):
    def create(self,data,type,user):
        map_id = data.get("map_id")
        time_limit = data.get("time") if data.get("time") else -1
        num_rounds = data.get("rounds") if data.get("rounds") else 5
        nmpz = data.get("nmpz") if data.get("nmpz") else False

        if num_rounds <= 0 and num_rounds != -1:
            raise Exception("Invalid number of rounds")
        
        if not map_id:
            raise Exception("Map not found")
        
        if time_limit <= 0 and time_limit != -1:
            raise Exception("Invalid time limit")
        
        map = GameMap.query.filter_by(uuid=map_id).first()
        if not map:
            raise Exception("Map not found")
        
        if map.total_weight <= 0:
            raise Exception("Map has no locations")
            
        session = Session(host_id=user.id,map_id=map.id,time_limit=time_limit,max_rounds=num_rounds,type=type, nmpz=nmpz)
        return session

    def join(self,data,user,session):
        pass
    
    @abstractmethod
    def get_round(self,data,user,session):
        pass
    
    @abstractmethod
    def guess(self,data,user,session):
        pass
    
    @abstractmethod
    def results(self,data,user,session):
        pass
    
    @abstractmethod
    def summary(self,data,user,session):
        pass
    
    @abstractmethod
    def get_state(self,data,user,session):
        pass
    
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
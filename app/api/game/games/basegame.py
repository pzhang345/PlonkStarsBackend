from abc import ABC,abstractmethod

from models.configs import Configs
from models.db import db
from models.session import BaseRules, Round,Session,Player
from models.map import GameMap
class BaseGame(ABC):
    def create(self,data,type,user):
        map_id = data.get("map_id") if data.get("map_id") else data.get("map").get("id")
        time_limit = data.get("time") if data.get("time") else -1
        num_rounds = data.get("rounds") if data.get("rounds") else 5
        nmpz = data.get("nmpz") if data.get("nmpz") != None else False

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
        
        rules = BaseRules.query.filter_by(
            map_id=map.id,
            time_limit=time_limit,
            max_rounds=num_rounds,
            nmpz=nmpz
        ).first()
        
        if not rules:
            rules = BaseRules(
                map_id=map.id,
                time_limit=time_limit,
                max_rounds=num_rounds,
                nmpz=nmpz
            )
            db.session.add(rules)
            db.session.flush()
            
        session = Session(host_id=user.id, type=type,base_rule_id=rules.id)
        return session

    def join(self,data,user,session):
        pass
    
    
    @abstractmethod
    def next(self,data,user,session):
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
    
    def rules_config(self):
        return {
            "time": {
                "name": "Time Limit",
                "type": "integer",
                "min": 5,
                "max": 300,
                "step": 1,
                "infinity": True,
                "default": Configs.get("GAME_DEFAULT_TIME_LIMIT"),
                
            },
            "rounds": {
                "name": "Number of Rounds",
                "type": "integer",
                "min": 5,
                "max": 20,
                "step": 1,
                "default": Configs.get("GAME_DEFAULT_ROUNDS"),
            },
            "nmpz": {
                "name": "NMPZ",
                "type": "boolean",
                "default": Configs.get("GAME_DEFAULT_NMPZ").lower() == "true",
            }
        }
    
    def ping(self,data,user,session):
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
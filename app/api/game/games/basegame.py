from abc import ABC,abstractmethod

from models.configs import Configs
from models.db import db
from models.session import BaseRules, Round,Session,Player
from models.map import GameMap
class BaseGame(ABC):
    def create(self,data,type,user):
        values = self.check_rules(data, self.rules_config(), ["time","rounds","nmpz"], ["time_limit","max_rounds","nmpz"])
        
        map_id = data.get("map_id",int(Configs.get("GAME_DEFAULT_MAP_ID")))
        map = GameMap.query.filter_by(uuid=map_id).first()
        if not map:
            raise Exception("Map not found")
        
        if map.total_weight <= 0:
            raise Exception("Map has no locations")
        
        rules = BaseRules.query.filter_by(
            map_id=map.id,
            **values
        ).first()
        
        if not rules:
            rules = BaseRules(
                map_id=map.id,
                **values
            )
            db.session.add(rules)
            db.session.flush()
            
        session = Session(host_id=user.id, type=type, base_rule_id=rules.id)
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
    
    def get_state_(self, data, user, session):
        state = self.get_state(data, user, session)
        state["state"] = state["state"].name
        return state
    
    def plonk(self, data, user, session):
        pass
    
    def ping(self, user, session):
        pass
    
    def rules_config(self):
        return {
            "rounds": {
                "name": "Number of Rounds",
                "type": "integer",
                "display":"slider",
                "min": 5,
                "max": 20,
                "step": 1,
                "default": Configs.get("GAME_DEFAULT_ROUNDS"),
            },
            "time": {
                "name": "Time Limit",
                "type": "integer",
                "display":"slider",
                "min": 5,
                "max": 300,
                "step": 1,
                "infinity": True,
                "default": Configs.get("GAME_DEFAULT_TIME_LIMIT"),
                "format" : "<value>s",
            },
            "nmpz": {
                "name": "NMPZ",
                "type": "boolean",
                "display":"checkbox",
                "default": Configs.get("GAME_DEFAULT_NMPZ").lower() == "true",
            }
        }
    
    
    def get_player(self,user,session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player:
            raise Exception("player not found")
        return player
    
    def get_round_(self,session,round_number=None):
        round = Round.query.filter_by(session_id=session.id,round_number=round_number).first()
        if not round:
            raise Exception("Round not found")
        return round
    
    def rules_config_list(self):
        config = self.rules_config()
        return [
            {
                "key": key,
                **value
            } for key, value in config.items()
        ]
        
    def check_rule(self,rule,value):
        if (rule["type"] == "integer" and not isinstance(value,int)) or \
            (rule["type"] == "number" and not isinstance(value,(int,float))) or \
            (rule["type"] == "boolean" and not isinstance(value,bool)):
            raise Exception(f"Invalid value for {rule['name']}")
        
        if "min" in rule and value < rule["min"] and value != -1:
            raise Exception(f"Value for {rule['name']} too low")
        
        if "max" in rule and value > rule["max"]:
            raise Exception(f"Value for {rule['name']} too high")
        
        if (not "infinity" in rule or not rule["infinity"]) and value == -1:
            raise Exception(f"Invalid value for {rule['name']}")
        
    def check_rules(self, data, configs, rule_names, db_names, rules_default=None):
        values = {}
        if not rules_default:
            rules_default = [configs[rule]["default"] for rule in rule_names]
        for name,db_name,default in zip(rule_names, db_names, rules_default):
            values[db_name] = data.get(name, default)
            self.check_rule(configs[name], values[db_name])
        return values
    
    def allow_demo(self):
        return False
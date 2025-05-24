from api.game.games.basegame import BaseGame
from api.game.gameutils import assign_teams
from models.configs import Configs
from models.db import db
from models.session import GameType, Session
from models.duels import DuelRules, DuelState, GameTeam, TeamPlayer, DuelHp, DuelRulesLinker
class DuelsGame(BaseGame):
    def create(self,data,user,party):
        rules = party.rules
        session = Session(host_id=user.id,type=GameType.DUELS,base_rule_id=rules.base_rule_id)
        db.session.add(session)
        db.session.flush()
        
        db.session.add(DuelRulesLinker(session_id=session.id,rules_id=rules.duel_rules.id))
        assign_teams(data.get("teams"),session,party)
        
        db.session.commit()
        return {"id":session.uuid},200,session

    def join(self,data,user,session):
        pass
    
    def next(self,data,user,session):
        pass
    
    def get_round(self,data,user,session):
        pass
    
    def guess(self,data,user,session):
        pass
    
    def results(self,data,user,session):
        pass
    
    def summary(self,data,user,session):
        pass
    
    def get_state(self,data,user,session):
        pass
    
    def ping(self,data,user,session):
        pass
    
    def rules_config(self):
        base = super().rules_config()
        
        base["rounds"]["infinity"] = True
        base["rounds"]["default"] = Configs.get("DUELS_DEFAULT_ROUNDS")
        
        base["time"]["default"] = Configs.get("DUELS_DEFAULT_TIME_LIMIT")
        
        base["nmpz"]["default"] = Configs.get("DUELS_DEFAULT_NMPZ").lower() == "true"
        
        return {
            **base,
            "hp": {
                "name": "HP",
                "type": "integer",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_HP"),
            },
            "guess_time": {
                "name": "Time After Guess",
                "type": "integer",
                "min": 5,
                "default": Configs.get("DUELS_DEFAULT_GUESS_TIME_LIMIT"),
            },
            "multi_start":{
                "name": "Multi Start Round",
                "type": "integer",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND"),
            },
            "multi_mult":{
                "name": "Multi Multiplier",
                "type": "number",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_MULT"),
            },
            "multi_add": {
                "name": "Multi Additive",
                "type": "number",
                "min": 0,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_ADD"),
            },
            "mult_freq":{
                "name": "Multi Frequency",
                "type": "integer",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_FREQ"),
            }
        },200
from api.game.games.basegame import BaseGame
from api.game.gameutils import assign_teams
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
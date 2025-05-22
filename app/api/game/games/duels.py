from api.game.games.basegame import BaseGame
from models.db import db
from models.session import GameType
from models.duels import DuelRules, DuelState, GameTeam, TeamPlayer, DuelHp, DuelRulesLinker
class DuelsGame(BaseGame):
    def create(self,data,user):
        session = super().create(data,GameType.DUELS,user)
        db.session.add(session)
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
from api.game.games.basegame import BaseGame
from models.db import db
from models.session import Player,GameType

class LiveGame(BaseGame):
    def create(self,data,user):
        ret = super().create(data,GameType.LIVE,user)
        if ret[1] != 200:
            return ret
        
        session = ret[2]
        db.session.add(session)
        db.session.commit()
        return {"id":session.uuid},200
    
    def socket_join(self, data, user, session):
        player = Player(session_id=session.id,user_id=user.id,current_round=session.current_round)
        db.session.add(player)
        db.session.commit()
        return True
    
    def next(self, data, user, session):
        pass
    
    def guess(self, data, user, session):
        pass
    
    def results(self, data, user, session):
        pass
    
    def summary(self, data, user, session):
        pass
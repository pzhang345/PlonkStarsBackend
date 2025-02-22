from api.game.games import basegame
from models import db,Player,GameType

class LiveGame(basegame):
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
    
    
    
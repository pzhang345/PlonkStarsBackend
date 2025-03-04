from datetime import datetime, timedelta

from api.game.games.basegame import BaseGame
from models import db,Round,GameType,Player,Guess

class ChallengeGame(BaseGame):
    def create(self,data,user):
        ret = super().create(data,GameType.CHALLENGE,user)
        if ret[1] != 200:
            return ret
        
        session = ret[2]
        db.session.add(session)
        db.session.commit()
        return {"id":session.uuid},200

    def join(self,data,user,session):
        player = Player(session_id=session.id,user_id=user.id)
        db.session.add(player)
        db.session.commit()
        return {"message":"session joined"},200
    
    def get_round(self,data,user,session):
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        
        if Guess.query.filter_by(user_id=user.id,round_id=round.id).count() == 0 and (round.time_limit == -1 or player.start_time + timedelta(seconds=round.time_limit) > datetime.now()):
            location = round.location
            return {
                "round":player.current_round,
                "lat":location.latitude,
                "lng":location.longitude,
                "time": player.start_time + timedelta(seconds=round.time_limit) if round.time_limit != -1 else -1
            },200
        
        if player.current_round + 1 > session.current_round:
            if session.max_rounds == session.current_round:
                return {"error":"No more rounds are available"},400
            super().create_round(session,session.time_limit)
        player.current_round += 1
        
        round = super().get_round(player,session)
        location = round.location
        
        player.start_time = datetime.now()
        db.session.commit()
        
        return {
            "round":player.current_round,
            "lat":location.latitude,
            "lng":location.longitude,
            "time": player.start_time + timedelta(seconds=round.time_limit) if round.time_limit != -1 else -1
        },200
    
    def guess(self,data,user,session):
        now = datetime.now()
        lat,lng = data.get("lat"),data.get("lng")
        if lat == None or lng == None:
            return {"error":"provided: lat, lng"},400
        
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        
        if round.time_limit != -1 and player.start_time + timedelta(seconds=round.time_limit) < now:
            return {"error":"timed out"},400
        
        guess = super().add_guess(lat,lng,user,round)
        return {"message":"guess added"},200
    
    def results(self,data,user,session):
        round_num = data.get("round")
        if not data.get("round"):
            return {"error":"not implemented yet"},400
        
        round = Round.query.filter_by(session_id=session.id,round_number=round_num).first()
        if not round:
            return {"error":"No round found"},400
        
        guess = Guess.query.filter_by(user_id=user.id,round_id=round_num).first()
        if not guess:
            return {"error":"No guess found"},400
        
        return {
            "distance":guess.distance,
            "score": guess.score
        },200
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
        if player.current_round != 0:
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
                raise Exception("No more rounds are available")
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
            raise Exception("provided: lat, lng")
        
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        
        time = (now - player.start_time).total_seconds()
        
        if round.time_limit != -1 and time > round.time_limit:
            raise Exception("timed out")
        
        guess = super().add_guess(lat,lng,user,round,time)
        return {"message":"guess added"},200
    
    def results(self,data,user,session):
        round_num = int(data.get("round"))
        
        if not data.get("round"):
            raise Exception("not implemented yet")
        
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player:
            raise Exception("No player found")
        
        if player.current_round < round_num:
            raise Exception("Round not played yet")
        
        round = Round.query.filter_by(session_id=session.id,round_number=round_num).first()
        if not round:
            raise Exception("No round found")
        
        guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
        if not guess:
            return {
                "score": 0,
                "correctLat": round.location.latitude,
                "correctLng": round.location.longitude,
            },200

        return {
            "distance":guess.distance,
            "score": guess.score,
            "time": guess.time,
            "userLat": guess.latitude,
            "userLng": guess.longitude,
            "correctLat": guess.round.location.latitude,
            "correctLng": guess.round.location.longitude
        },200
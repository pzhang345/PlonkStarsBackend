from datetime import datetime, timedelta
import pytz

from api.game.games.basegame import BaseGame
from models import db,Round,GameType,Player,Guess, RoundStats
from api.game.gameutils import guess_to_json,create_round,create_guess,create_round_stats

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
        prev_round_stats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=player.current_round).first()
        if player.current_round != 0:
            if not prev_round_stats:
                create_round_stats(user,session)
            
            round = super().get_round(player,session)
            
            if Guess.query.filter_by(user_id=user.id,round_id=round.id).count() == 0 and (round.time_limit == -1 or pytz.utc.localize(player.start_time) + timedelta(seconds=round.time_limit) > datetime.now(tz=pytz.utc)):
                location = round.location
                ret = {
                    "round":player.current_round,
                    "lat":location.latitude,
                    "lng":location.longitude,
                    "total":prev_round_stats.total_score
                }
                if round.time_limit != -1:
                    ret["time"] = pytz.utc.localize(player.start_time) + timedelta(seconds=round.time_limit)
                    ret["time_limit"] = round.time_limit
                return ret,200
            
        if player.current_round + 1 > session.current_round:
            if session.max_rounds == session.current_round:
                raise Exception("No more rounds are available")
            create_round(session,session.time_limit)
        player.current_round += 1
        
        round = super().get_round(player,session)
        location = round.location
        
        player.start_time = datetime.now(tz=pytz.utc)
        db.session.commit()
        ret =  {
            "round":player.current_round,
            "lat":location.latitude,
            "lng":location.longitude,
            "total":prev_round_stats.total_score if prev_round_stats else 0
        }
        if(round.time_limit != -1):
            ret["time"] =  pytz.utc.localize(player.start_time) + timedelta(seconds=round.time_limit)
            ret["time_limit"] = round.time_limit

        return ret,200
    
    def guess(self,data,user,session):
        now = datetime.now(tz=pytz.utc)
        lat,lng = data.get("lat"),data.get("lng")
        if lat == None or lng == None:
            raise Exception("provided: lat, lng")
        
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        
        time = (now - pytz.utc.localize(player.start_time)).total_seconds()
        
        if round.time_limit != -1 and time > round.time_limit:
            raise Exception("timed out")
        
        guess = create_guess(lat,lng,user,round,time)
        db.session.add(guess)
        db.session.flush()
        round_stat = create_round_stats(user,session,guess)
        db.session.add(round_stat)
        db.session.commit()
       
        return {"message":"guess added"},200
    
    def results(self,data,user,session):
        round_num = int(data.get("round"))
        
        if not data.get("round"):
            raise Exception("not implemented yet")
        
        top = data.get("top") if data.get("top") else 10
        if top < 1:
            raise Exception("top must be greater than 0")
        
        player = super().get_player(user,session)
        round = Round.query.filter_by(session_id=session.id,round_number=round_num).first()
        if not round:
            raise Exception("No round found")
        
        
        if player.current_round < round_num or (player.current_round == round_num and
            (Guess.query.filter_by(user_id=user.id,round_id=round.id).count() == 0 and (round.time_limit == -1 or pytz.utc.localize(player.start_time) + timedelta(seconds=round.time_limit) > datetime.now(tz=pytz.utc)))):
            raise Exception("Round not played yet")
        json = guess_to_json(user,round)
        json["total"] = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=round_num).first().total_score
        return json,200
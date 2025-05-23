from datetime import datetime, timedelta
import pytz
from sqlalchemy import desc, func

from api.game.games.basegame import BaseGame
from api.game.gameutils import guess_to_json,create_round,create_guess,create_round_stats,timed_out
from models.db import db
from models.user import User
from models.session import Round,GameType,Player, Guess
from models.stats import RoundStats,UserMapStats

class ChallengeGame(BaseGame):
    def create(self,data,user):
        session = super().create(data,GameType.CHALLENGE,user)
        db.session.add(session)
        db.session.commit()
        return {"id":session.uuid},200,session

    def join(self,data,user,session):
        state = self.get_state(data,session.host,session)[0]
        if state["state"] == "unfinished":
            raise Exception("Host has not finished the session")
        player = Player(session_id=session.id,user_id=user.id)
        db.session.add(player)
        db.session.commit()
        return {"message":"session joined"},200
    
    def next(self,data,user,session):
        state = self.get_state(data,user,session)[0]
        if state["state"] == "finished":
            raise Exception("No more rounds are available")
        
        if state["state"] == "playing":
            raise Exception("Player has not finished the current round")
        
        player = super().get_player(user,session)
        if player.current_round + 1 > session.current_round:
            create_round(session,session.base_rules)
        
        player.current_round += 1
        player.start_time = datetime.now(tz=pytz.utc)
        db.session.commit()
        
        return {"message":"round exists"},200
    
    
    def get_round(self,data,user,session):
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        prev_round_stats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=player.current_round).first()
        
        state = self.get_state(data,user,session)[0]
        if state["state"] != "playing":
            raise Exception("Call the 'next' endpoint first")
      
        prev_round_stats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=player.current_round-1).first()
        location = round.location
        map = session.base_rules.map
        ret = {
            "round":player.current_round,
            "lat":location.latitude,
            "lng":location.longitude,
            "total":prev_round_stats.total_score if prev_round_stats else 0,
            "nmpz": round.base_rules.nmpz,
            "map_bounds":{
                "start":{
                    "lat":map.start_latitude,
                    "lng":map.start_longitude,
                },
                "end":{
                    "lat":map.end_latitude,
                    "lng":map.end_longitude,
                },
            },
        }
        if round.base_rules.time_limit != -1:
            ret["time"] = pytz.utc.localize(player.start_time) + timedelta(seconds=round.base_rules.time_limit)
            ret["time_limit"] = round.base_rules.time_limit
        return ret,200
    
    def guess(self,data,user,session):
        now = datetime.now(tz=pytz.utc)
        lat,lng = data.get("lat"),data.get("lng")
        if lat == None or lng == None:
            raise Exception("provided: lat, lng")
        
        player = super().get_player(user,session)
        round = super().get_round(player,session)
        
        time = (now - pytz.utc.localize(player.start_time)).total_seconds()
        
        if timed_out(player,round.base_rules.time_limit + 1 if round.base_rules.time_limit != -1 else -1):
            raise Exception("timed out")

        guess = create_guess(lat,lng,user,round,time)
        create_round_stats(user,session,guess=guess)
       
        return {"message":"guess added"},200
    
    def get_state(self,data,user,session):
        if session.daily_challenge == None and session.host_id != user.id and session.type == GameType.CHALLENGE:
            state = self.get_state(data,session.host,session)[0]
            if state["state"] != "finished":
                return {"state":"unfinished"},200
        
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player or player.current_round == 0:
            return {"state":"not_playing"},200
        round = super().get_round(player,session)
        if not timed_out(player,round.base_rules.time_limit) and Guess.query.filter_by(user_id=user.id,round_id=round.id).count() == 0:
            return {"state":"playing","round":player.current_round},200
        else:
            next_round = player.current_round + 1
            if next_round > session.base_rules.max_rounds:
                return {"state":"finished"},200
            return {"state":"results","round":player.current_round},200
            
    
    def results(self,data,user,session):
        round_num = data.get("round")
        
        if not data.get("round"):
            raise Exception("provided round number")
        
        round_num = data.get("round",0,type=int)
        page = data.get("page", 1, type=int)
        per_page = data.get("per_page", 10, type=int)
        
        if round_num < 1 or per_page < 1:
            raise Exception("Please provide valid inputs")
        
        player = super().get_player(user,session)
        round = Round.query.filter_by(session_id=session.id,round_number=round_num).first()
        if not round:
            raise Exception("No round found")
        
        state = self.get_state(data,user,session)[0]
        if player.current_round < round_num or (player.current_round == round_num and state["state"] == "playing"):
            raise Exception("Round not finished yet")
            
        if not RoundStats.query.filter_by(session_id=session.id,round=round_num,user_id=user.id).first():
            create_round_stats(user,session,round_num=round_num)
        
        json = {
            "round_number":round_num,
            "correct":{
                "lat":round.location.latitude,
                "lng":round.location.longitude
            },
            "this_user": user.to_json(),
            "users":[
                
            ]
        }
        stats = RoundStats.query.filter_by(session_id=session.id,round=round_num).subquery()
        ranked_users = db.session.query(
            stats.c.user_id,
            stats.c.total_score,
            stats.c.total_distance,
            stats.c.total_time,
            func.rank().over(order_by=(desc(stats.c.total_score),stats.c.total_time)).label("rank")
        )
        
        this_user = db.session.query(ranked_users.subquery()).filter_by(user_id=user.id).first()
        
        
        if this_user.rank < (page - 1) * per_page + 1:
            json["users"] += [{
                "user":user.to_json(),
                "score":this_user.total_score,
                "distance":this_user.total_distance,
                "time":this_user.total_time,
                "rank":this_user.rank,
                "guess":guess_to_json(user,round),
            }]
        
        leaderboard = ranked_users.paginate(page=page,per_page=per_page,error_out=False)
        for stats in leaderboard.items:
            curr_user = User.query.filter_by(id=stats.user_id).first()
            json["users"] += [{
                "user":curr_user.to_json(),
                "score":stats.total_score,
                "distance":stats.total_distance,
                "time":stats.total_time,
                "rank":stats.rank,
                "guess":guess_to_json(curr_user,round),
            }]
            
        if this_user.rank > page * per_page:
            json["users"] += [{
                "user":user.to_json(),
                "score":this_user.total_score,
                "distance":this_user.total_distance,
                "time":this_user.total_time,
                "rank":this_user.rank,
                "guess":guess_to_json(user,round),
            }]
        
        return json,200
    
    def summary(self, data, user, session):
        page = data.get("page", 1, type=int)
        per_page = data.get("per_page", 10, type=int)
        
        if per_page < 1:
            raise Exception("Please provide valid inputs")
        
        round = Round.query.filter_by(session_id=session.id,round_number=session.base_rules.max_rounds).first()
        state = self.get_state(data,user,session)[0]
        if state["state"] != "finished":
            raise Exception("The game is not finished first")
        
        
        rounds = Round.query.filter_by(session_id=session.id).order_by(Round.round_number).all()
                
        user_stats = RoundStats.query.filter_by(user_id=user.id,session_id=session.id,round=session.base_rules.max_rounds).first()
        if not user_stats:
            create_round_stats(user,session,round_num=session.base_rules.max_rounds)
                
        stats = RoundStats.query.filter_by(session_id=session.id,round=session.base_rules.max_rounds).subquery()
        ranked_users = db.session.query(
            stats.c.user_id,
            stats.c.total_distance,
            stats.c.total_time,
            stats.c.total_score,
            func.rank().over(order_by=(desc(stats.c.total_score),stats.c.total_time)).label("rank")
        )
        
        this_user = db.session.query(ranked_users.subquery()).filter_by(user_id=user.id).first()
        leaderboard = ranked_users.paginate(page=page,per_page=per_page,error_out=False)
        
        json = {
            "this_user":user.to_json(),
            "users": [],
            "rounds": []
        }
        
        for round in rounds:
            json["rounds"] += [{
                "lat":round.location.latitude,
                "lng":round.location.longitude,
            }]
        
        if this_user.rank < (page - 1) * per_page + 1:
            json["users"] = {
                "user":user.to_json(),
                "score":user_stats.total_score,
                "distance":user_stats.total_distance,
                "time":user_stats.total_time,
                "rank":this_user.rank,
                "rounds":[guess_to_json(user,round) for round in rounds]
            }
        
        for users in leaderboard.items:
            curr_user = User.query.filter_by(id=users.user_id).first()
            json["users"] += [{
                "user":curr_user.to_json(),
                "score":users.total_score,
                "distance":users.total_distance,
                "time":users.total_time,
                "rank":users.rank,
                "guesses":[guess_to_json(curr_user,round) for round in rounds]
            }]
        
        if this_user.rank > page * per_page:
            json["users"] = {
                "user":user.to_json(),
                "score":user_stats.total_score,
                "distance":user_stats.total_distance,
                "time":user_stats.total_time,
                "rank":this_user.rank,
                "guesses":[guess_to_json(user,round) for round in rounds]
            }
        
        user_map_stat = UserMapStats.query.filter_by(user_id=user.id,map_id=session.base_rules.map_id, nmpz=session.base_rules.nmpz).first()
        if not user_map_stat:
            user_map_stat = UserMapStats(user_id=user.id,map_id=session.base_rules.map_id, nmpz=session.base_rules.nmpz)
            db.session.add(user_map_stat)
            db.session.commit()
            
        max_round = session.base_rules.max_rounds
        if session.host_id == user.id and (user_map_stat.high_average_score,user_map_stat.high_round_number,-user_map_stat.high_average_time) < (user_stats.total_score/max_round,max_round,-user_stats.total_time/max_round):
            user_map_stat.high_round_number = max_round
            user_map_stat.high_average_score = user_stats.total_score/max_round
            user_map_stat.high_average_distance = user_stats.total_distance/max_round
            user_map_stat.high_average_time = user_stats.total_time/max_round
            user_map_stat.high_session_id = session.id
            db.session.commit()
        
        return json, 200

    def rules_config(self):
        return super().rules_config(),200
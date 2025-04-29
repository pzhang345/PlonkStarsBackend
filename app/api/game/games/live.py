from api.game.games.basegame import BaseGame
from api.game.games.challenge import ChallengeGame
from api.game.gameutils import timed_out, create_round_stats
from models.db import db
from models.session import Player,GameType, Round, Guess
from models.stats import RoundStats, UserMapStats
from fsocket import socketio

class LiveGame(BaseGame):
    def create(self,data,user):
        session = super().create(data,GameType.LIVE,user)
        db.session.add(session)
        db.session.commit()
        return {"id":session.uuid},200,session
    
    def join(self,data,user,session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if player:
            return {"error":"You are already in a game"},400
        
        hostPlayer = Player.query.filter_by(user_id=session.host_id,session_id=session.id).first()
        player = Player(
            user_id=user.id,
            session_id=session.id,
        )
        if hostPlayer:
            player.start_time = hostPlayer.start_time
            player.current_round = hostPlayer.current_round
        
        db.session.add(player)
        db.session.commit()
    
        return {"id":session.uuid},200
    
    def next(self,data,user,session):
        if user.id != session.host_id:
            raise Exception("You are not the host")
        ret = ChallengeGame().next(data, user, session)
        host_player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        for player in Player.query.filter_by(session_id=session.id):
            player.current_round = host_player.current_round
            player.start_time = host_player.start_time
        db.session.commit()
        socketio.emit("next",namespace="/socket/party",room=data.get("code"))
        return ret
        
    def get_round(self, data, user, session):
        return ChallengeGame().get_round(data, user, session)
        
    def guess(self, data, user, session):
        ChallengeGame().guess(data, user, session)
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        round = super().get_round(player, session)
        if Guess.query.filter_by(round_id=round.id).count() <= Player.query.filter_by(session_id=session.id).count():
            socketio.emit("next",namespace="/socket/party",room=data.get("code"))
        return {"message":"guess submitted"},200
    
    def get_state(self, data, user, session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player:
            return {"state":"not_playing"},200
        
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        print(guess_count,player_count)
        
        if  guess_count < player_count and not timed_out(player,round.time_limit):
            guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
            if guess:
                return {"state":"waiting","round":player.current_round,"lat":guess.latitude,"lng":guess.longitude},200
            else:
                return {"state":"playing","round":player.current_round},200
        else:
            next_round = player.current_round + 1
            if next_round > session.max_rounds:
                return {"state":"finished"},200
            return {"state":"results","round":player.current_round},200
    
    def results(self, data, user, session):
        player = super().get_player(user, session)
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        if guess_count < player_count and not timed_out(player,round.time_limit):
            return {"error":"not everyone guessed"},400
            
        return ChallengeGame().results(data, user, session)
    
    def summary(self, data, user, session):
        player = super().get_player(user, session)
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        if guess_count < player_count and not timed_out(player,round.time_limit):
            return {"error":"not everyone guessed"},400
        
        ret = ChallengeGame().summary(data, user, session)
        for round_stats in RoundStats.query.filter_by(user_id=player.user_id,session_id=session.id,round=session.max_rounds):
            user_map_stat = UserMapStats.query.filter_by(user_id=user.id,map_id=session.map_id, nmpz=session.nmpz).first()
            if not user_map_stat:
                user_map_stat = UserMapStats(user_id=user.id,map_id=session.map_id, nmpz=session.nmpz)
                db.session.add(user_map_stat)
                db.session.commit()
            
            if (user_map_stat.high_average_score,user_map_stat.high_round_number,-user_map_stat.high_average_time) < (round_stats.total_score/session.max_rounds,session.max_rounds,-round_stats.total_time/session.max_rounds):
                user_map_stat.high_round_number = session.max_rounds
                user_map_stat.high_average_score = round_stats.total_score/session.max_rounds
                user_map_stat.high_average_distance = round_stats.total_distance/session.max_rounds
                user_map_stat.high_average_time = round_stats.total_time/session.max_rounds
                user_map_stat.high_session_id = session.id
                db.session.commit()
        
        party = session.party
        
        party.session_id = None
        session.type = GameType.CHALLENGE
        db.session.commit()
        return ret
    
    def ping(session):
        player = super().get_player(session.host, session)
        round = super().get_round(player, session)
        
        player_count = Player.query.filter_by(session_id=session.id).count()

        if Guess.query.join(Round).filter(Round.session_id==session.id).count() < player_count and timed_out(player,round.time_limit):
            for player in Player.query.filter_by(session_id=session.id):
                if RoundStats.query.filter_by(user_id=player.user_id,session_id=session.id,round=player.current_round).count() == 0:
                    create_round_stats(player.user,session,player.current_round)
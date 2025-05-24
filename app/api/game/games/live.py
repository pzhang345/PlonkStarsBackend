from api.game.games.basegame import BaseGame
from api.game.games.challenge import ChallengeGame
from api.game.gameutils import timed_out, create_round_stats
from models.db import db
from models.party import PartyMember
from models.session import Player,GameType, Guess, Session
from models.stats import RoundStats, UserMapStats
from fsocket import socketio

class LiveGame(BaseGame):
    def create(self,data,user,party):
        session = Session(host_id=user.id,type=GameType.LIVE,base_rule_id=party.rules.base_rule_id)
        db.session.add(session)
        db.session.flush()
        
        for member in PartyMember.query.filter_by(party_id=party.id,in_lobby=True).all():
            LiveGame().join(data, member.user, session)
            member.in_lobby = False
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
        socketio.emit("next",self.get_state(data,user,session),namespace="/socket/party",room=session.uuid)
        return ret
        
    def get_round(self, data, user, session):
        return ChallengeGame().get_round(data, user, session)
        
    def guess(self, data, user, session):
        ChallengeGame().guess(data, user, session)
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        round = super().get_round(player, session)
        socketio.emit("guess",user.to_json(),namespace="/socket/party",room=session.uuid)
        if Player.query.filter_by(session_id=session.id).count() <= Guess.query.filter_by(round_id=round.id).count():
            print("pinging",Player.query.filter_by(session_id=session.id).count(),Guess.query.filter_by(round_id=round.id).count())
            socketio.emit("next",self.get_state(data,user,session),namespace="/socket/party",room=session.uuid)
            
        return {"message":"guess submitted"},200
    
    def get_state(self, data, user, session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if not player:
            return {"state":"not_playing"},200
        
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        
        if  guess_count < player_count and not timed_out(player,round.base_rules.time_limit):
            guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
            if guess:
                return {
                    "state":"waiting",
                    "round":player.current_round,
                    "lat":guess.latitude,
                    "lng":guess.longitude,
                    "guess":guess_count,
                    "player":player_count
                },200
            else:
                return {
                    "state":"playing",
                    "round":player.current_round,
                    "guess":guess_count,
                    "player":player_count
                },200
        else:
            next_round = player.current_round + 1
            if next_round > session.base_rules.max_rounds:
                return {"state":"finished","round":player.current_round},200
            return {"state":"results","round":player.current_round},200
    
    def results(self, data, user, session):
        player = super().get_player(user, session)
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        if guess_count < player_count and not timed_out(player,round.base_rules.time_limit):
            return {"error":"not everyone guessed"},400
            
        return ChallengeGame().results(data, user, session)
    
    def summary(self, data, user, session):
        player = super().get_player(user, session)
        round = super().get_round(player, session)
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        if guess_count < player_count and not timed_out(player,round.base_rules.time_limit):
            return {"error":"not everyone guessed"},400
        
        ret = ChallengeGame().summary(data, user, session)
        
        max_rounds = session.base_rules.max_rounds
        for round_stat in RoundStats.query.filter_by(session_id=session.id,round=max_rounds):
            user_map_stat = UserMapStats.query.filter_by(user_id=round_stat.user_id,map_id=session.base_rules.map_id, nmpz=session.base_rules.nmpz).first()
            if not user_map_stat:
                user_map_stat = UserMapStats(user_id=round_stat.user_id,map_id=session.map_id, nmpz=session.base_rules.nmpz)
                db.session.add(user_map_stat)
                db.session.commit()
            
            if (user_map_stat.high_average_score,user_map_stat.high_round_number,-user_map_stat.high_average_time) < (round_stat.total_score/max_rounds,max_rounds,-round_stat.total_time/max_rounds):
                user_map_stat.high_round_number = max_rounds
                user_map_stat.high_average_score = round_stat.total_score/max_rounds
                user_map_stat.high_average_distance = round_stat.total_distance/max_rounds
                user_map_stat.high_average_time = round_stat.total_time/max_rounds
                user_map_stat.high_session_id = session.id
                db.session.commit()
        
        party = session.party
        
        party.session_id = None
        session.type = GameType.CHALLENGE
        db.session.commit()
        socketio.emit("summary",namespace="/socket/party",room=session.uuid)
        return ret
    
    def ping(self,data,user,session):
        player = super().get_player(session.host, session)
        round = super().get_round(player, session)
        
        player_count = Player.query.filter_by(session_id=session.id).count()
        guess_count = Guess.query.filter_by(round_id=round.id).count()
        
        if guess_count < player_count and timed_out(player,round.base_rules.time_limit + 1):
            for player in Player.query.filter_by(session_id=session.id):
                if RoundStats.query.filter_by(user_id=player.user_id,session_id=session.id,round=player.current_round).count() == 0:
                    create_round_stats(player.user,session,player.current_round)
            socketio.emit("next",self.get_state(data,user,session),namespace="/socket/party",room=session.uuid)        
            
    def rules_config(self):
        return ChallengeGame().rules_config()
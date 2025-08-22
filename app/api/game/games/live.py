from api.game.games.challenge import ChallengeGame
from api.game.games.party_game import PartyGame
from api.game.gameutils import create_guess_on_timeout, timed_out, create_round_stats
from api.game.tasks import stop_current_task, update_game_state
from models.db import db
from models.party import PartyMember
from models.session import GameState, GameStateTracker, Player,GameType, Guess, PlayerPlonk, Session
from models.stats import RoundStats, UserMapStats
from fsocket import socketio

class LiveGame(PartyGame):
    def create(self,data,user,party):
        session = super().create(user,GameType.LIVE,party.rules.base_rules)
        
        for member in PartyMember.query.filter_by(party_id=party.id,in_lobby=True).all():
            LiveGame().join(data, member.user, session)
            member.in_lobby = False
        db.session.commit()
        return {"id":session.uuid},200,session
    
    def join(self,data,user,session):
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        if player:
            raise Exception("You are already in a game")
        
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
        
        socketio.emit("join_game", user.to_json(), namespace="/socket/party", room=session.uuid)
    
        return {"id":session.uuid}
    
    def next(self,data,user,session):
        if user.id != session.host_id:
            raise Exception("You are not the host")
        
        if session.current_round >= session.base_rules.max_rounds:
            self.update_state({"state":GameState.FINISHED}, session)
            return
        
        ret = ChallengeGame().next(data, user, session)
        host_player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        for player in Player.query.filter_by(session_id=session.id):
            player.current_round = host_player.current_round
            player.start_time = host_player.start_time
        db.session.commit()
        
        self.change_state(session, GameState.GUESSING, time=host_player.start_time)
        
        round = self.get_round_(session, host_player.current_round)
        if round.base_rules.time_limit > 0:
            update_game_state({}, session, round.base_rules.time_limit + 1)
        
        return ret
        
    def get_round(self, data, user, session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.GUESSING:
            raise Exception("not correct state")
        return ChallengeGame().get_round(data, user, session)
        
    def guess(self, data, user, session):        
        ChallengeGame().guess(data, user, session)
        player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
        round = self.get_round_(session,player.current_round)
        socketio.emit("guess",user.to_json(),namespace="/socket/party",room=session.uuid)
        if Player.query.filter_by(session_id=session.id).count() <= Guess.query.filter_by(round_id=round.id).count():
            stop_current_task(session)
            self.change_state(session, GameState.RESULTS)
            
        return {"message":"guess submitted"}
    
    def get_state(self, data, user, session, only_state=False, called=False):
        game_state_tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
        state = game_state_tracker.state if game_state_tracker else GameState.NOT_STARTED
        ret = {"state": state}
        if not only_state and state == GameState.GUESSING: 
            round = self.get_round_(session,session.current_round)
            if timed_out(game_state_tracker.time, round.base_rules.time_limit) and not called:
                self.update_state(data,session)
                return ret
              
            ret = {
                **ret,
                "round": session.current_round,
                "guess": Guess.query.filter_by(round_id=round.id).count(),
                "player": Player.query.filter_by(session_id=session.id).count()
            }
            
            player = Player.query.filter_by(user_id=user.id,session_id=session.id).first()
            if not player:
                return ret
            
            guess = Guess.query.filter_by(user_id=user.id,round_id=round.id).first()
            if guess:
                ret = {
                    **ret,
                    "guessed":True,
                    "lat":guess.latitude,
                    "lng":guess.longitude,
                }
            else:
                ret = {
                    **ret,
                    "guessed": False,
                }
                player_plonk = PlayerPlonk.query.filter_by(user_id=user.id,round_id=round.id).first()
                if player_plonk:
                    ret["lat"] = player_plonk.latitude
                    ret["lng"] = player_plonk.longitude
        return ret
    
    def results(self, data, user, session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.RESULTS:
           raise Exception("not correct state")          
        return ChallengeGame().results(data, user, session)
    
    def summary(self, data, user, session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.FINISHED:
            raise Exception("not correct state")
        return ChallengeGame().summary(data, user, session)            
    
    def update_state(self,data,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        current_round = self.get_round_(session, session.current_round)
        if state.state == GameState.GUESSING and timed_out(state.time, current_round.base_rules.time_limit):
            for player in Player.query.filter_by(session_id=session.id):
                if RoundStats.query.filter_by(user_id=player.user_id,session_id=session.id,round=session.current_round).count() == 0:
                    guess = create_guess_on_timeout(player.user, current_round)
                    create_round_stats(player.user, session, round_num=session.current_round, guess=guess)
            self.change_state(session, GameState.RESULTS)
            
        elif state.state == GameState.RESULTS and session.current_round == session.base_rules.max_rounds \
            and data.get("state") == GameState.FINISHED:
                
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
            self.change_state(session, GameState.FINISHED)
            party = session.party
        
            GameStateTracker.query.filter_by(session_id=session.id).delete()
            party.session_id = None
            session.type = GameType.CHALLENGE
            db.session.commit()
            
    def plonk(self, data, user, session):
        return ChallengeGame().plonk(data, user, session)
    
    def rules_config(self):
        return ChallengeGame().rules_config()
    
    def get_rules(self,party,data):
        rules = super().get_rules(party,data)
        rules["team_type"] = "solo"
        return rules
        
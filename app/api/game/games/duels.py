from datetime import datetime, timedelta
from flask_socketio import join_room
import pytz
from sqlalchemy import func

from api.game.games.party_game import PartyGame
from api.game.gameutils import create_guess, create_round, timed_out
from fsocket import socketio
from models.configs import Configs
from models.db import db
from models.session import GameType, Guess, Round
from models.duels import DuelRules, DuelState, GameTeam, GameTeamLinker, TeamPlayer, DuelHp, DuelRulesLinker, MarkerPosition
from models.user import User
class DuelsGame(PartyGame):
    def create(self,data,user,party):
        session = super().create(user,GameType.DUELS,party.rules)
        
        rules = party.rules
        db.session.add(DuelRulesLinker(session_id=session.id,rules_id=rules.duel_rules.id))
        for teams in party.teams:
            team = GameTeam(
                session_id=session.id,
                team_id=teams.team.id,
                color=teams.color
            )
            db.session.add(team)
            db.session.flush()
        
        db.session.commit()
        return {"id":session.uuid},200,session

    def join(self,data,user,session):
        pass
    
    def next(self,data,user,session):
        state = self.get_state(data,user,session,only_state=True)
        if state["state"] != "results" and state["state"] != "not started":
            raise Exception("Game is in the wrong state")
        
        round = create_round(session,session.base_rules)
        duel_rules = session.duel_rules
        prev_round = self.get_round_(session,session.current_round - 1) if session.current_round > 1 else None
        prev_multi = prev_round.duels_state.multi if prev_round else 1
        new_multi = (duel_rules.damage_mutli_mult * prev_multi) + duel_rules.damage_multi_add
        
        duel_state = DuelState(
            round_id=round.id,
            multi=new_multi
        )
        db.session.add(duel_state)
        db.session.commit()
        
        socketio.emit("next", self.get_state(data, user, session, only_state=True), namespace="/socket/party", room=session.uuid)
            
    def get_round(self,data,user,session):
        state = self.get_state(data,user,session,only_state=True)
        if state["state"] != "playing" and state["state"] != "waiting" and state["state"] != "spectating":
            raise Exception("Game is in the wrong state")
        
        round = self.get_round_(session,session.current_round)
        
        location = round.location
        ret = {
            "lat": location.latitude,
            "lng": location.longitude,   
            "multi": round.duels_state.multi
        }
        
        if round.base_rules.time_limit != -1:
            first_guess = Guess.query.filter_by(round_id=round.id).order_by(Guess.time).first()
            time_limit = min(round.base_rules.time_limit, first_guess.time + round.session.duel_rules.guess_time_limit) if first_guess else round.base_rules.time_limit
            ret["time"] = pytz.utc.localize(round.duels_state.start_time) + timedelta(seconds=time_limit)
            ret["time_limit"] = time_limit if time_limit == round.base_rules.time_limit else round.session.duel_rules.guess_time_limit
            ret["now"] = datetime.now(tz=pytz.utc)
        
        return ret
        
    def guess(self,data,user,session):
        state = self.get_state(data,user,session,only_state=True)
        if state["state"] != "playing":
            raise Exception("Game is in the wrong state")
        
        player = TeamPlayer.query.filter_by(user_id=user.id).join(GameTeam).filter(GameTeam.session_id == session.id).first()
        if not player:
            raise Exception("You are not in a team")
        
        game_team = player.team
        
        lat = data.get("lat")
        lng = data.get("lng")
        if lat == None or lng == None:
            raise Exception("You must provide a latitude and longitude")
            
        round = self.get_round_(session,session.current_round)
        if Guess.query.filter_by(round_id=round.id,user_id=user.id).count() > 0:
            raise Exception("You have already guessed this round")
        
        now = datetime.now(tz=pytz.utc)
        time = (now - pytz.utc.localize(player.start_time)).total_seconds()
        
        create_guess(lat, lng, user, round, time)
        socketio.emit("guess", {"user": user.to_json(), "lat": lat, "lng": lng}, namespace="/socket/party", room=f"team_{game_team.hash}")
        socketio.emit("guess", {"user": user.to_json()}, namespace="/socket/party", room=session.uuid)
        
        if Guess.query.filter_by(round_id=round.id).count() >= TeamPlayer.query.join(GameTeam).join(GameTeamLinker).filter(GameTeamLinker.session_id == session.id).count():
            socketio.emit("next", self.get_state(data, user, session, only_state=True), namespace="/socket/party", room=session.uuid)
        
    def results(self,data,user,session):
        state = self.get_state(data,user,session,only_state=True)
        if state["state"] != "results" and state["state"] != "finished":
            raise Exception("Game is in the wrong state")
        
        round = self.get_round_(session,session.current_round)
        prev_round = self.get_round_(session, session.current_round - 1) if session.current_round > 1 else None
        duels_state = round.duels_state
        
        if DuelHp.query.filter_by(state_id=duels_state.id).count() < GameTeam.query.filter_by(session_id=session.id).count():
            high_team_scores = (db.session.query(
                GameTeam.id,
                func.coalesce(func.max(Guess.score), 0).label("max_score")
            )
            .join(GameTeamLinker, GameTeamLinker.team_id == GameTeam.id)
            .join(DuelHp, DuelHp.team_id == GameTeam.id)
            .filter(GameTeamLinker.session_id == session.id)
            )
            
            if prev_round:
                high_team_scores = high_team_scores.filter(DuelHp.state_id == prev_round.duels_state.id, DuelHp.hp != 0)
            
            high_team_scores = (high_team_scores
            .join(TeamPlayer, TeamPlayer.team_id == GameTeam.id)
            .join(User, User.id == TeamPlayer.user_id)
            .outerjoin(Guess, Guess.user_id == User.id)
            .group_by(GameTeam.id)
            )
            
            high_score = Guess.query.join(Round).filter(Round.session_id == session.id).order_by(Guess.score.desc()).first()
            
            for team_id, score in high_team_scores:
                prev_duel_hp = DuelHp.query.filter_by(state_id=state.id, team_id=team_id).first()
                if not prev_duel_hp:
                    prev_duel_hp = session.duel_rules.start_hp
                else:
                    prev_duel_hp = prev_duel_hp.hp
                

                if high_score and score < high_score.score:
                    score = high_score.score
                
                duel_hp = DuelHp.query.filter_by(state_id=state.id, team_id=team_id).first()
                if not duel_hp:
                    duel_hp = DuelHp(state_id=state.id, team_id=team_id, hp=max(0,prev_duel_hp + score - high_score.score))
                    db.session.add(duel_hp)
                else:
                    duel_hp.hp = max(0,prev_duel_hp + (score - high_score.score) * duels_state.multi)
                
                db.session.commit()

        ret = {
            "lat": round.location.latitude,
            "lng": round.location.longitude,
            "max_hp": session.duel_rules.start_hp,
            "multi": duels_state.multi,
            "teams":[]
        }
        for hp in DuelHp.query.filter_by(state_id=duels_state.id).order_by(DuelHp.hp.desc()):
            team = hp.team
            prev_round_hp = DuelHp.query.filter_by(state_id=prev_round.duels_state.id, team_id=team.id).first()
            if not prev_round_hp:
                prev_round_hp = session.duel_rules.start_hp
            else:
                prev_round_hp = prev_round_hp.hp
            ret["teams"].append({
                "team": team.to_json(),
                "prev_hp": prev_round_hp,
                "hp": hp.hp,
                "guesses": [
                    {
                        "user": guess.user.username,
                        "lat": guess.latitude,
                        "lng": guess.longitude,
                        "score": guess.score,
                    } for guess in Guess.query.join(User).join(TeamPlayer, User.id == TeamPlayer.user_id).join(Round).filter(team.id == TeamPlayer.team_id, Round.id==round.id).order_by(Guess.score.desc())
                ]
            })        
        
        return ret
            
    def summary(self,data,user,session):
        state = self.get_state(data,user,session,only_state=True)
        if state["state"] != "finished":
            raise Exception("Game is in the wrong state")
        
        rounds = Round.query.filter_by(session_id=session.id).order_by(Round.round_number).all()
        
        ret = {
            "teams": [],
            "rounds": [{
                "lat": round.location.latitude,
                "lng": round.location.longitude,
                "multi": round.duels_state.multi,
            } for round in rounds],
        }
        
        teams = (
            GameTeamLinker.query.
            filter_by(session_id=session.id)
            .join(GameTeam)
            .join(DuelHp)
            .join(DuelState)
            .join(Round)
            .order_by(func.max(Round.round_number).desc(), func.min(DuelHp.hp).desc())
        )
        for team in teams:
            team_data = {
                "team": team.team.to_json(),
                "rounds": [],
            }
            for hp in DuelHp.query.filter_by(team_id=team.id).join(DuelState).join(Round).filter(Round.session_id==session.id).order_by(Round.round_number):
                round = hp.state.round
                team_data["rounds"].append({
                    "hp": hp.hp,
                    "guesses": [
                        {
                            "user": guess.user.username,
                            "lat": guess.latitude,
                            "lng": guess.longitude,
                            "score": guess.score,
                        } for guess in Guess.query.join(User).join(TeamPlayer, User.id == TeamPlayer.user_id).join(Round).filter(team.id == TeamPlayer.team_id,Round.id==round.id).order_by(Guess.score.desc())
                    ]
                })
            ret["teams"].append(team_data)
        return ret
    
    def get_state(self,data,user,session, only_state=False):
        if session.current_round == 0:
            return {"state":"not started"}
        round = self.get_round_(session,session.current_round)
        
        state = DuelState.query.filter_by(round_id=round.id).first()
        
        first_guess = Guess.query.filter_by(round_id=round.id).order_by(Guess.time).first()
        if (DuelHp.query.filter_by(state_id=state.id).count() == 0
            and not timed_out(round.duels_state.start_time,min(round.base_rules.time_limit, first_guess.time + round.session.duel_rules.guess_time_limit) if first_guess else round.base_rules.time_limit)
            and Guess.query.filter_by(round_id=round.id).count() < TeamPlayer.query.join(GameTeam).join(GameTeamLinker).filter(GameTeamLinker.session_id == session.id).count()):
            
            game_team = GameTeamLinker.query.filter(GameTeamLinker.session_id==session.id).join(GameTeam).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first() if user else None
            prev_round = self.get_round_(session, session.current_round - 1) if session.current_round > 1 else None
            hp = session.duel_rules.start_hp if prev_round == None else DuelHp.query.filter_by(state_id=prev_round.duels_state.id, team_id=game_team.team.id).first() if game_team else None
            
            if only_state:
                if hp == None or hp.hp <= 0:
                    return {"state":"spectating", "round": round.round_number}
                else:
                    return {
                        "state":"playing" if Guess.query.filter_by(round_id=round.id,user_id=user.id).count() == 0 else "waiting",
                        "round": round.round_number
                        }
            
            if hp == None or hp.hp <= 0:
                return {
                    "state":"spectating",
                    "round": round.round_number,
                    "max_hp": session.duel_rules.start_hp,
                    "teams": [
                        {
                            **team.to_json(),
                            "hp": session.duel_rules.start_hp
                        } for team in GameTeamLinker.query.filter_by(session_id=session.id)
                    ] if session.current_round == 1 else [
                        {
                            **hp.team.to_json(),
                            "hp": hp.hp
                        }
                        for hp in DuelHp.query.filter_by(state_id=prev_round.state.id).filter(DuelHp.hp > 0).order_by(DuelHp.hp.desc())
                    ] 
                }
            
            last_round = self.get_round_(session,session.current_round - 1) if session.current_round > 1 else None
            round = self.get_round_(session,session.current_round)
            return {
                "state":"playing" if Guess.query.filter_by(round_id=round.id,user_id=user.id).count() == 0 else "waiting",
                "round": round.round_number, 
                "team": game_team.to_json(),
                "max_hp": session.duel_rules.start_hp,
                "markers": [
                    {
                        "user": marker.player.user.to_json(),
                        "lat": marker.latitude,
                        "lng": marker.longitude,
                    } for marker in MarkerPosition.query.join(TeamPlayer).filter(game_team.id == TeamPlayer.team_id)
                ],
                "guesses": [
                    {
                        "user": guess.user.to_json(),
                        "lat": guess.latitude,
                        "lng": guess.longitude,
                    } for guess in Guess.query.join(User).join(TeamPlayer,User.id == TeamPlayer.user_id).join(GameTeam).join(GameTeamLinker).filter(game_team.id == TeamPlayer.team_id,Guess.round_id == round.id)
                ],
                "teams": [
                    {
                        **team.to_json(),
                        "hp": session.duel_rules.start_hp
                    } for team in GameTeamLinker.query.filter_by(session_id=session.id)
                ] if session.current_round == 1 else [
                    {
                        **hp.team.to_json(),
                        "hp": hp.hp
                    } for hp in DuelHp.query.filter_by(state_id=prev_round.state.id).filter(DuelHp.hp > 0).order_by(DuelHp.hp.desc())
                ] 
            }
            
        
        if DuelHp.query.filter_by(state_id=state.id).filter(DuelHp.hp != 0).count() < 1 or session.current_round == session.base_rules.max_rounds:
            return {"state":"finished", "round": round.round_number}
    
        return {"state":"results","round":round.round_number}
        
    
    def ping(self,data,user,session):
        if data.get("type") == "plonk":
            state = self.get_state(data,user,session,only_state=True)
            if state["state"] != "playing" and state["state"] != "waiting":
                raise Exception("Game is in the wrong state")
            
            player = TeamPlayer.query.filter_by(user_id=user.id).join(GameTeam).join(GameTeamLinker).filter(GameTeamLinker.session_id == session.id).first()
            if not player:
                raise Exception("You are not in a team")
            
            game_team = player.team
            
            lat = data.get("lat")
            lng = data.get("lng")
            if lat == None or lng == None:
                raise Exception("You must provide a latitude and longitude")
            
            marker = MarkerPosition.query.filter_by(player_id=player.id).first()
            if not marker:
                marker = MarkerPosition(player_id=player.id, latitude=lat, longitude=lng)
                db.session.add(marker)
            else:
                marker.latitude = lat
                marker.longitude = lng
            
            db.session.commit()
            socketio.emit("plonk", {"user": user.to_json(), "lat": lat, "lng":lng}, namespace="/socket/party", room=f"team_{game_team.hash}")

        elif data.get("type") == "ping":
            state = self.get_state(data,user,session,only_state=True)
            duel_state = DuelState.query.filter_by(round_id=round.id).first()
            if (state["state"] == "results" or state["state"] == "finished") and DuelHp.query.filter_by(state_id=duel_state.id).count() == 0:
                socketio.emit("next", self.get_state(data, user, session, only_state=True), namespace="/socket/party", room=session.uuid)
                
    def rules_config(self):
        base = super().rules_config()
        
        base["rounds"]["infinity"] = True
        base["rounds"]["default"] = Configs.get("DUELS_DEFAULT_ROUNDS")
        
        base["time"]["default"] = Configs.get("DUELS_DEFAULT_TIME_LIMIT")
        
        base["nmpz"]["default"] = Configs.get("DUELS_DEFAULT_NMPZ").lower() == "true"
        
        return {
            **base,
            "hp": {
                "name": "HP",
                "type": "integer",
                "display":"input",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_HP"),
            },
            "guess_time": {
                "name": "Time After Guess",
                "type": "integer",
                "display":"input",
                "min": 5,
                "default": Configs.get("DUELS_DEFAULT_GUESS_TIME_LIMIT"),
            },
            "multi_start":{
                "name": "Multi Start Round",
                "type": "integer",
                "display":"input",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_START_ROUND"),
            },
            "multi_mult":{
                "name": "Multi Multiplier",
                "type": "number",
                "display":"input",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_MULT"),
            },
            "multi_add": {
                "name": "Multi Additive",
                "type": "number",
                "display":"input",
                "min": 0,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_ADD"),
            },
            "mult_freq":{
                "name": "Multi Frequency",
                "type": "integer",
                "display":"input",
                "min": 1,
                "default": Configs.get("DUELS_DEFAULT_DAMAGE_MULTI_FREQ"),
            }
        }
        
    def set_rules(self, party, data):
        super().set_rules(party, data)
        
        duel_rules = party.rules.duel_rules
        start_hp = data.get("hp", duel_rules.start_hp)
        damage_multi_start_round = data.get("multi_start", duel_rules.damage_multi_start_round)
        damage_multi_mult = data.get("multi_mult", duel_rules.damage_multi_mult)
        damage_multi_add = data.get("multi_add", duel_rules.damage_multi_add)
        damage_multi_freq = data.get("mult_freq", duel_rules.damage_multi_freq)
        guess_time_limit = data.get("guess_time", duel_rules.guess_time_limit)
        
        duel_rules = DuelRules.query.filter_by(
            start_hp=start_hp,
            damage_multi_start_round=damage_multi_start_round,
            damage_multi_mult=damage_multi_mult,
            damage_multi_add=damage_multi_add,
            damage_multi_freq=damage_multi_freq,
            guess_time_limit=guess_time_limit
        ).first()
        
        if not duel_rules:
            duel_rules = DuelRules(
                start_hp=start_hp,
                damage_multi_start_round=damage_multi_start_round,
                damage_multi_mult=damage_multi_mult,
                damage_multi_add=damage_multi_add,
                damage_multi_freq=damage_multi_freq,
                guess_time_limit=guess_time_limit
            )
            db.session.add(duel_rules)
            db.session.flush()
        
        party.rules.duel_rules_id = duel_rules.id
        db.session.commit()
        
        
    def get_rules(self, party, data):
        rules = super().get_rules(party, data)
        duel_rules = party.rules.duel_rules
        
        return {
            **rules,
            "team_type": "team",
            "hp": duel_rules.start_hp,
            "multi_start": duel_rules.damage_multi_start_round,
            "multi_mult": duel_rules.damage_multi_mult,
            "multi_add": duel_rules.damage_multi_add,
            "mult_freq": duel_rules.damage_multi_freq,
            "guess_time": duel_rules.guess_time_limit,
        }
        
    def join_socket(self, session, user):
        super().join_socket(session, user)
        team = GameTeamLinker.query.filter_by(session_id=session.id).join(GameTeam).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first()
        if team:
            join_room(f"team_{team.hash}")
        else: 
            join_room(f"spectator_{session.uuid}")
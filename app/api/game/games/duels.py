from datetime import datetime, timedelta
from flask_socketio import join_room
import pytz
from sqlalchemy import func

from api.game.games.party_game import PartyGame
from api.game.gameutils import create_guess, create_plonk, create_round, timed_out
from api.game.tasks import stop_current_task, update_game_state
from fsocket import socketio
from models.configs import Configs
from models.db import db
from models.session import GameState, GameStateTracker, GameType, Guess, PlayerPlonk, Round
from models.duels import DuelRules, DuelState, GameTeam, GameTeamLinker, TeamPlayer, DuelHp, DuelRulesLinker
from models.user import User
class DuelsGame(PartyGame):
    def create(self,data,user,party):
        session = super().create(user,GameType.DUELS,party.rules.base_rules)
        
        rules = party.rules
        db.session.add(DuelRulesLinker(session_id=session.id,rules_id=rules.duel_rules.id))
        for teams in party.teams:
            team = GameTeam(
                session_id=session.id,
                team_id=teams.team.id,
                color=teams.color,
                name=teams.name,
                uuid=teams.uuid
            )
            db.session.add(team)
            db.session.flush()
        
        db.session.commit()
        return {"id":session.uuid},200,session

    def join(self,data,user,session):
        pass
    
    def next(self,data,user,session):
        if user != None:
            raise Exception("Cannot be called by a user")
        
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state == GameState.GUESSING or state.state == GameState.FINISHED:
            raise Exception("Game is in the wrong state")
        
        
        
        duel_rules = session.duel_rules
        prev_round = self.get_round_(session,session.current_round) if session.current_round != 0 else None
        prev_multi = prev_round.duels_state.multi if prev_round else 1
        
        if prev_round and DuelHp.query.filter_by(state_id=prev_round.duels_state.id).filter(DuelHp.hp > 0).count() < 2 or session.current_round >= session.base_rules.max_rounds:
            self.change_state(session, GameState.FINISHED)
            return
        
        if (session.current_round - duel_rules.damage_multi_start_round) % duel_rules.damage_multi_freq == 0:
            new_multi = (duel_rules.damage_mutli_mult * prev_multi) + duel_rules.damage_multi_add
        else:
            new_multi = prev_multi
        
        round = create_round(session,session.base_rules)
        duel_state = DuelState(
            round_id=round.id,
            multi=new_multi
        )
        db.session.add(duel_state)
        db.session.flush()
        
        
        if round.round_number  == 1:        
            for team in GameTeam.query.join(GameTeamLinker).filter(GameTeamLinker.session_id==session.id).all():
                db.session.add(DuelHp(team_id=team.id,state_id=duel_state.id,hp=duel_rules.start_hp))
        else:
            for prev_hp in DuelHp.query.filter_by(state_id=prev_round.duels_state.id).filter(DuelHp.hp > 0).all():
                db.session.add(DuelHp(team_id=prev_hp.team_id,state_id=duel_state.id,hp=prev_hp.hp))
                
        db.session.commit()
        
        self.change_state(session, GameState.GUESSING)
        
        if round.base_rules.time_limit != -1:
            update_game_state({"state":GameState.RESULTS}, session, round.base_rules.time_limit + 1)
            
    def get_round(self,data,user,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.GUESSING:
            raise Exception("Game is in the wrong state")
        
        round = self.get_round_(session,session.current_round)
        
        location = round.location
        map = round.base_rules.map
        ret = {
            "round": round.round_number,
            "lat": location.latitude,
            "lng": location.longitude,   
            "nmpz": session.base_rules.nmpz,
            "map_bounds": map.get_bounds(),
        }
        first_guess = Guess.query.filter_by(round_id=round.id).order_by(Guess.time).first()
        if round.base_rules.time_limit != -1 or first_guess:
            time_limit = min(round.base_rules.time_limit, first_guess.time + round.session.duel_rules.guess_time_limit) if first_guess else round.base_rules.time_limit
            ret["time"] = pytz.utc.localize(round.duels_state.start_time) + timedelta(seconds=time_limit)
            ret["time_limit"] = time_limit if time_limit == round.base_rules.time_limit else round.session.duel_rules.guess_time_limit
            ret["now"] = datetime.now(tz=pytz.utc)
        
        return ret
        
    def guess(self,data,user,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state["state"] != GameState.GUESSING:
            raise Exception("Game is in the wrong state")
        
        player = TeamPlayer.query.filter_by(user_id=user.id).join(GameTeam).filter(GameTeam.session_id == session.id).first()
        if not player:
            raise Exception("You are not in a team")
        
        round = self.get_round_(session,session.current_round)
        if Guess.query.filter_by(round_id=round.id,user_id=user.id).count() > 0:
            raise Exception("You have already guessed this round")
        
        can_guess = self.can_guess(session)
        if can_guess.filter(TeamPlayer.id == player.id).count() == 0:
            raise Exception("You cannot guess")
        
        lat = data.get("lat")
        lng = data.get("lng")
        if lat == None or lng == None:
            raise Exception("You must provide a latitude and longitude")
        
        game_team = player.team

        now = datetime.now(tz=pytz.utc)
        time = (now - pytz.utc.localize(player.start_time)).total_seconds()
        
        guess = create_guess(lat, lng, user, round, time)
        
        team_state = DuelHp.query.filter_by(state_id=round.duels_state.id, team_id=game_team.id).first()
        if team_state.guess_id == None or guess.distance < team_state.guess.distance:
            team_state.guess_id = guess.id
            db.session.commit()
        
        socketio.emit("guess", {"user": user.username, "lat": lat, "lng": lng}, namespace="/socket/party", room=f"team_{game_team.hash}")
        socketio.emit("guess", {"user": user.username}, namespace="/socket/party", room=session.uuid)
        
        if Guess.query.filter_by(round_id=round.id).count() == 1 and guess.time + session.duel_rules.guess_time_limit < round.base_rules.time_limit:
            update_game_state({"state": GameState.RESULTS}, session, guess.time + session.duel_rules.guess_time_limit + 1)
            socketio.emit("time", {
                "time": now + timedelta(seconds=session.duel_rules.guess_time_limit),
                "time_limit": session.duel_rules.guess_time_limit,
                "now": now
            }, namespace="/socket/party", room=session.uuid)
            
        
        if Guess.query.filter_by(round_id=round.id).count() >= can_guess.count():
            stop_current_task(session)
            self.update_state({"state":GameState.RESULTS}, session)
            
    def can_guess(self,session):
        round = self.get_round_(session,session.current_round)
        return TeamPlayer.query.join(DuelHp, DuelHp.team_id == TeamPlayer.team_id).join(DuelState).filter(DuelState.round_id == round.id)
        
    def results(self,data,user,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.RESULTS:
            raise Exception("Game is in the wrong state")
        
        round = self.get_round_(session,session.current_round)
        prev_round = self.get_round_(session, session.current_round - 1) if session.current_round > 1 else None
        duels_state = round.duels_state

        ret = {
            "lat": round.location.latitude,
            "lng": round.location.longitude,
            "start_hp": session.duel_rules.start_hp,
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
                        "distance": guess.distance,
                        "time": guess.time,
                    } for guess in Guess.query.join(User).join(TeamPlayer, User.id == TeamPlayer.user_id).join(Round).filter(team.id == TeamPlayer.team_id, Round.id==round.id).order_by(Guess.distance)
                ]
            })        
        
        return ret
            
    def summary(self,data,user,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state.state != GameState.FINISHED:
            raise Exception("Game is in the wrong state")
        
        rounds = Round.query.filter_by(session_id=session.id).order_by(Round.round_number).all()
        
        ret = {
            "teams": [],
            "start_hp": session.duel_rules.start_hp,
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
                "team": team.to_json(),
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
                            "distance": guess.distance,
                            "time": guess.time,
                        } for guess in Guess.query.join(User).join(TeamPlayer, User.id == TeamPlayer.user_id).join(Round).filter(team.id == TeamPlayer.team_id,Round.id==round.id).order_by(Guess.distance)
                    ]
                })
            ret["teams"].append(team_data)
        return ret
    
    def get_state(self,data,user,session,called=False):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        ret = {"state":state.state}

        if state.state == GameState.GUESSING:
            round = self.get_round_(session,session.current_round)
            if timed_out(state.time,round.base_rules.time_limit) and not called:
                stop_current_task(session)
                self.update_state({"state":GameState.RESULTS}, session)
                return self.get_state(data,user,session,called=True)
            
            game_team = GameTeamLinker.query.filter(GameTeamLinker.session_id==session.id).join(GameTeam).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first() if user else None
            
            ret = {
                **ret,
                "round": round.round_number,
                "multi": round.duels_state.multi,
                "start_hp": session.duel_rules.start_hp,
                "teams": [
                    {
                        **team.to_json(),
                        "hp": hp.hp if hp else 0
                     } for team,hp in db.session.query(GameTeamLinker,DuelHp).filter_by(session_id=session.id).outerjoin(DuelHp, DuelHp.team_id == GameTeamLinker.team_id).filter(DuelHp.state_id == round.duels_state.id).order_by(DuelHp.hp.desc().nullslast())
                ],
            }
            
            if game_team:
                hp = DuelHp.query.filter_by(state_id=round.duels_state.id, team_id=game_team.team.id).first()
                ret = {
                    **ret,
                    "spectating": hp == None,
                    "can_guess": Guess.query.filter_by(round_id=round.id,user_id=user.id).count() == 0 and hp,
                    "team": game_team.team.uuid,
                }
                if hp:
                    ret = {
                        **ret,
                        "markers": [
                            {
                                "user": marker.user.username,
                                "lat": marker.latitude,
                                "lng": marker.longitude,
                            } for marker in PlayerPlonk.query.join(TeamPlayer, PlayerPlonk.user_id == TeamPlayer.user_id).filter(game_team.team.id == TeamPlayer.team_id, PlayerPlonk.round_id == round.id)
                        ],
                        "guesses": [
                            {
                                "user": guess.user.username,
                                "lat": guess.latitude,
                                "lng": guess.longitude,
                            } for guess in Guess.query.join(TeamPlayer,Guess.user_id == TeamPlayer.user_id).filter(game_team.team.id == TeamPlayer.team_id,Guess.round_id == round.id)
                        ],
                    }
            else:
                ret = {
                    **ret,
                    "spectating": True,
                    "can_guess": False,
                    "team": None,
                }
        
        elif state.state == GameState.RESULTS:
            if timed_out(state.time,5) and not called:
                stop_current_task(session)
                self.update_state({"state":GameState.GUESSING}, session)
                return self.get_state(data,user,session,called=True)
        
        return ret
    
    def plonk(self,data,user,session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if state["state"] != GameState.GUESSING:
            raise Exception("Game is in the wrong state")
        
        player = self.can_guess(session).filter(TeamPlayer.user_id == user.id).first()
        if not player:
            raise Exception("You are cannot guess")
        
        game_team = player.team
        
        lat = data.get("lat")
        lng = data.get("lng")
        if lat == None or lng == None:
            raise Exception("You must provide a latitude and longitude")
        
        round = self.get_round_(session,session.current_round)
        create_plonk(user, round, lat, lng)
        socketio.emit("plonk", {"user": user.username, "lat": lat, "lng":lng}, namespace="/socket/party", room=f"team_{game_team.hash}")

    def update_state(self, data, session):
        state = GameStateTracker.query.filter_by(session_id=session.id).first()
        if data.get("state") == GameState.RESULTS:
            if state.state == GameState.GUESSING:
                round = self.get_round_(session,session.current_round)
                first_guess = Guess.query.filter_by(round_id=round.id).order_by(Guess.time).first()
                time_limit = min(round.base_rules.time_limit, first_guess.time + session.duel_rules.guess_time_limit) if first_guess else round.base_rules.time_limit
                all_guessed = self.can_guess(session).count() >= Guess.query.filter_by(round_id=round.id).count()
                
                if timed_out(state.time, time_limit) or all_guessed:
                    if not all_guessed:
                        not_guessed = (db.session.query(PlayerPlonk, DuelHp)
                            .filter(PlayerPlonk.round_id == round.id)
                            .join(TeamPlayer, PlayerPlonk.user_id == TeamPlayer.user_id)
                            .join(DuelHp, DuelHp.team_id == TeamPlayer.team_id)
                            .filter(DuelHp.state_id == round.duels_state.id)
                            .outerjoin(Guess, Guess.user_id == PlayerPlonk.user_id)
                            .filter(Guess.id == None)
                        ).all()
                        
                        for plonk, team_state in not_guessed:
                            guess = create_guess(plonk.latitude, plonk.longitude, plonk.player.user, round, time_limit)
                            if team_state.guess_id == None or guess.distance < team_state.guess.distance:
                                team_state.guess_id = guess.id
                                            
                    highest_guess = Guess.query.filter_by(round_id=round.id).order_by(Guess.score.desc()).first()
                    highest_score = highest_guess.score if highest_guess else 0
                    multi = round.duels_state.multi
                    for hp in DuelHp.query.filter_by(state_id=round.duels_state.id).filter(DuelHp.hp > 0):
                        if hp.guess and hp.guess.score < highest_score:
                            guess_score = hp.guess.score if hp.guess else 0
                            hp.hp = max(0, hp.hp - ((highest_score - guess_score) * multi)//1)
                    db.session.commit()
                    self.change_state(session, GameState.RESULTS)
                    update_game_state({"state": GameState.GUESSING}, session, 5)
        elif data.get("state") == GameState.GUESSING:
            if state.state == GameState.RESULTS:
                self.next({}, None, session)
        
        
                
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
                "min": 0,
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
        
    def set_rules(self, party, data, configs=None):
        if not configs:
            configs = self.rules_config()
        super().set_rules(party, data)
        duel_rules = party.rules.duel_rules
        
        rule_names = ["hp","multi_start","multi_mult","multi_add","mult_freq","guess_time"]
        db_names = ["start_hp","damage_multi_start_round","damage_multi_mult","damage_multi_add","damage_multi_freq","guess_time_limit"]
        rules_default = [duel_rules.start_hp, duel_rules.damage_multi_start_round, duel_rules.damage_multi_mult, duel_rules.damage_multi_add, duel_rules.damage_multi_freq, duel_rules.guess_time_limit]
        values = {}
        for name,db_name,default in zip(rule_names, db_names, rules_default):
            values[db_name] = data.get(name, default)
            self.check_rule(configs[name], values[db_name])
        
        duel_rules = DuelRules.query.filter_by(**values).first()
        
        if not duel_rules:
            duel_rules = DuelRules(**values)
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
from flask_socketio import join_room
from api.game.games.basegame import BaseGame
from api.game.games.party_game import PartyGame
from api.game.gameutils import assign_teams
from models.configs import Configs
from models.db import db
from models.session import GameType, Session
from models.duels import DuelRules, DuelState, GameTeam, TeamPlayer, DuelHp, DuelRulesLinker
class DuelsGame(PartyGame):
    def create(self,data,user,party):
        rules = party.rules
        session = Session(host_id=user.id,type=GameType.DUELS,base_rule_id=rules.base_rule_id)
        db.session.add(session)
        db.session.flush()
        
        db.session.add(DuelRulesLinker(session_id=session.id,rules_id=rules.duel_rules.id))
        assign_teams(data.get("teams"),session,party)
        
        db.session.commit()
        return {"id":session.uuid},200,session

    def join(self,data,user,session):
        pass
    
    def next(self,data,user,session):
        pass
    
    def get_round(self,data,user,session):
        pass
    
    def guess(self,data,user,session):
        pass
    
    def results(self,data,user,session):
        pass
    
    def summary(self,data,user,session):
        pass
    
    def get_state(self,data,user,session):
        if session.current_round == 0:
            return {"state":"not started"}
        round = self.get_round_(session,session.current_round)
        
        state = DuelState.query.filter_by(round_id=round.id).first()
        
        if DuelHp.query.filter_by(state_id=state.id).count() == 0:
            return {"state":"playing","round": round.round_number}
        
        if DuelHp.query.filter_by(state_id=state.id, hp=0).count() == 0:
            return {"state":"finished"}
    
        return {"state":"results","round":round.round_number}
        
    
    def ping(self,data,user,session):
        pass
    
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
            "hp": duel_rules.start_hp,
            "multi_start": duel_rules.damage_multi_start_round,
            "multi_mult": duel_rules.damage_multi_mult,
            "multi_add": duel_rules.damage_multi_add,
            "mult_freq": duel_rules.damage_multi_freq,
            "guess_time": duel_rules.guess_time_limit,
        }
        
    def join_socket(self, session, user):
        super().join_socket(session, user)
        team = GameTeam.query.filter_by(session_id=session.id).join(TeamPlayer).filter(TeamPlayer.user_id == user.id).first()
        if team:
            join_room(f"team_{team.uuid}")
        else:
            join_room(f"spectator_{session.uuid}")
        
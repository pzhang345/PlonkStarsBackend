from datetime import datetime
from flask_socketio import join_room
import pytz
from sqlalchemy import func

from api.game.games.basegame import BaseGame
from fsocket import socketio
from models.db import db
from models.configs import Configs
from models.map import GameMap
from models.session import Session, BaseRules, GameStateTracker
from models.stats import MapStats


class PartyGame(BaseGame):
    def create(self, host, type, base_rules):
        session = Session(host_id=host.id, type=type, base_rule_id=base_rules.id)
        db.session.add(session)
        db.session.flush()
        db.session.add(GameStateTracker(session_id=session.id))
        db.session.commit()
        return session
    
    def change_state(self, session, state, time=None):
        game_state_tracker = GameStateTracker.query.filter_by(session_id=session.id).first()
        if not game_state_tracker:
            game_state_tracker = GameStateTracker(session_id=session.id)
            db.session.add(game_state_tracker)
        
        game_state_tracker.state = state
        game_state_tracker.time = time if time else datetime.now(tz=pytz.utc)
        db.session.commit()
        socketio.emit("next", {"state":state.name}, namespace="/socket/party", room=session.uuid)
        
    def update_state(self, data, session):
        pass
        
    def set_default_rules(self, party, data=None):
        type = party.rules.type
        prefix = type.name.upper() if Configs.in_(f"{type.name.upper()}_DEFAULT_ROUNDS") else "GAME"
        print(prefix)
        rounds = int(Configs.get(f"{prefix}_DEFAULT_ROUNDS"))
        time = int(Configs.get(f"{prefix}_DEFAULT_TIME_LIMIT"))
        nmpz = party.rules.base_rules.nmpz
        map_id = party.rules.base_rules.map_id
        
        base_rules = BaseRules.query.filter_by(
            map_id=map_id,
            time_limit=time,
            max_rounds=rounds,
            nmpz=nmpz
        ).first()
        
        if not base_rules:
            base_rules = BaseRules(
                map_id=map_id,
                time_limit=time,
                max_rounds=rounds,
                nmpz=nmpz
            )
            db.session.add(base_rules)
            db.session.flush()
        
        party.rules.base_rule_id = base_rules.id
        db.session.commit()
        
    def set_rules(self, party, data, configs=None):
        map = GameMap.query.filter_by(uuid=data.get("map_id")).first()        
        base_rules = party.rules.base_rules
        map_id = map.id if map else base_rules.map_id
        if map and map.total_weight <= 0:
            raise Exception("Map has no locations")
        
        if not configs:
            configs = self.rules_config()
        
        rule_names = ["time","rounds","nmpz"]
        db_names = ["time_limit","max_rounds","nmpz"]
        rules_default = [base_rules.time_limit, base_rules.max_rounds, base_rules.nmpz]
        values = self.check_rules(data, configs, rule_names, db_names, rules_default)
        
        base_rule = BaseRules.query.filter_by(map_id=map_id, **values).first()
        if not base_rule:
            base_rule = BaseRules(map_id=map_id, **values)
            db.session.add(base_rule)
            db.session.flush()
        
        party.rules.base_rule_id = base_rule.id
        db.session.commit()
        
    def get_rules(self, party, data):
        rules = party.rules.base_rules
        map,score,guess = (db.session.query(
            GameMap,
            func.sum(MapStats.total_score).label("total_score"),
            func.sum(MapStats.total_guesses).label("total_guesses"),
        )
        .outerjoin(MapStats, GameMap.id == MapStats.map_id)
        ).group_by(GameMap.id).filter(GameMap.id == rules.map_id).first()
        return {
            "map": {
                "name": map.name,
                "id": map.uuid,
                "creator": map.creator.username,
                "average_score": float(score / guess) if guess != None or guess == 0 else 0,
                "average_generation_time": float(map.generation.total_generation_time / map.generation.total_loads) if map.generation != None and map.generation.total_loads != 0 else 0,
                "total_guesses": float(guess) if guess != None else 0,
            },
            "rounds": rules.max_rounds,
            "time": rules.time_limit,
            "type": party.rules.type.name,
            "nmpz": rules.nmpz,
            "team_type": None
        }
        
    def join_socket(self,session,user):
        join_room(session.uuid)
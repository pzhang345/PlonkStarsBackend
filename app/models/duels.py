import uuid
from models.db import db

class DuelsRules(db.Model):
    __tablename__ = "duels_rules"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    
    start_hp = db.Column(db.Integer, nullable=False, default=5000)
    
    damage_multi_start_round = db.Column(db.Integer, nullable=False, default=1)
    damage_multi_mult = db.Column(db.Float, nullable=False, default=1)
    damage_multi_add = db.Column(db.Float, nullable=False, default=0)
    damage_multi_freq = db.Column(db.Integer, nullable=False, default=1)
    
    guess_time_limit = db.Column(db.Integer, nullable=False, default=15)

class DuelState(db.Model):
    __tablename__ = "duel_state"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    multi = db.Column(db.Float, nullable=False, default=1)
    
    team_hps = db.relationship("DuelHp", backref="state", cascade="all,delete", passive_deletes=True)

class GameTeam(db.Model):
    __tablename__ = "game_teams"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    
    color = db.Column(db.Integer, nullable=False, default=0)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    
    team_players = db.relationship("TeamPlayer", backref="team", cascade="all,delete", passive_deletes=True)
    round_hps = db.relationship("DuelHp", backref="team", cascade="all,delete", passive_deletes=True)
    
class TeamPlayer(db.Model):
    __tablename__ = "team_players"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    team_id = db.Column(db.Integer, db.ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
class DuelHp(db.Model):
    __tablename__ = "duel_hp"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    state_id = db.Column(db.Integer, db.ForeignKey("duel_state.id", ondelete="CASCADE"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    hp = db.Column(db.Integer, nullable=False)

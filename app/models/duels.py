from datetime import datetime
import uuid

import pytz
from sqlalchemy import Column, DateTime, Double, Float, ForeignKey, Integer, String, UniqueConstraint
from models.db import db

class DuelRules(db.Model):
    __tablename__ = "duel_rules"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    start_hp = Column(Integer, nullable=False, default=5000)
    
    damage_multi_start_round = Column(Integer, nullable=False, default=1)
    damage_multi_mult = Column(Float, nullable=False, default=1)
    damage_multi_add = Column(Float, nullable=False, default=0)
    damage_multi_freq = Column(Integer, nullable=False, default=1)
    
    guess_time_limit = Column(Integer, nullable=False, default=15)
    
    linker = db.relationship("DuelRulesLinker", backref="rules", cascade="all,delete", passive_deletes=True)
    party_rules = db.relationship("PartyRules", backref="duel_rules", cascade="all,delete", passive_deletes=True)
    
    __table_args__ = (
        UniqueConstraint('start_hp', 'damage_multi_start_round', 'damage_multi_mult', 'damage_multi_add', 'damage_multi_freq', 'guess_time_limit'),
    )

class DuelRulesLinker(db.Model):
    __tablename__ = "duel_rules_linker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    rules_id = Column(Integer, ForeignKey("duel_rules.id", ondelete="CASCADE"), nullable=False)

class DuelState(db.Model):
    __tablename__ = "duel_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    round_id = Column(Integer, ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False, unique=True)
    multi = Column(Float, nullable=False, default=1)
    
    team_hps = db.relationship("DuelHp", backref="state", cascade="all,delete", passive_deletes=True)

class GameTeamLinker(db.Model):
    __tablename__ = "game_team_linker"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    team_id = Column(Integer, ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(64), nullable=False, default="")
    uuid = Column(String(36), nullable=False, default=lambda: str(uuid.uuid4()))
    color = Column(Integer, nullable=False, default=0)
    
    def to_json(self):
        return {
            **self.team.to_json(),
            "id": self.uuid,
            "color": self.color,
        }
    

class GameTeam(db.Model):
    __tablename__ = "game_teams"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hash = Column(String(50), nullable=False, unique=True)
        
    session_team = db.relationship("GameTeamLinker", backref="team", cascade="all,delete", passive_deletes=True)
    party_team = db.relationship("PartyTeam", backref="team", cascade="all,delete", passive_deletes=True)
    players = db.relationship("TeamPlayer", backref="team", cascade="all,delete", passive_deletes=True)
    round_hps = db.relationship("DuelHp", backref="team", cascade="all,delete", passive_deletes=True)
    
    def to_json(self):
        return {
            "members": [player.user.username for player in self.team_players],
        }
    
class TeamPlayer(db.Model):
    __tablename__ = "team_players"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('team_id', 'user_id'),
    )
    
class DuelHp(db.Model):
    __tablename__ = "duel_hp"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guess_id = Column(Integer, ForeignKey("guesses.id", ondelete="CASCADE"))
    state_id = Column(Integer, ForeignKey("duel_state.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    hp = Column(Integer, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('state_id', 'team_id'),
    )
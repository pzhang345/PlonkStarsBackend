from datetime import datetime
import enum
import uuid
import pytz
from sqlalchemy import Boolean, Column, DateTime, Double, Enum, ForeignKey, Integer, String, UniqueConstraint

from models.db import db

class GameType(enum.Enum):
    CHALLENGE = 0
    LIVE = 1
    DUELS = 2
    
class Session(db.Model):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True)

    current_round = Column(Integer, nullable=False, default=0)
    host_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(GameType), nullable=False, default=GameType.CHALLENGE)
    base_rule_id = Column(Integer, ForeignKey("base_rules.id", ondelete="CASCADE"), nullable=False)
    
    rounds = db.relationship("Round", backref="session", cascade="all,delete", passive_deletes=True)
    players = db.relationship("Player",backref="session",cascade="all,delete", passive_deletes=True)
    round_tracker = db.relationship("RoundStats",backref="session",cascade="all,delete", passive_deletes=True)
    high_scores = db.relationship("UserMapStats",backref="high_session",cascade="all,delete", passive_deletes=True)
    daily_challenge = db.relationship("DailyChallenge",backref="session",cascade="all,delete", passive_deletes=True, uselist=False)
    party = db.relationship("Party", backref="session", passive_deletes=True, uselist=False)
    teams = db.relationship("GameTeam", backref="session", cascade="all,delete", passive_deletes=True)
    duel_rules_link = db.relationship("DuelRulesLinker", backref="session", uselist=False, cascade="all, delete-orphan")
    duel_rules = db.relationship("DuelRules", secondary="duel_rules_linker", uselist=False, viewonly=True)
    
    def __str__(self):
        return self.uuid


class BaseRules(db.Model):
    __tablename__ = "base_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time_limit = Column(Integer, nullable=False, default=-1)
    max_rounds = Column(Integer, nullable=False, default=-1)
    nmpz = Column(Boolean, nullable=False, default=False)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    
    sessions = db.relationship("Session", backref="base_rules", cascade="all,delete", passive_deletes=True)
    party_rules = db.relationship("PartyRules", backref="base_rules", cascade="all,delete", passive_deletes=True)
    rounds = db.relationship("Round", backref="base_rules", cascade="all,delete", passive_deletes=True)
    
    __table_args__ = (
        UniqueConstraint('map_id', 'time_limit', 'max_rounds', 'nmpz'),
    )

    def __str__(self):
        return f"Rounds:{self.max_rounds} Time:{self.time_limit} NMPZ:{self.nmpz} Map:{self.map}"

class Round(db.Model):
    __tablename__= "rounds"

    id = Column(Integer, primary_key=True, autoincrement=True)

    location_id = Column(Integer, ForeignKey("svlocations.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    base_rule_id = Column(Integer, ForeignKey("base_rules.id", ondelete="CASCADE"), nullable=False)

    guesses = db.relationship("Guess", backref="round", cascade="all,delete", passive_deletes=True)
    duel_state = db.relationship("DuelState", backref="round", cascade="all,delete", passive_deletes=True, uselist=False)
    
    __table_args__ = (
        UniqueConstraint('session_id', 'round_number'),
    )

    def __str__(self):
        return f"{self.round_number}. {self.session.uuid[:4]} {self.location}"

    
class Player(db.Model):
    __tablename__= "players"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer,ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    current_round = Column(Integer, nullable=False, default=0)
    start_time = Column(DateTime, nullable=False,default=lambda: datetime.now(tz=pytz.utc))
    
    __table_args__ = (
        UniqueConstraint('user_id', 'session_id'),
    )
    
class Guess(db.Model):
    __tablename__ = "guesses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(Integer, ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)

    latitude = Column(Double, nullable=False)
    longitude = Column(Double, nullable=False)

    distance = Column(Double,nullable=False)
    score = Column(Integer, nullable=False)
    time = Column(Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'round_id'),
    )

    def __str__(self):
        return f"({self.latitude},{self.longitude})"
    
    duels_high_guess = db.relationship("DuelHp", backref="guess", cascade="all,delete", passive_deletes=True)

class DailyChallenge(db.Model):
    __tablename__ = "daily_challenge"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    date = Column(db.Date, nullable=False, unique=True, default=datetime.now(tz=pytz.utc).date())
    coins_added = Column(Boolean, nullable=False,default=False)


    def __str__(self):
        return f"{self.date} {self.map.name}"
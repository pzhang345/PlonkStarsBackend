from datetime import datetime
import enum
import uuid
import pytz

from models.db import db

class GameType(enum.Enum):
    CHALLENGE = 0
    LIVE = 1
    
class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    max_rounds = db.Column(db.Integer, nullable=False, default=-1)
    current_round = db.Column(db.Integer, nullable=False, default=0)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)
    type = db.Column(db.Enum(GameType), nullable=False, default=GameType.CHALLENGE)
    nmpz = db.Column(db.Boolean, nullable=False, default=False)
    
    rounds = db.relationship("Round", backref="session", cascade="all,delete", passive_deletes=True)
    players = db.relationship("Player",backref="session",cascade="all,delete", passive_deletes=True)
    round_tracker = db.relationship("RoundStats",backref="session",cascade="all,delete", passive_deletes=True)
    high_scores = db.relationship("UserMapStats",backref="high_session",cascade="all,delete", passive_deletes=True)
    daily_challenge = db.relationship("DailyChallenge",backref="session",cascade="all,delete", passive_deletes=True)
    party = db.relationship("Party", backref="session", passive_deletes=True, uselist=False)
    
    def __str__(self):
        return self.uuid


class Round(db.Model):
    __tablename__= "rounds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    location_id = db.Column(db.Integer, db.ForeignKey("svlocations.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)
    nmpz = db.Column(db.Boolean, nullable=False, default=False)

    guesses = db.relationship("Guess", backref="round", cascade="all,delete", passive_deletes=True)

    def __str__(self):
        return f"{self.round_number}. {self.session.uuid[:4]} {self.location}"

    
class Player(db.Model):
    __tablename__= "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    current_round = db.Column(db.Integer, nullable=False, default=0)
    start_time = db.Column(db.DateTime, nullable=False,default=datetime.now(tz=pytz.utc))
    
class Guess(db.Model):
    __tablename__ = "guesses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)

    latitude = db.Column(db.Double, nullable=False)
    longitude = db.Column(db.Double, nullable=False)

    distance = db.Column(db.Double,nullable=False)
    score = db.Column(db.Integer, nullable=False)
    time = db.Column(db.Integer, nullable=False, default=0)

    def __str__(self):
        return f"({self.latitude},{self.longitude})"

class DailyChallenge(db.Model):
    __tablename__ = "daily_challenge"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    date = db.Column(db.Date, nullable=False, unique=True, default=datetime.now(tz=pytz.utc).date())

    def __str__(self):
        return f"{self.date} {self.map.name}"
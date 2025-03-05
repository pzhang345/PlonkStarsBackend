from flask_sqlalchemy import SQLAlchemy
import uuid
from datetime import datetime
import pytz
import enum

db = SQLAlchemy()

class GameType(enum.Enum):
    CHALLENGE = 0
    LIVE = 1
    
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    guess = db.relationship("Guess", backref="user", cascade="all,delete")
    sessions = db.relationship("Session",backref="host",cascade="all,delete")
    maps = db.relationship("GameMap",backref="creator",cascade="all,delete")
    player = db.relationship("Player",backref="user",cascade="all,delete")
    round_stats = db.relationship("RoundStats",backref="user",cascade="all,delete")


    def __str__(self):
        return self.username

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.username,
        }

class Guess(db.Model):
    __tablename__ = "guesses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)

    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)

    distance = db.Column(db.Numeric(10, 3),nullable=False)
    score = db.Column(db.Integer, nullable=False)
    time = db.Column(db.Integer, nullable=False, default=0)

    def __str__(self):
        return f"({self.latitude},{self.longitude})"


class SVLocation(db.Model):
    __tablename__ = "svlocations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)

    rounds = db.relationship("Round", backref="location", cascade="all,delete")

    def __str__(self):
        return f"({self.latitude},{self.longitude})"

############################################################################################
#   Sessions                                                                               #
############################################################################################
class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    max_rounds = db.Column(db.Integer, nullable=False, default=-1)
    current_round = db.Column(db.Integer, nullable=False, default=0)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id"), nullable=False)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)
    type = db.Column(db.Enum(GameType), nullable=False, default=GameType.CHALLENGE)
    
    rounds = db.relationship("Round", backref="session", cascade="all,delete")
    players = db.relationship("Player",backref="session",cascade="all,delete")
    round_tracker = db.relationship("RoundStats",backref="session",cascade="all,delete")

    def __str__(self):
        return self.uuid


class Round(db.Model):
    __tablename__= "rounds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    location_id = db.Column(db.Integer, db.ForeignKey("svlocations.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)

    guesses = db.relationship("Guess", backref="round", cascade="all,delete")

    def __str__(self):
        return f"{self.round_number}. {self.session.uuid[:4]} {self.location}"

    
class Player(db.Model):
    __tablename__= "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id"), nullable=False)
    current_round = db.Column(db.Integer, nullable=False, default=0)
    start_time = db.Column(db.DateTime, nullable=False,default=datetime.now(tz=pytz.utc))

class RoundStats(db.Model):
    __tablename__ = "roundstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Numeric(12, 3), nullable=False, default=0)

############################################################################################
#   MAP                                                                                    #
############################################################################################
class GameMap(db.Model):
    __tablename__="maps"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    name = db.Column(db.String(150), nullable=False)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    start_latitude = db.Column(db.Numeric(10, 7), nullable=False,default=-1)
    start_longitude = db.Column(db.Numeric(10, 7), nullable=False,default=-1)
    end_latitude = db.Column(db.Numeric(10, 7), nullable=False,default=-1)
    end_longitude = db.Column(db.Numeric(10, 7), nullable=False,default=-1)
    
    total_weight = db.Column(db.Integer, nullable=False, default=0)
    max_distance = db.Column(db.Numeric(10, 3), nullable=False,default=-1)
    
    map_bounds = db.relationship("MapBound", backref="map", cascade="all,delete")
    sessions = db.relationship("Session", backref="map", cascade="all,delete")
    stats = db.relationship('MapStats', backref='map', uselist=False)
    
    def __str__(self):
        return self.name

class MapStats(db.Model):
    __tablename__="mapstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id"), nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    total_guesses = db.Column(db.Integer, nullable=False, default=0)
    
    total_generation_time = db.Column(db.Integer, nullable=False, default=0)
    total_loads = db.Column(db.Integer, nullable=False, default=0)
    
class Bound(db.Model):
    __tablename__="bounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    start_latitude = db.Column(db.Numeric(10, 7), nullable=False)
    start_longitude = db.Column(db.Numeric(10, 7), nullable=False)
    end_latitude = db.Column(db.Numeric(10, 7), nullable=False)
    end_longitude = db.Column(db.Numeric(10, 7), nullable=False)
    
    map_bounds = db.relationship("MapBound", backref="bound", cascade="all,delete")
    
    def __str__(self):
        return f"({self.start_latitude},{self.start_longitude})-({self.end_latitude},{self.end_longitude})"
    
    def to_dict(self):
        return {
            "start":(self.start_latitude,self.start_longitude),
            "end":(self.end_latitude,self.end_longitude)
        }

class MapBound(db.Model):
    __tablename__="mapbounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    bound_id = db.Column(db.Integer, db.ForeignKey("bounds.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id"), nullable=False)
    weight = db.Column(db.Integer, nullable=False)
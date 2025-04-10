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
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(70), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    guess = db.relationship("Guess", backref="user", cascade="all,delete", passive_deletes=True)
    sessions = db.relationship("Session",backref="host",cascade="all,delete", passive_deletes=True)
    maps = db.relationship("GameMap",backref="creator",cascade="all,delete", passive_deletes=True)
    player = db.relationship("Player",backref="user",cascade="all,delete", passive_deletes=True)
    round_stats = db.relationship("RoundStats",backref="user",cascade="all,delete", passive_deletes=True)
    user_map_stats = db.relationship("UserMapStats",backref="user",cascade="all,delete", passive_deletes=True)


    def __str__(self):
        return self.username

    def to_json(self):
        return {
            "username": self.username,
        }

class UserMapStats(db.Model):
    __tablename__ = "usermapstats"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Double, nullable=False, default=0)
    total_guesses = db.Column(db.Integer, nullable=False, default=0)
    nmpz=db.Column(db.Boolean, nullable=False, default=False)

    high_average_score = db.Column(db.Float, nullable=False, default=0)
    high_average_distance = db.Column(db.Double, nullable=False, default=0)
    high_average_time = db.Column(db.Float, nullable=False, default=0)
    high_round_number = db.Column(db.Integer, nullable=False, default=0)
    high_session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))

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
    
    def to_json(self):
        return {
            "id": self.id,
            "user": self.user.to_json(),
            "session_id": self.round.session_id,
            "round_number": self.round.round_number,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "correct_lat": self.round.location.latitude,
            "correct_lng": self.round.location.longitude,
            "distance": self.distance,
            "score": self.score,
            "time": self.time
        }


class SVLocation(db.Model):
    __tablename__ = "svlocations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    latitude = db.Column(db.Double, nullable=False)
    longitude = db.Column(db.Double, nullable=False)

    rounds = db.relationship("Round", backref="location", cascade="all,delete", passive_deletes=True)

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
    host_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)
    type = db.Column(db.Enum(GameType), nullable=False, default=GameType.CHALLENGE)
    nmpz = db.Column(db.Boolean, nullable=False, default=False)
    
    rounds = db.relationship("Round", backref="session", cascade="all,delete", passive_deletes=True)
    players = db.relationship("Player",backref="session",cascade="all,delete", passive_deletes=True)
    round_tracker = db.relationship("RoundStats",backref="session",cascade="all,delete", passive_deletes=True)
    high_scores = db.relationship("UserMapStats",backref="high_session",cascade="all,delete", passive_deletes=True)
    
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

class RoundStats(db.Model):
    __tablename__ = "roundstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Double, nullable=False, default=0)

############################################################################################
#   MAP                                                                                    #
############################################################################################
class GameMap(db.Model):
    __tablename__="maps"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    description = db.Column(db.String(512))
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    start_latitude = db.Column(db.Double, nullable=False,default=-1)
    start_longitude = db.Column(db.Double, nullable=False,default=-1)
    end_latitude = db.Column(db.Double, nullable=False,default=-1)
    end_longitude = db.Column(db.Double, nullable=False,default=-1)
    
    total_weight = db.Column(db.Integer, nullable=False, default=0)
    max_distance = db.Column(db.Double, nullable=False,default=-1)
    
    map_bounds = db.relationship("MapBound", backref="map", cascade="all,delete", passive_deletes=True)
    sessions = db.relationship("Session", backref="map", cascade="all,delete", passive_deletes=True)
    stats = db.relationship("MapStats", backref="map", uselist=False, passive_deletes=True)
    user_map_stats = db.relationship("UserMapStats",backref="map",cascade="all,delete", passive_deletes=True)
    
    def __str__(self):
        return self.name
    
    def to_json(self):
        return {
            "name":self.name,
            "id":self.uuid, 
            "creator":self.creator.to_json(),
            "average_score":self.stats.total_score/self.stats.total_guesses if self.stats.total_guesses != 0 else 0,
            "average_generation_time": self.stats.total_generation_time/self.stats.total_loads if self.stats.total_loads != 0 else 0,
            "total_guesses": self.stats.total_guesses,
        }

class MapStats(db.Model):
    __tablename__="mapstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Double, nullable=False, default=0)
    total_guesses = db.Column(db.Integer, nullable=False, default=0)
    
    total_generation_time = db.Column(db.Integer, nullable=False, default=0)
    total_loads = db.Column(db.Integer, nullable=False, default=0)
    
class Bound(db.Model):
    __tablename__="bounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    start_latitude = db.Column(db.Double, nullable=False)
    start_longitude = db.Column(db.Double, nullable=False)
    end_latitude = db.Column(db.Double, nullable=False)
    end_longitude = db.Column(db.Double, nullable=False)
    
    map_bounds = db.relationship("MapBound", backref="bound", cascade="all,delete", passive_deletes=True)
    
    def __str__(self):
        return f"({self.start_latitude},{self.start_longitude})-({self.end_latitude},{self.end_longitude})"
    
    def to_json(self):
        if self.start_latitude == self.end_latitude and self.start_longitude == self.end_longitude:
            return {
                "lat":self.start_latitude,
                "lng":self.start_longitude
            }
        else:
            return {
                "start":{"lat":self.start_latitude,"lng":self.start_longitude},
                "end":{"lat":self.end_latitude,"lng":self.end_longitude}
            }

class MapBound(db.Model):
    __tablename__="mapbounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    bound_id = db.Column(db.Integer, db.ForeignKey("bounds.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    weight = db.Column(db.Integer, nullable=False)
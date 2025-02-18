from flask_sqlalchemy import SQLAlchemy
import uuid
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    guess = db.relationship("Guess", backref="user", cascade="all,delete")
    sessions = db.relationship("Session",backref="host",cascade="all,delete")
    maps = db.relationship("GameMap",backref="creator",cascade="all,delete")

    def __str__(self):
        return self.username


class Guess(db.Model):
    __tablename__ = "guesses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)

    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)

    distance = db.Column(db.Numeric(10, 3),nullable=False)
    score = db.Column(db.Integer, nullable=False)

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

    current_round = db.Column(db.Integer, default=0, nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id"), nullable=False)
    
    rounds = db.relationship("Round", backref="session", cascade="all,delete")
    players = db.relationship("Player",backref="session",cascade="all,delete")

    def __str__(self):
        return self.uuid


class Round(db.Model):
    __tablename__= "rounds"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)

    location_id = db.Column(db.Integer, db.ForeignKey("svlocations.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)

    guesses = db.relationship("Guess", backref="round", cascade="all,delete")

    def __str__(self):
        return str(self.location)
    
class Player(db.Model):
    __tablename__= "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id"), nullable=False)

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
    
    def __str__(self):
        return self.name
    

class Bound(db.Model):
    __tablename__="bounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    start_latitude = db.Column(db.Numeric(10, 7), nullable=False)
    start_longitude = db.Column(db.Numeric(10, 7), nullable=False)
    end_latitude = db.Column(db.Numeric(10, 7), nullable=False)
    end_longitude = db.Column(db.Numeric(10, 7), nullable=False)
    
    map_bounds = db.relationship("MapBound", backref="bound", cascade="all,delete")
    
    def __str__(self):
        return f'({self.start_latitude},{self.start_longitude})-({self.end_latitude},{self.end_longitude})'

class MapBound(db.Model):
    __tablename__="mapbounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    bound_id = db.Column(db.Integer, db.ForeignKey("bounds.id"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id"), nullable=False)
    weight = db.Column(db.Integer, nullable=False)
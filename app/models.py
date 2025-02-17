from flask_sqlalchemy import SQLAlchemy
import uuid
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "Users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    guess = db.relationship("Guess", backref="user", cascade="all,delete")
    maps = db.relationship("Session",backref="creator",cascade="all,delete")

class Guess(db.Model):
    __tablename__ = "Guesses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("Rounds.id"), nullable=False)

    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    score = db.Column(db.Integer, nullable=False)

    round = db.relationship("Round", backref="guess", cascade="all,delete")

class SVLocation(db.Model):
    __tablename__ = "SVLocations"

    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)


class Session(db.Model):
    __tablename__ = "Sessions"

    id = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True, primary_key=True)

    current_round = db.Column(db.Integer, default=0, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=False)

    rounds = db.relationship("Round", backref="session", cascade="all,delete")
    players = db.relationship("Player",backref="session",cascade="all,delete")


class Round(db.Model):
    __tablename__= "Rounds"

    id = db.Column(db.Integer, primary_key=True)

    location_id = db.Column(db.Integer, db.ForeignKey("SVLocations.id"), nullable=False)
    session_id = db.Column(db.String(36), db.ForeignKey("Sessions.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)

class Player(db.Model):
    __tablename__= "Players"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=False)
    session_id = db.Column(db.String(36),db.ForeignKey("Sessions.id"), nullable=False)
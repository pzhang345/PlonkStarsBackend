from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'Users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

    guess = db.relationship('Guess', backref='user', cascade="all, delete")

class Guess(db.Model):
    __tablename__ = 'Guesses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey('Rounds.id'), nullable=False)

    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    score = db.Column(db.Integer, nullable=False)

    round = db.relationship('Round', backref='guess', cascade="all, delete")

class SVLocation(db.Model):
    __tablename__ = 'SVLocations'

    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)


class Session(db.Model):
    __tablename__ = "Sessions"

    id = db.Column(db.Integer, primary_key=True)

    rounds = db.relationship('Round', backref='session', cascade="all, delete")


class Round(db.Model):
    __tablename__= 'Rounds'

    id = db.Column(db.Integer, primary_key=True)

    location_id = db.Column(db.Integer, db.ForeignKey('SVLocations.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('Sessions.id'), nullable=False)
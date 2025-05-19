from sqlalchemy import UniqueConstraint
from models.db import db

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
    
    __table_args__ = (
        UniqueConstraint('user_id', 'map_id', 'nmpz'),
    )
    
class MapStats(db.Model):
    __tablename__="mapstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    nmpz = db.Column(db.Boolean, nullable=False, default=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Double, nullable=False, default=0)
    total_guesses = db.Column(db.Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('map_id', 'nmpz'),
    )

class RoundStats(db.Model):
    __tablename__ = "roundstats"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.Integer,db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    total_time = db.Column(db.Integer, nullable=False, default=0)
    total_score = db.Column(db.Integer, nullable=False, default=0)
    total_distance = db.Column(db.Double, nullable=False, default=0)
    
    
    __table_args__ = (
        UniqueConstraint('user_id', 'session_id', 'round'),
    )
    

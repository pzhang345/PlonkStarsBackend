from sqlalchemy import Boolean, Column, Double, Float, ForeignKey, Integer, UniqueConstraint
from models.db import db

class UserMapStats(db.Model):
    __tablename__ = "usermapstats"
    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    total_time = Column(Integer, nullable=False, default=0)
    total_score = Column(Integer, nullable=False, default=0)
    total_distance = Column(Double, nullable=False, default=0)
    total_guesses = Column(Integer, nullable=False, default=0)
    nmpz=Column(Boolean, nullable=False, default=False)

    high_average_score = Column(Float, nullable=False, default=0)
    high_average_distance = Column(Double, nullable=False, default=0)
    high_average_time = Column(Float, nullable=False, default=0)
    high_round_number = Column(Integer, nullable=False, default=0)
    high_session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"))
    
    __table_args__ = (
        UniqueConstraint('user_id', 'map_id', 'nmpz'),
    )
    
class MapStats(db.Model):
    __tablename__="mapstats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    nmpz = Column(Boolean, nullable=False, default=False)
    total_time = Column(Integer, nullable=False, default=0)
    total_score = Column(Integer, nullable=False, default=0)
    total_distance = Column(Double, nullable=False, default=0)
    total_guesses = Column(Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('map_id', 'nmpz'),
    )

class RoundStats(db.Model):
    __tablename__ = "roundstats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer,ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round = Column(Integer, nullable=False)
    total_time = Column(Integer, nullable=False, default=0)
    total_score = Column(Integer, nullable=False, default=0)
    total_distance = Column(Double, nullable=False, default=0)
    
    
    __table_args__ = (
        UniqueConstraint('user_id', 'session_id', 'round'),
    )
    

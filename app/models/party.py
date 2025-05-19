from datetime import datetime

import pytz
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from models.db import db

from models.session import GameType
from utils import generate_code

class Party(db.Model):
    __tablename__ = "party"
    
    id = Column(Integer, primary_key=True)
    code = Column(String(4), unique=True, nullable=False, default=lambda: generate_code(Party))
    session_id = Column(Integer, ForeignKey("sessions.id"))
    host_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_activity = Column(DateTime, nullable=False, default=lambda: datetime.now(tz=pytz.utc))
    
    members = db.relationship("PartyMember", backref="party", cascade="all,delete", passive_deletes=True)
    rules = db.relationship("PartyRules", backref="party", cascade="all,delete", passive_deletes=True, uselist=False)

    def __str__(self):
        return f"{self.host}'s party ({self.code})"

class PartyMember(db.Model):
    __tablename__ = "party_members"
    
    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("party.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    in_lobby = Column(Boolean, nullable=False, default=True)
    
    __table_args__ = (
        UniqueConstraint('party_id', 'user_id'),
    )
    
    def __str__(self):
        return f"{self.party} member ({self.user})"

class PartyRules(db.Model):
    __tablename__ = "party_rules"
    
    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("party.id", ondelete="CASCADE"), nullable=False, unique=True)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    max_rounds = Column(Integer, nullable=False, default=-1)
    time_limit = Column(Integer, nullable=False, default=-1)
    type = Column(Enum(GameType), nullable=False, default=GameType.LIVE)
    nmpz = Column(Boolean, nullable=False, default=False)
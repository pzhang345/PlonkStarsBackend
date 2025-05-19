from datetime import datetime

import pytz
from sqlalchemy import UniqueConstraint
from models.db import db

from models.session import GameType
from utils import generate_code

class Party(db.Model):
    __tablename__ = "party"
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(4), unique=True, nullable=False, default=lambda: generate_code(Party))
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"))
    host_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_activity = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(tz=pytz.utc))
    
    members = db.relationship("PartyMember", backref="party", cascade="all,delete", passive_deletes=True)
    rules = db.relationship("PartyRules", backref="party", cascade="all,delete", passive_deletes=True, uselist=False)

    def __str__(self):
        return f"{self.host}'s party ({self.code})"

class PartyMember(db.Model):
    __tablename__ = "party_members"
    
    id = db.Column(db.Integer, primary_key=True)
    party_id = db.Column(db.Integer, db.ForeignKey("party.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    in_lobby = db.Column(db.Boolean, nullable=False, default=True)
    
    __table_args__ = (
        UniqueConstraint('party_id', 'user_id'),
    )
    
    def __str__(self):
        return f"{self.party} member ({self.user})"

class PartyRules(db.Model):
    __tablename__ = "party_rules"
    
    id = db.Column(db.Integer, primary_key=True)
    party_id = db.Column(db.Integer, db.ForeignKey("party.id", ondelete="CASCADE"), nullable=False, unique=True)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    max_rounds = db.Column(db.Integer, nullable=False, default=-1)
    time_limit = db.Column(db.Integer, nullable=False, default=-1)
    type = db.Column(db.Enum(GameType), nullable=False, default=GameType.LIVE)
    nmpz = db.Column(db.Boolean, nullable=False, default=False)
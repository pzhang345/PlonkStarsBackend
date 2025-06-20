from datetime import datetime
import random
import uuid

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
    teams = db.relationship("PartyTeam", backref="party", cascade="all,delete", passive_deletes=True)

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
    type = Column(Enum(GameType), nullable=False, default=GameType.LIVE)
    base_rule_id = Column(Integer, ForeignKey("base_rules.id", ondelete="CASCADE"),nullable=False)
    duel_rules_id = Column(Integer, ForeignKey("duel_rules.id", ondelete="CASCADE"),nullable=False)
    
class PartyTeam(db.Model):
    __tablename__ = "party_teams"
    
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True)
    party_id = Column(Integer, ForeignKey("party.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False)
    leader_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    color = Column(Integer, nullable=False, default=lambda: random.randint(0,255 * 255 * 255))

    __table_args__ = (
        UniqueConstraint('party_id', 'color'),
        UniqueConstraint('party_id', 'team_id'),
        UniqueConstraint('party_id', 'leader_id')
    )
    
    def to_json(self):
        return {
            "team_leader": self.leader.username,
            "color": self.color,
            "uuid": self.team_id,
            "members": [member.user.username for member in self.team.players]
        }
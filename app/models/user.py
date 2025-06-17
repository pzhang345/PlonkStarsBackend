from sqlalchemy import Boolean, Column, Integer, String

from models.db import db

class User(db.Model):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(70), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)

    guess = db.relationship("Guess", backref="user", cascade="all,delete", passive_deletes=True)
    sessions = db.relationship("Session",backref="host",cascade="all,delete", passive_deletes=True)
    maps = db.relationship("GameMap",backref="creator",cascade="all,delete", passive_deletes=True)
    player = db.relationship("Player",backref="user",cascade="all,delete", passive_deletes=True)
    round_stats = db.relationship("RoundStats",backref="user",cascade="all,delete", passive_deletes=True)
    user_map_stats = db.relationship("UserMapStats",backref="user",cascade="all,delete", passive_deletes=True)
    can_edit = db.relationship("MapEditor",backref="user",cascade="all,delete", passive_deletes=True)
    cosmetics = db.relationship("UserCosmetics", backref="user", cascade="all,delete", uselist=False, passive_deletes=True)
    parties = db.relationship("Party", backref="host", cascade="all,delete", passive_deletes=True)
    party_member = db.relationship("PartyMember", backref="user", cascade="all,delete", passive_deletes=True)
    cosmetics_items = db.relationship("CosmeticsOwnership", backref="user", cascade="all, delete", passive_deletes=True)
    coins = db.relationship("UserCoins", backref="user", cascade="all, delete",uselist=False, passive_deletes=True)
    team_players = db.relationship("TeamPlayer", backref="user", cascade="all, delete", passive_deletes=True)
    party_leader = db.relationship("PartyTeams", backref="leader", cascade="all, delete", passive_deletes=True)

    def __str__(self):
        return self.username

    def to_json(self):
        return {
            "username": self.username,
            "user_cosmetics": self.cosmetics.to_json() if self.cosmetics else None,
        }
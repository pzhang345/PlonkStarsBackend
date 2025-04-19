from random import randint
from models.db import db

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
    can_edit = db.relationship("MapEditor",backref="user",cascade="all,delete", passive_deletes=True)
    cosmetics = db.relationship("UserCosmetics", backref="user", cascade="all,delete", uselist=False, passive_deletes=True)

    def __str__(self):
        return self.username

    def to_json(self):
        return {
            "username": self.username,
            "user_cosmetics": self.cosmetics.to_json() if self.cosmetics else None,
        }
    
class UserCosmetics(db.Model):
    __tablename__ = "user_cosmetics"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hue = db.Column(db.Integer, nullable=False, default=randint(0, 360))
    saturation = db.Column(db.Integer, nullable=False, default=randint(90, 150))
    brightness = db.Column(db.Integer, nullable=False, default=randint(90, 150))

    def __str__(self):
        return f"UserCosmetics({self.user_id}, {self.cosmetics})"
    
    def to_json(self):
        return {
            "hue": self.hue,
            "saturation": self.saturation,
            "brightness": self.brightness
        }
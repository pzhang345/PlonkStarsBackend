from random import randint
from models.db import db
import enum
from sqlalchemy import Enum as SQLEnum

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
    parties = db.relationship("Party", backref="host", cascade="all,delete", passive_deletes=True)
    party_member = db.relationship("PartyMember", backref="user", cascade="all,delete", passive_deletes=True)

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

    hue = db.Column(db.Integer, nullable=False, default=lambda: randint(0, 360))
    saturation = db.Column(db.Integer, nullable=False, default=lambda: randint(90, 150))
    brightness = db.Column(db.Integer, nullable=False, default=lambda: randint(90, 150))

    # Cosmetics equipped (foreign key by unique image string)
    # TODO: should be string (image name) instead of int
    face = db.Column(db.String(50), db.ForeignKey("cosmetics.image", ondelete="CASCADE"), nullable=True, default=None)
    body = db.Column(db.String(50), db.ForeignKey("cosmetics.image", ondelete="CASCADE"), nullable=True, default=None)
    hat = db.Column(db.String(50), db.ForeignKey("cosmetics.image", ondelete="CASCADE"), nullable=True, default=None)

    face_obj = db.relationship("Cosmetics", foreign_keys=[face], primaryjoin="UserCosmetics.face==Cosmetics.image", backref="face_users")
    body_obj = db.relationship("Cosmetics", foreign_keys=[body], primaryjoin="UserCosmetics.body==Cosmetics.image", backref="body_users")
    hat_obj = db.relationship("Cosmetics", foreign_keys=[hat], primaryjoin="UserCosmetics.hat==Cosmetics.image", backref="hat_users")

    def __str__(self):
        return f"UserCosmetics(user_id={self.user_id}, face='{self.face}', body='{self.body}', hat='{self.hat}')"

    def to_json(self):
        return {
            "hue": self.hue,
            "saturation": self.saturation,
            "brightness": self.brightness,
            "face": self.face_obj.to_json() if self.face_obj else None,
            "body": self.body_obj.to_json() if self.body_obj else None,
            "hat": self.hat_obj.to_json() if self.hat_obj else None,
    }

    
class Tier(enum.Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"

class Cosmetic_Type(enum.Enum):
    FACE = "face"
    BODY = "body"
    HAT = "hat"
    
class Cosmetics(db.Model):
    __tablename__ = "cosmetics"

    image = db.Column(db.String(50), primary_key=True, unique=True, nullable=False)
    item_name = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(SQLEnum(Cosmetic_Type), nullable=False)
    tier = db.Column(SQLEnum(Tier), nullable=False, default=Tier.COMMON)
    top_position = db.Column(db.Float, nullable=False, default=0)
    left_position = db.Column(db.Float, nullable=False, default=0)
    scale = db.Column(db.Float, nullable=False, default=0)

    # Added relationship
    ownerships = db.relationship("CosmeticsOwnership", backref="cosmetic", cascade="all, delete", passive_deletes=True)

    def __str__(self):
        return self.image

    def to_json(self):
        return {
            "item_name": self.item_name,
            "tier": self.tier.value,
            "type": self.type.value,
            "image": self.image,
            "top_position": self.top_position,
            "left_position": self.left_position,
            "scale": self.scale
        }
    
class CosmeticsOwnership(db.Model):
    __tablename__ = "cosmetics_ownership"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cosmetics_image = db.Column(db.String(50), db.ForeignKey("cosmetics.image", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'cosmetics_image', name='uix_user_cosmetic_pair'),
    )

    user = db.relationship("User", backref=db.backref("owned_cosmetics", cascade="all, delete", passive_deletes=True))

    def to_json(self):
        return {
            "user_id": self.user_id,
            "cosmetics_image": self.cosmetics_image,
            "cosmetic": self.cosmetic.to_json() if self.cosmetic else None,
            "user": {
                "id": self.user.id,
                "username": self.user.username
            } if self.user else None
        }

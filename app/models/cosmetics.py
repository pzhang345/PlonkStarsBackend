from sqlalchemy import CheckConstraint
from models.db import db
import enum
from random import randint

class UserCosmetics(db.Model):
    __tablename__ = "user_cosmetics"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    hue = db.Column(db.Integer, nullable=False, default=lambda: randint(0, 360))
    saturation = db.Column(db.Integer, nullable=False, default=lambda: randint(90, 150))
    brightness = db.Column(db.Integer, nullable=False, default=lambda: randint(90, 150))

    face_id = db.Column(db.Integer, db.ForeignKey("cosmetics.id", ondelete="CASCADE"), default=None)
    body_id = db.Column(db.Integer, db.ForeignKey("cosmetics.id", ondelete="CASCADE"), default=None)
    hat_id = db.Column(db.Integer, db.ForeignKey("cosmetics.id", ondelete="CASCADE"), default=None)

    def __str__(self):
        return f"UserCosmetics(user_id={self.user_id}, face='{self.face.image}', body='{self.body.image}', hat='{self.hat.image}')"

    def to_json(self):
        return {
            "hue": self.hue,
            "saturation": self.saturation,
            "brightness": self.brightness,
            "face": self.face.to_json() if self.face else None,
            "body": self.body.to_json() if self.body else None,
            "hat": self.hat.to_json() if self.hat else None,
    }

    
class Tier(enum.Enum):
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4
    
    def from_str(str):
        strings = {"common": Tier.COMMON, "uncommon": Tier.UNCOMMON, "rare": Tier.RARE, "epic": Tier.EPIC, "legendary": Tier.LEGENDARY}
        return strings[str.lower()] if str and str.lower() in strings else None

class Cosmetic_Type(enum.Enum):
    FACE = 0
    BODY = 1
    HAT = 2
    
class Cosmetics(db.Model):
    __tablename__ = "cosmetics"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    image = db.Column(db.String(50), unique=True, nullable=False)
    item_name = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.Enum(Cosmetic_Type), nullable=False)
    tier = db.Column(db.Enum(Tier), nullable=False, default=Tier.COMMON)
    top_position = db.Column(db.Float, nullable=False, default=0)
    left_position = db.Column(db.Float, nullable=False, default=0)
    scale = db.Column(db.Float, nullable=False, default=0)

    # Added relationship
    ownerships = db.relationship("CosmeticsOwnership", backref="cosmetic", cascade="all, delete", passive_deletes=True)
    face_obj = db.relationship("UserCosmetics", foreign_keys="[UserCosmetics.face_id]", backref="face", cascade="all, delete", passive_deletes=True)
    body_obj = db.relationship("UserCosmetics", foreign_keys="[UserCosmetics.body_id]", backref="body", cascade="all, delete", passive_deletes=True)
    hat_obj = db.relationship("UserCosmetics", foreign_keys="[UserCosmetics.hat_id]", backref="hat", cascade="all, delete", passive_deletes=True)

    def __str__(self):
        return self.image

    def to_json(self):
        return {
            "item_name": self.item_name,
            "tier": self.tier.name,
            "type": self.type.name,
            "image": self.image,
            "top_position": self.top_position,
            "left_position": self.left_position,
            "scale": self.scale
        }
    
class CosmeticsOwnership(db.Model):
    __tablename__ = "cosmetics_ownership"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cosmetics_id = db.Column(db.Integer, db.ForeignKey("cosmetics.id", ondelete="CASCADE"), nullable=False)

    def to_json(self):
        return {
            "cosmetics_image": self.cosmetics.image,
            "cosmetic": self.cosmetic.to_json() if self.cosmetic else None,
            "user": {
                "username": self.user.username
            } if self.user else None
        }

class UserCoins(db.Model):
    __tablename__ = "user_coins"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    coins = db.Column(db.Integer, nullable = False, default = 0)

    __table_args__ = (
        CheckConstraint('coins >= 0', name='check_coins_positive'),
    )

    def __str__(self):
        return f'Coins: {self.coins}'

    def to_json(self):
        return {
            "coins": self.coins,
        }
import uuid
from models.db import db
from models.cosmetics import Tier

class Crate(db.Model):
    __tablename__ = "crates"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)    
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(200), nullable=False, default="")
    image = db.Column(db.String(50))
    price = db.Column(db.Integer, nullable=False)
    total_weight = db.Column(db.Integer, nullable=False, default=0)
    
    items = db.relationship("CrateItem", backref="crate", cascade="all, delete", passive_deletes=True)

    def __str__(self):
        return self.name
    
class CrateItem(db.Model):
    __tablename__ = "crate_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    crate_id = db.Column(db.Integer, db.ForeignKey("crates.id", ondelete="CASCADE"), nullable=False)
    tier = db.Column(db.Enum(Tier), nullable=False)
    weight = db.Column(db.Integer, nullable=False)
    
    def __str__(self):
        return f"{self.crate.name} item ({self.tier.name})"
from sqlalchemy import Column, Enum, ForeignKey, Integer, String, UniqueConstraint
from models.db import db
from models.cosmetics import Tier

class Crate(db.Model):
    __tablename__ = "crates"

    id = Column(Integer, primary_key=True, autoincrement=True)    
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(200), nullable=False, default="")
    image = Column(String(50))
    price = Column(Integer, nullable=False)
    total_weight = Column(Integer, nullable=False, default=0)
    
    items = db.relationship("CrateItem", backref="crate", cascade="all, delete", passive_deletes=True)

    def __str__(self):
        return self.name
    
class CrateItem(db.Model):
    __tablename__ = "crate_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    crate_id = Column(Integer, ForeignKey("crates.id", ondelete="CASCADE"), nullable=False)
    tier = Column(Enum(Tier), nullable=False)
    weight = Column(Integer, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('crate_id', 'tier'),
    )
    
    def __str__(self):
        return f"{self.crate.name} item ({self.tier.name})"
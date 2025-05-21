import uuid

from sqlalchemy import Column, Double, ForeignKey, Integer, String, UniqueConstraint

from models.db import db

class GameMap(db.Model):
    __tablename__="maps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True)
    description = Column(String(512))
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    start_latitude = Column(Double, nullable=False,default=-1)
    start_longitude = Column(Double, nullable=False,default=-1)
    end_latitude = Column(Double, nullable=False,default=-1)
    end_longitude = Column(Double, nullable=False,default=-1)
    
    total_weight = Column(Integer, nullable=False, default=0)
    max_distance = Column(Double, nullable=False,default=-1)
    
    map_bounds = db.relationship("MapBound", backref="map", cascade="all,delete", passive_deletes=True)
    stats = db.relationship("MapStats", backref="map", cascade="all,delete", passive_deletes=True)
    user_map_stats = db.relationship("UserMapStats",backref="map",cascade="all,delete", passive_deletes=True)
    editors = db.relationship("MapEditor", backref="map", cascade="all,delete", passive_deletes=True)
    generation = db.relationship("GenerationTime", backref="map", cascade="all,delete", uselist=False, passive_deletes=True)
    rules = db.relationship("BaseRules", backref="map", cascade="all,delete", passive_deletes=True)
    
    def __str__(self):
        return self.name
    
    def to_json(self):
        return {
            "id":self.id,
            "name":self.name,
            "uuid":self.uuid,
            "description":self.description,
            "creator_id":self.creator_id,
        }
    
class Bound(db.Model):
    __tablename__="bounds"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    start_latitude = Column(Double, nullable=False)
    start_longitude = Column(Double, nullable=False)
    end_latitude = Column(Double, nullable=False)
    end_longitude = Column(Double, nullable=False)
    
    map_bounds = db.relationship("MapBound", backref="bound", cascade="all,delete", passive_deletes=True)
    
    __table_args__ = (
        UniqueConstraint('start_latitude', 'start_longitude', 'end_latitude', 'end_longitude'),
    )
    
    def __str__(self):
        return f"({self.start_latitude},{self.start_longitude})-({self.end_latitude},{self.end_longitude})"
    
    def to_json(self):
        if self.start_latitude == self.end_latitude and self.start_longitude == self.end_longitude:
            return {
                "lat":self.start_latitude,
                "lng":self.start_longitude
            }
        else:
            return {
                "start":{"lat":self.start_latitude,"lng":self.start_longitude},
                "end":{"lat":self.end_latitude,"lng":self.end_longitude}
            }

class MapBound(db.Model):
    __tablename__="mapbounds"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    bound_id = Column(Integer, ForeignKey("bounds.id", ondelete="CASCADE"), nullable=False)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Integer, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('bound_id', 'map_id'),
    )
    
class MapEditor(db.Model):
    __tablename__="mapeditors"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    permission_level = Column(Integer, nullable=False, default=0)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'map_id'),
    )
    
class GenerationTime(db.Model):
    __tablename__="generationtimes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    map_id = Column(Integer, ForeignKey("maps.id", ondelete="CASCADE"), nullable=False, unique=True)
    total_generation_time = Column(Integer, nullable=False, default=0)
    total_loads = Column(Integer, nullable=False, default=0)
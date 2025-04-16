import uuid

from models.db import db

class GameMap(db.Model):
    __tablename__="maps"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), unique=True)
    description = db.Column(db.String(512))
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    start_latitude = db.Column(db.Double, nullable=False,default=-1)
    start_longitude = db.Column(db.Double, nullable=False,default=-1)
    end_latitude = db.Column(db.Double, nullable=False,default=-1)
    end_longitude = db.Column(db.Double, nullable=False,default=-1)
    
    total_weight = db.Column(db.Integer, nullable=False, default=0)
    max_distance = db.Column(db.Double, nullable=False,default=-1)
    
    map_bounds = db.relationship("MapBound", backref="map", cascade="all,delete", passive_deletes=True)
    sessions = db.relationship("Session", backref="map", cascade="all,delete", passive_deletes=True)
    stats = db.relationship("MapStats", backref="map", cascade="all,delete", uselist=False, passive_deletes=True)
    user_map_stats = db.relationship("UserMapStats",backref="map",cascade="all,delete", passive_deletes=True)
    editors = db.relationship("MapEditor", backref="map", cascade="all,delete", passive_deletes=True)
    generation = db.relationship("GenerationTime", backref="map", cascade="all,delete", uselist=False, passive_deletes=True)
    
    def __str__(self):
        return self.name
    
    def to_json(self):
        return {
            "name":self.name,
            "id":self.uuid, 
            "creator":self.creator.to_json(),
            "average_score":self.stats.total_score/self.stats.total_guesses if self.stats.total_guesses != 0 else 0,
            "average_generation_time": self.generation.total_generation_time/self.generation.total_loads if self.stats.total_loads != 0 else 0,
            "total_guesses": self.stats.total_guesses,
        }
    
class Bound(db.Model):
    __tablename__="bounds"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    start_latitude = db.Column(db.Double, nullable=False)
    start_longitude = db.Column(db.Double, nullable=False)
    end_latitude = db.Column(db.Double, nullable=False)
    end_longitude = db.Column(db.Double, nullable=False)
    
    map_bounds = db.relationship("MapBound", backref="bound", cascade="all,delete", passive_deletes=True)
    
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
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    bound_id = db.Column(db.Integer, db.ForeignKey("bounds.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    weight = db.Column(db.Integer, nullable=False)
    
class MapEditor(db.Model):
    __tablename__="mapeditors"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    
class GenerationTime(db.Model):
    __tablename__="generationtimes"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    map_id = db.Column(db.Integer, db.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    total_generation_time = db.Column(db.Integer, nullable=False, default=0)
    total_loads = db.Column(db.Integer, nullable=False, default=0)
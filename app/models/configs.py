from sqlalchemy import Column, Integer, String

from models.db import db

class Configs(db.Model):
    __tablename__ = "configs"
    id = Column(Integer,primary_key=True)
    key = Column(String(50),unique=True, nullable=False)
    value = Column(String(50),nullable=False)

    def __str__(self):
        return f"{self.key}:{self.value}"
    
    def to_json(self):
        return {
            "key":self.key,
            "value":self.value
        }
        
    def get(key):
        config = Configs.query.filter_by(key=str(key)).first()
        if not config:
            return None
        return config.value
from models.db import db

class Configs(db.Model):
    __tablename__ = "configs"
    id = db.Column(db.Integer,primary_key=True)
    key = db.Column(db.String(50),unique=True, nullable=False)
    value = db.Column(db.String(50),nullable=False)

    def __str__(self):
        return f"{self.key}:{self.value}"
    
    def to_json(self):
        return {
            "key":self.key,
            "value":self.value
        }
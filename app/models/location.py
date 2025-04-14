from models.db import db


class SVLocation(db.Model):
    __tablename__ = "svlocations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    latitude = db.Column(db.Double, nullable=False)
    longitude = db.Column(db.Double, nullable=False)

    rounds = db.relationship("Round", backref="location", cascade="all,delete", passive_deletes=True)

    def __str__(self):
        return f"({self.latitude},{self.longitude})"
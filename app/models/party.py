from models.db import db

from utils import generate_code

class Party(db.Model):
    __tablename__ = "party"
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(4), unique=True, nullable=False, default=lambda: generate_code(Party))
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"))
    host_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    members = db.relationship("PartyMember", backref="party", cascade="all,delete", passive_deletes=True)

    def __str__(self):
        return f"<Party {self.host}>"

class PartyMember(db.Model):
    __tablename__ = "party_members"
    
    id = db.Column(db.Integer, primary_key=True)
    sid = db.Column(db.String(36), nullable=False)
    party_id = db.Column(db.Integer, db.ForeignKey("party.id", ondelete="CASCASE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCASE"), nullable=False)

    def __str__(self):
        return f"<PartyMember {self.user} in {self.party.host}>"

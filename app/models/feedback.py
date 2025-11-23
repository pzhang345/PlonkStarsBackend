from datetime import datetime
import pytz
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from models.db import db

class Feedback(db.Model):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(String(2048), nullable=False)
    sent = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime, nullable=False,default=lambda: datetime.now(tz=pytz.utc))
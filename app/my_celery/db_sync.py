import threading
import redis
from config import Config
from models.db import db

redis_instance = redis.from_url(Config.REDIS_URL)
def start_sync_db(app):
    def sync_db():
        pubsub = redis_instance.pubsub()
        pubsub.subscribe("db_changes")
        for message in pubsub.listen():
            if message["type"] == "message":
                with app.app_context():
                    db.session.expire_all()
    t = threading.Thread(target=sync_db, daemon=True)
    t.start()
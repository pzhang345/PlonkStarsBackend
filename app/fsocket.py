from flask_socketio import SocketIO
from config import Config

redis_ssl_url = Config.REDIS_URL + "/0?ssl_cert_reqs=none" if Config.REDIS_URL.startswith("rediss://") else Config.REDIS_URL
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=redis_ssl_url
)
from flask_socketio import SocketIO
from config import Config
    
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=Config.REDIS_URL,
)

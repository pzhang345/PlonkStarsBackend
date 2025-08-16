from flask_socketio import SocketIO
from config import Config
import ssl
    
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=Config.REDIS_URL,
    ssl_cert_reqs=ssl.CERT_NONE
)

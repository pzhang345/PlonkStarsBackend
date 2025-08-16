from flask_socketio import SocketIO
from config import Config
import ssl
    
socketio = SocketIO(
    cors_allowed_origins="*",
)

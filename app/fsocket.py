from flask_socketio import SocketIO
from config import Config

args = {}
if Config.REDIS_URL.startswith("rediss://"):
    import ssl
    args["ssl_cert_reqs"] = ssl.CERT_NONE
    
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=Config.REDIS_URL,
    **args
)

from flask_socketio import SocketIO
from config import Config

args = {}
if Config.REDIS_URL.startswith("rediss://"):
    import ssl
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    args["ssl"] = ssl_ctx
    args["ssl_cert_reqs"] = ssl.CERT_NONE
    
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=Config.REDIS_URL,
    **args
)

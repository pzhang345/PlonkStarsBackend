import eventlet
eventlet.monkey_patch(socket=True)

from flask import Flask
from flask_migrate import Migrate
from flask_cors import CORS

from fsocket import socketio
from api.routes import api_bp
from api.socket import register_sockets
from base_celery import init_celery

from cli.cli import register_commands

from admin import admin
from models.db import db
from config import Config

app = Flask(__name__)
CORS(app, cors_allow_origins="*")

app.config.from_object(Config)

db.init_app(app)
with app.app_context():
    db.create_all()
migrate = Migrate(app, db,directory=app.config["MIGRATION_DIR"])


init_celery(app)
admin.init_app(app)
socketio.init_app(app)
app.register_blueprint(api_bp, url_prefix="/api")
register_sockets(socketio)
register_commands(app)

if __name__ == "__main__":
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

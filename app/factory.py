"""Flask application factory.

This module intentionally does NOT import eventlet or monkey-patch anything -
that must happen (if at all) before this module is imported, at the real
process entrypoint (app/app.py) or not at all (tests).

All process-wide singletons (db, mail, socketio, celery, admin) live in their
own modules and are configured here against a single Flask app instance.
Each optional piece of wiring is gated behind a Config feature flag so tests
can build a minimal app without touching Celery/Redis/SMTP/Admin.
"""

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from api.routes import api_bp
from api.socket import register_sockets
from cli.cli import register_commands
from config import Config
from fsocket import socketio
from mail.mail import mail
from models.db import db
from my_celery.base_celery import init_celery


def create_app(config_object=Config):
    app = Flask(__name__)
    CORS(app, cors_allow_origins="*")

    app.config.from_object(config_object)

    db.init_app(app)
    if app.config.get("AUTO_CREATE_ALL", True):
        with app.app_context():
            db.create_all()

    Migrate(app, db, directory=app.config["MIGRATION_DIR"])

    if app.config.get("ENABLE_CELERY", True):
        init_celery(app)

    if app.config.get("ENABLE_MAIL", True):
        mail.init_app(app)

    if app.config.get("ENABLE_ADMIN", True):
        # Imported lazily: importing admin.py has side effects (it iterates
        # db.Model.__subclasses__() and builds a global Admin singleton at
        # import time), so tests that disable ENABLE_ADMIN must never trigger
        # this import.
        from admin import admin

        admin.init_app(app)

    if app.config.get("ENABLE_SOCKETIO", True):
        # LANDMINE: fsocket.py constructs `socketio` at import time via
        # SocketIO(message_queue=...). flask_socketio's __init__ treats a
        # present `message_queue` kwarg as a signal to call init_app()
        # immediately, which builds and stores a RedisManager under
        # socketio.server_options["client_manager"]. On a *second* init_app
        # call (here), flask_socketio only rebuilds client_manager when the
        # newly-passed message_queue is truthy - if it's None/falsy it just
        # reuses the stale one. That means passing message_queue=None would
        # silently keep talking to Redis instead of falling back to an
        # in-memory manager. Popping it first forces a clean rebuild from
        # whatever message_queue we pass now.
        socketio.server_options.pop("client_manager", None)
        socketio.init_app(app, message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"))
        register_sockets(socketio)

    app.register_blueprint(api_bp, url_prefix="/api")

    if app.config.get("REGISTER_CLI", True):
        register_commands(app)

    return app

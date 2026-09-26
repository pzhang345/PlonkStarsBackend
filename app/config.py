from pathlib import Path

from dotenv import load_dotenv
import os

# Resolve relative to this file so imports work regardless of the process cwd
# (previously a relative path that only resolved when cwd was `app/`).
load_dotenv(Path(__file__).resolve().parent / ".env.local")


def _database_uri():
    explicit = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if explicit:
        return explicit
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url.replace("postgres://", "postgresql://")
    return None


class Config:
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MIGRATION_DIR = ".migrations"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
    # redis.from_url() (called at import time in my_celery/db_sync.py) needs a
    # valid-looking URL even when Redis isn't actually available/used; it does
    # not connect eagerly, so a placeholder is safe here.
    REDIS_URL = os.environ.get("REDIS_URL") or "redis://localhost:6379"
    REDIS_SSL_URL = REDIS_URL + "/0?ssl_cert_reqs=CERT_NONE" if REDIS_URL.startswith("rediss://") else REDIS_URL

    EMAILS = os.environ.get("EMAILS").split(",") if os.environ.get("EMAILS") else []
    MAIL_SERVER = os.environ.get("MAILGUN_SMTP_SERVER") if os.environ.get("MAILGUN_SMTP_SERVER") else "localhost"
    MAIL_PORT = int(os.environ.get("MAILGUN_SMTP_PORT")) if os.environ.get("MAILGUN_SMTP_PORT") else 8025
    MAIL_USERNAME = os.environ.get("MAILGUN_SMTP_LOGIN")
    MAIL_PASSWORD = os.environ.get("MAILGUN_SMTP_PASSWORD")
    MAIL_USE_TLS = True if MAIL_SERVER != "localhost" else False
    MAIL_USE_SSL = False

    # Feature flags used by the app factory (app/factory.py) to make each
    # piece of wiring optional. Defaults preserve current production behavior.
    ENABLE_CELERY = True
    ENABLE_ADMIN = True
    ENABLE_SOCKETIO = True
    ENABLE_MAIL = True
    AUTO_CREATE_ALL = True
    REGISTER_CLI = True

    SOCKETIO_MESSAGE_QUEUE = REDIS_SSL_URL

    if os.environ.get("DOCKER_CONTAINER") == "true" and SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("localhost", "host.docker.internal")

# Running a local SMTP server for testing purposes
# python -m smtpd -c DebuggingServer -n localhost:8025

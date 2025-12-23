from dotenv import load_dotenv
import os

load_dotenv(".env.local")
class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI") if os.environ.get("SQLALCHEMY_DATABASE_URI") else os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MIGRATION_DIR=".migrations"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
    REDIS_URL = os.environ.get("REDIS_URL")
    REDIS_SSL_URL = REDIS_URL + "/0?ssl_cert_reqs=CERT_NONE" if REDIS_URL.startswith("rediss://") else REDIS_URL

    EMAILS = os.environ.get("EMAILS").split(",") if os.environ.get("EMAILS") else []
    MAIL_SERVER = os.environ.get("MAILGUN_SMTP_SERVER") if os.environ.get("MAILGUN_SMTP_SERVER") else "localhost"
    MAIL_PORT = int(os.environ.get("MAILGUN_SMTP_PORT")) if os.environ.get("MAILGUN_SMTP_PORT") else 8025
    MAIL_USERNAME = os.environ.get("MAILGUN_SMTP_LOGIN")
    MAIL_PASSWORD = os.environ.get("MAILGUN_SMTP_PASSWORD")
    MAIL_USE_TLS = True if MAIL_SERVER != "localhost" else False
    MAIL_USE_SSL = False
    
    
    if os.environ.get("DOCKER_CONTAINER") == "true":
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("localhost", "host.docker.internal")
        
# Running a local SMTP server for testing purposes
# python -m smtpd -c DebuggingServer -n localhost:8025

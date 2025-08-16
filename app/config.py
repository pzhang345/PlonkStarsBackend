from dotenv import load_dotenv
import os

load_dotenv(".env.local")
class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI") if os.environ.get("SQLALCHEMY_DATABASE_URI") else os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MIGRATION_DIR=".migrations"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
    REDIS_URL = os.environ.get("REDIS_URL") + "/0"
    REDIS_URL_WITH_EXTENSION = REDIS_URL + "/0?ssl_cert_reqs=CERT_NONE" if REDIS_URL.startswith("rediss://") else REDIS_URL
    
    if os.environ.get("DOCKER_CONTAINER") == "true":
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("localhost", "host.docker.internal")
        
from dotenv import load_dotenv
import os

load_dotenv(".env.local")
class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI") if os.environ.get("SQLALCHEMY_DATABASE_URI") else os.environ.get("DATABASE_URL").replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MIGRATION_DIR=".migrations"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
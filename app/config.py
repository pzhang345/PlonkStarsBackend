import os

class Config:
    SECRET_KEY = 'RICE_LOVER'  # Flask's secret key used for JWT signing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///users.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = 'RICE_LOVER_JWT'
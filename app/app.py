# app.py

from flask import Flask
from flask_migrate import Migrate
from config import Config
from api.auth.account import account_bp
from models.db import db
# from api.user import user_bp

app = Flask(__name__)

# Load configuration from config.py
app.config.from_object(Config)

# Initialize the database
db.init_app(app)
migrate = Migrate(app, db)

# Register the blueprints
app.register_blueprint(account_bp, url_prefix='/api/account')
# app.register_blueprint(user_bp, url_prefix='/api/user')

# Start the app
if __name__ == '__main__':
    app.run(debug=True)

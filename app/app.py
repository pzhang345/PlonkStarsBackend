from flask import Flask
from flask_migrate import Migrate

from api.auth.routes import account_bp
from api.game.routes import game_bp
from api.map.routes import map_bp

from admin import admin
from models import db
from fsocket import socketio
from config import Config

app = Flask(__name__)

app.config.from_object(Config)

db.init_app(app)
with app.app_context():
    db.create_all()

socketio.init_app(app)
admin.init_app(app)


migrate = Migrate(app, db,directory=app.config["MIGRATION_DIR"])

app.register_blueprint(account_bp, url_prefix='/api/account')
app.register_blueprint(game_bp, url_prefix='/api/game')
app.register_blueprint(map_bp, url_prefix='/api/map')

if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask
from flask_migrate import Migrate
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin
from flask_socketio import SocketIO

from api.auth.routes import account_bp
from api.location.routes import location_bp
from api.game.routes import game_bp
from models import db,User,SVLocation,Guess,Session,Round
from api.auth.socket import socketio
from config import Config

app = Flask(__name__)

app.config.from_object(Config)

db.init_app(app)
socketio.init_app(app)

migrate = Migrate(app, db)

app.register_blueprint(account_bp, url_prefix='/api/account')
app.register_blueprint(location_bp, url_prefix='/api/location')
app.register_blueprint(game_bp, url_prefix='/api/game')

admin = Admin(app, name='My Admin Panel', template_mode='bootstrap4')
admin.add_view(ModelView(User,db.session))
admin.add_view(ModelView(SVLocation,db.session))
admin.add_view(ModelView(Guess,db.session))
admin.add_view(ModelView(Session,db.session))
admin.add_view(ModelView(Round,db.session))

if __name__ == '__main__':
    app.run(debug=True)

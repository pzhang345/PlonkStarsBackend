from flask import Flask
from flask_migrate import Migrate
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin

from api.auth.account import account_bp
from api.location.location import location_bp
from models import db,User,Coordinate
from config import Config

app = Flask(__name__)

app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)

app.register_blueprint(account_bp, url_prefix='/api/account')
app.register_blueprint(location_bp, url_prefix='/api/location')

admin = Admin(app, name='My Admin Panel', template_mode='bootstrap4')
admin.add_view(ModelView(User,db.session))
admin.add_view(ModelView(Coordinate,db.session))

if __name__ == '__main__':
    app.run(debug=True)

from flask import Blueprint

from api.account.routes import account_bp
from api.game.routes import game_bp
from api.map.routes import map_bp
from api.session.routes import session_bp
from api.admin.routes import admin_bp
from api.party.routes import party_bp
from api.cosmetics.routes import cosmetics_bp
from api.time.routes import time_bp

api_bp = Blueprint("api", __name__)

api_bp.register_blueprint(account_bp, url_prefix="/account")
api_bp.register_blueprint(game_bp, url_prefix="/game")
api_bp.register_blueprint(map_bp, url_prefix="/map")
api_bp.register_blueprint(session_bp, url_prefix="/session")
api_bp.register_blueprint(admin_bp, url_prefix="/admin")
api_bp.register_blueprint(party_bp, url_prefix="/party")
api_bp.register_blueprint(cosmetics_bp, url_prefix="/cosmetics")
api_bp.register_blueprint(time_bp, url_prefix="/time")
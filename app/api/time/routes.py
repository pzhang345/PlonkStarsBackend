from flask import Blueprint, jsonify
from datetime import datetime

import pytz

time_bp = Blueprint("time_bp", __name__)

@time_bp.route("", methods=["GET"])
def get_time():
    current_time = datetime.now(tz=pytz.utc)
    return jsonify({"time": current_time}), 200
from flask import Blueprint,jsonify,request
from api.auth.auth import login_required

game_bp = Blueprint("game",__name__)

@game_bp.route("/start",methods=["GET"])
@login_required
def start_game(current_user):
    session_id = 0

    return jsonify({"error":"Not done","session":session_id}),404

@game_bp.route("/join",methods=["POST"])
@login_required
def join_game(current_user):
    data = request.json()
    session_id = data["session_id"]

    return jsonify({"error":"Not done"}),404

@game_bp.route("/guess",methods=["POST"])
@login_required
def submit_guess(current_user):
    data = request.json()
    session_id = data["session_id"]
    lat,lng = data["lat"],data["lng"]
    user_id = current_user.id


    return jsonify({"error":"Not done"}),404

@game_bp.route("/summary",methods=["GET"])
@login_required
def summary(current_user):
    data = request.json()
    session_id = data["session_id"]
    
    return jsonify({"error":"Not done"}),404


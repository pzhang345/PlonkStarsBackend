from flask import Blueprint,jsonify,request
from api.location.generate import generate_location
from api.auth.auth import login_required
from models import db,Session,Round,GameMap
from api.game.guess import add_guess

game_bp = Blueprint("game",__name__)

@game_bp.route("/create",methods=["POST"])
@login_required
def create_game(user):
    data = request.get_json()
    map = data.get("map")
    if not map:
        map = GameMap.query.first_or_404()
    else:
        query = GameMap.query
        map_name = map.get("name")
        if map_name:
            query.filter_by(name=map_name)
        
        map_id = map.get("id")
        if map_id:
            query.filter_by(uuid=map_id)
        
        map_creator = map.get("creator")
        if map_creator:
            query.filter_by(uuid=map_creator)
        map = query.first_or_404()
        
    session = Session(host_id=user.id,map_id=map.id)
    db.session.add(session)
    db.session.commit()
    return jsonify({"session":session.uuid}),200

@game_bp.route("/join",methods=["POST"])
@login_required
def join_game(user):
    session_id = request.get_json().get("id")

    session = Session.query.filter_by(uuid=session_id).first_or_404()

    return jsonify({"error":"Not done"}),404

@game_bp.route("/next",methods=["POST"])
@login_required
def next_round(user):
    session_id = request.get_json().get("id")
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    if session.host_id != user.id:
        return jsonify({"error":"access denied"}),403

    map = session.map
    location = generate_location(map)
    round = Round(
        location_id=location.id,
        session_id=session.id,
        round_number=session.current_round + 1
    )
    session.current_round = session.current_round + 1

    db.session.add(round)
    db.session.commit()

    return jsonify({
        "round_id":round.uuid,
        "lat":location.latitude,
        "lng":location.longitude
    }),200



@game_bp.route("/guess",methods=["POST"])
@login_required
def submit_guess(user):
    data = request.get_json()
    round_id = data.get("round_id")
    lat,lng = data.get("lat"),data.get("lng")
    user_id = user.id

    try:
        guess = add_guess(user_id,lat,lng,round_id)
        return jsonify({
            "distance":guess.distance,
            "score": guess.score
        }),200
    except Exception as e:
        return jsonify({"error":str(e)}),400

@game_bp.route("/end",methods=["GET"])
@login_required
def summary(user):
    data = request.get_json()
    session_id = data.get("session_id")

    return jsonify({"error":"Not done"}),404


from flask import Blueprint,jsonify,request
from api.game.game import create_round,find_map, add_guess
from api.auth.auth import login_required
from models import db,Session,Round,GameMap, Player
from datetime import datetime,timedelta

game_bp = Blueprint("game",__name__)

@game_bp.route("/create",methods=["POST"])
@login_required
def create_game(user):
    if request.is_json:
        data = request.get_json()
    else:
        data = {}
    
    map_data = data.get("map")
    time_limit = data.get("time") if data.get("time") else -1
    num_rounds = data.get("rounds") if data.get("rounds") else 5
    
    map = find_map(map_data) if map_data else GameMap.query.first_or_404("No maps in the database")
    
    session = Session(host_id=user.id,map_id=map.id,time_limit=time_limit,max_rounds=num_rounds)
    db.session.add(session)
    db.session.commit()
    return jsonify({"session":session.uuid}),200

@game_bp.route("/generate",methods=["POST"])
@login_required
def create_rounds(user):
    data = request.get_json()
    session_id = data.get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    round_num = data.get("num") if data.get("num") else 1
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    if session.host_id != user.id:
        return jsonify({"error":"access denied"}),403

    created = 0
    try:
        for _ in range(round_num):
            if session.max_rounds == session.current_round:
                return jsonify({"error":"max_round reached", "created":created}),400
            create_round(session,session.time_limit)
            created += 1
        return jsonify({"message":"rounds created","created":created}),200
    except Exception as e:
        return jsonify({"error":str(e),"created":created}),400
    

@game_bp.route("/play",methods=["POST"])
@login_required
def play(user):
    session_id = request.get_json().get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    
    if Player.query.filter_by(session_id=session.id,user_id=user.id).count() > 0:
        return jsonify({"error":"already played this session"}),403
    
    player = Player(session_id=session.id,user_id=user.id)
    db.session.add(player)
    db.session.commit()
    
    return jsonify({"message":"session joined"}),200

@game_bp.route("/next",methods=["GET"])
@login_required
def next_round(user):
    session_id = request.get_json().get("id")
    if not session_id:
        return jsonify({"error":"provided session id"}),400
    
    session = Session.query.filter_by(uuid=session_id).first_or_404("Session not found")
    player = Player.query.filter_by(session_id=session.id,user_id=user.id).first_or_404("Could not find player session")
    
    if player.current_round + 1 > session.current_round:
        print(player.current_round + 1,session.current_round)
        return jsonify({"error":"No more rounds are available"}),400
    
    player.current_round += 1
    
    round = Round.query.filter_by(round_number=player.current_round,session_id=session.id).first()
    location = round.location
    
    player.start_time = datetime.now()
    db.session.commit()
    
    return jsonify({
        "round_id":round.uuid,
        "lat":location.latitude,
        "lng":location.longitude,
        "time":round.time_limit
    }),200

@game_bp.route("/guess",methods=["POST"])
@login_required
def submit_guess(user):
    data = request.get_json()
    now = datetime.now()
    round_id = data.get("round_id")
    lat,lng = data.get("lat"),data.get("lng")
    user_id = user.id
    
    if not round_id or not lat or not lng:
        return jsonify({"error":"provided:round_id,lat,lng"}),400
    
    round = Round.query.filter_by(uuid=round_id).first_or_404("Round not found")
    player = Player.query.filter_by(user_id=user.id,session_id=round.session.id).first_or_404("Could not find player session")
    
    if round.round_number != player.current_round:
        return jsonify({"error":"wrong round provided"}),400
    
    if round.time_limit != -1 and player.start_time + timedelta(seconds=round.time_limit) < now:
        return jsonify({"error":"timed out"}),400
    
    try:
        guess = add_guess(user_id,lat,lng,round_id)
        return jsonify({
            "distance":guess.distance,
            "score": guess.score
        }),200
    except Exception as e:
        return jsonify({"error":str(e)}),400

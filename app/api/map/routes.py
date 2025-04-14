from flask import Blueprint,request, jsonify
from sqlalchemy import case, or_
from api.auth.auth import login_required
from models import Guess, Round, Session, User, GameMap, MapStats, UserMapStats
from api.game.gameutils import guess_to_json
from api.map.edit.route import map_edit_bp

map_bp = Blueprint("map",__name__)
map_bp.register_blueprint(map_edit_bp,url_prefix="/edit")
    
@map_bp.route("/search",methods=["GET"])
@login_required
def get_all_maps(user):
    name = request.args.get("name","")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    query = GameMap.query.join(GameMap.creator).filter(
        or_(
            GameMap.name.ilike(f"%{name}%"),
            User.username.ilike(f"%{name}%")
        )
    )
    maps = query.join(MapStats).order_by(
        case(
            (GameMap.creator_id == user.id, 0),
            (GameMap.creator_id == 42, 1),  
            else_=2
        ),
        MapStats.total_guesses.desc()
    ).paginate(page=page,per_page=per_page)
    return jsonify(
    {
        "maps":[map.to_json() for map in maps],
        "pages": maps.pages
    }),200

@map_bp.route("/stats",methods=["GET"])
@login_required
def get_map_info(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    stats = map.stats
    ret = {
        "name":map.name,
        "id":map.uuid, 
        "creator":map.creator.to_json(),
        "map_stats":{
            "average_generation_time": stats.total_generation_time/stats.total_loads if stats.total_loads != 0 else 0,
            "average_score": stats.total_score/stats.total_guesses if stats.total_guesses != 0 else 0,
            "average_distance": stats.total_distance/stats.total_guesses if stats.total_guesses != 0 else 0,
            "average_time": stats.total_time/stats.total_guesses if stats.total_guesses != 0 else 0,
            "total_guesses": stats.total_guesses,
            "max_distance": map.max_distance,
        },
    }
    
    if map.description:
        ret["description"] = map.description
    
    user_stats = UserMapStats.query.filter_by(user_id=user.id,map_id=map.id).order_by(UserMapStats.high_average_score.desc()).first()
    if user_stats and not user_stats.total_guesses == 0:
        ret["user_stats"] = {
            "average":{
                "score": user_stats.total_score/user_stats.total_guesses,
                "distance": user_stats.total_distance/user_stats.total_guesses,
                "time": user_stats.total_time/user_stats.total_guesses,
                "guesses": user_stats.total_guesses,
            }
        }
        
        if user_stats.high_session_id != None:
            ret["user_stats"]["high"] = {
                "score": user_stats.high_average_score,
                "distance": user_stats.high_average_distance,
                "time": user_stats.high_average_time,
                "rounds": user_stats.high_round_number,
                "session": user_stats.high_session.uuid
            }
    
    ret["other"] = {}
    
    top_guesses_stats = UserMapStats.query.filter_by(map_id=map.id).order_by(UserMapStats.total_guesses.desc()).first()
    
    if top_guesses_stats:
        ret["other"]["top_guesses"] = {
            "user":top_guesses_stats.user.to_json(),
            "stat":top_guesses_stats.total_guesses
        }
    
    fast_guesser_stats = UserMapStats.query.filter_by(map_id=map.id).order_by(
        case(
            (UserMapStats.total_guesses == 0, None),  
            else_=UserMapStats.total_time / UserMapStats.total_guesses
        )).first()
    if fast_guesser_stats:
        ret["other"]["fast_guesser"] = {
            "user":fast_guesser_stats.user.to_json(),
            "stat":fast_guesser_stats.total_time/fast_guesser_stats.total_guesses
        }
    
    best_average_stats = UserMapStats.query.filter_by(map_id=map.id).order_by(
        case(
            (UserMapStats.total_guesses == 0, None),  
            else_=UserMapStats.total_score / UserMapStats.total_guesses
        ).desc()).first()
    
    if best_average_stats:
        ret["other"]["best_average"] = {
            "user":best_average_stats.user.to_json(),
            "stat":best_average_stats.total_score/best_average_stats.total_guesses
        }
    
    number_of_5ks = Guess.query.filter_by(score=5000).join(Round).join(Session).filter(Session.map_id == map.id).count()
    ret["other"]["5ks"] = number_of_5ks
    
    return jsonify(ret),200

@map_bp.route("/bounds",methods=["GET"])
@login_required
def get_map_bounds(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    return jsonify([{**bound.bound.to_json(),"weight":bound.weight,"id":bound.id} for bound in map.map_bounds]),200

@map_bp.route("/leaderboard",methods=["GET"])
@login_required
def get_map_leaderboard(user):
    data = request.args
    map_id = data.get("id")
    nmpz = data.get("nmpz") == "true"
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    if not map_id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=map_id).first_or_404("Cannot find map")
    
    stats = UserMapStats.query.filter_by(map_id=map.id, nmpz=nmpz).filter(UserMapStats.high_session_id != None).order_by(UserMapStats.high_average_score.desc(),UserMapStats.high_round_number.desc(),UserMapStats.high_average_time).paginate(page=page,per_page=per_page)
    return jsonify({"data":[{
            "user":stat.user.to_json(),
            "average_score":stat.high_average_score,
            "average_distance":stat.high_average_distance,
            "average_time":stat.high_average_time,
            "rounds":stat.high_round_number,
            "rank": (page-1) * per_page + i + 1
        } for i,stat in enumerate(stats)],
        "pages":stats.pages
    }),200
    
@map_bp.route("/leaderboard/game",methods=["GET"])
@login_required
def get_leaderboard_game(user):
    data = request.args
    map_id = data.get("id")
    userInput = data.get("user")
    nmpz = data.get("nmpz") == "true" if data.get("nmpz") else None
    
    if not map_id or not user:
        return jsonify({"error":"provided: id and user"}),400
    
    map = GameMap.query.filter_by(uuid=map_id).first_or_404("Cannot find map")
    if (userInput):
        user = User.query.filter_by(username=userInput).first_or_404("Cannot find user")
    session = UserMapStats.query.filter_by(map_id=map.id,user_id=user.id)
    if nmpz != None:
        session = session.filter_by(nmpz=nmpz)

    session = session.order_by(UserMapStats.high_average_score.desc(),UserMapStats.high_round_number.desc(),UserMapStats.high_average_time).first_or_404("Cannot find user stats")
    if session.high_session_id == None:
        return jsonify({"error":"User has not played the game"}),400
    
    rounds = Round.query.filter_by(session_id=session.high_session.id).order_by(Round.round_number).all()
    
    ret = {
        "user":user.to_json(),
        "rounds":[{"lat":round.location.latitude,"lng":round.location.longitude} for round in rounds],
        "guesses":[guess_to_json(user,round) for round in rounds],
        "score":session.high_average_score * session.high_round_number,
        "distance":session.high_average_distance * session.high_round_number,
        "time":session.high_average_time * session.high_round_number,
    }

    return jsonify(ret),200
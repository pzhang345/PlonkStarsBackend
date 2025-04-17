from flask import Blueprint,request, jsonify
from sqlalchemy import Float, case, cast, desc, func, or_

from api.auth.auth import login_required
from models.session import Guess, Round, Session
from models.db import db
from models.user import User
from models.map import GameMap
from models.stats import MapStats, UserMapStats
from api.game.gameutils import guess_to_json
from api.map.edit.route import map_edit_bp
from api.map.map import get_stats

map_bp = Blueprint("map",__name__)
map_bp.register_blueprint(map_edit_bp,url_prefix="/edit")
    
@map_bp.route("/search",methods=["GET"])
@login_required
def get_all_maps(user):
    name = request.args.get("name","")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    nmpz = request.args.get("nmpz") == "true" if request.args.get("nmpz") else None
    
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
    
    maps = (
        db.session.query(
            GameMap,
            func.sum(MapStats.total_score).label("total_score"),
            func.sum(MapStats.total_guesses).label("total_guesses"),
        )
        .outerjoin(MapStats, GameMap.id == MapStats.map_id)
        .join(GameMap.creator)
        .filter(
            or_(
                GameMap.name.ilike(f"%{name}%"),
                User.username.ilike(f"%{name}%")
            )
        ) 
        .group_by(GameMap.id)
        .order_by(
            case(
                (GameMap.creator_id == user.id, 0),
                (GameMap.creator_id == 42, 1),  
                else_=2
            ),
            desc("total_guesses")
        ).paginate(page=page,per_page=per_page)
    )
    
    
    ret = []
    for map,score,guess in maps:
        ret.append({
            "name":map.name,
            "id":map.uuid,
            "creator":map.creator.to_json(),
            "average_score":score/guess if guess != None or guess == 0 else 0,
            "average_generation_time": map.generation.total_generation_time/map.generation.total_loads if map.generation != None and map.generation.total_loads != 0 else 0,
            "total_guesses": guess if guess != None else 0,
        })

    return jsonify(
    {
        "maps":ret,
        "pages": maps.pages
    }),200

@map_bp.route("/stats",methods=["GET"])
@login_required
def get_map_info(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    nmpz = request.args.get("nmpz") == "true" if request.args.get("nmpz") else None
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    stats = get_stats(map=map,nmpz=nmpz)
    generation = map.generation
    ret = {
        "name":map.name,
        "id":map.uuid, 
        "creator":map.creator.to_json(),
        "map_stats":{
            "average_generation_time": generation.total_generation_time/generation.total_loads if generation != None and generation.total_loads != 0 else 0,
            "average_score": stats.total_score/stats.total_guesses if stats.total_guesses != None and stats.total_guesses != 0 else 0,
            "average_distance": stats.total_distance/stats.total_guesses if stats.total_guesses != None and stats.total_guesses != 0 else 0,
            "average_time": stats.total_time/stats.total_guesses if stats.total_guesses != None and stats.total_guesses != 0 else 0,
            "total_guesses": stats.total_guesses if stats.total_guesses != None else 0,
            "max_distance": map.max_distance,
        },
    }
    
    if map.description:
        ret["description"] = map.description
    
    
    user_stats= get_stats(map=map,user=user,nmpz=nmpz)
    if user_stats.total_guesses != None and not user_stats.total_guesses == 0:
        ret["user_stats"] = {
            "average":{
                "score": user_stats.total_score/user_stats.total_guesses,
                "distance": user_stats.total_distance/user_stats.total_guesses,
                "time": user_stats.total_time/user_stats.total_guesses,
                "guesses": user_stats.total_guesses,
            }
        }
        
        user_high = UserMapStats.query.filter_by(user_id=user.id,map_id=map.id).order_by(UserMapStats.high_average_score.desc(),UserMapStats.high_round_number.desc(),UserMapStats.high_average_time)
        if nmpz != None:
            user_high = user_high.filter_by(nmpz=nmpz)
        user_high = user_high.first()
        if user_high.high_session_id != None:
            ret["user_stats"]["high"] = {
                "score": user_high.high_average_score,
                "distance": user_high.high_average_distance,
                "time": user_high.high_average_time,
                "rounds": user_high.high_round_number,
                "session": user_high.high_session.uuid
            }
    
    ret["other"] = {}
    
    map_stats = (
        db.session.query(
            User,
            func.sum(cast(UserMapStats.total_time,Float)).label("total_time"),
            func.sum(cast(UserMapStats.total_score,Float)).label("total_score"),
            func.sum(cast(UserMapStats.total_distance,Float)).label("total_distance"),
            func.sum(cast(UserMapStats.total_guesses,Float)).label("total_guesses"),
        ).join(UserMapStats, User.id == UserMapStats.user_id)
    )
    
    if nmpz != None:
        map_stats = map_stats.filter(UserMapStats.nmpz == nmpz)
        
    map_stats = map_stats.filter(UserMapStats.map_id == map.id).group_by(User.id)
    
    
    top_guesses_stats = map_stats.order_by(desc("total_guesses")).first()
    
    if top_guesses_stats:
        ret["other"]["top_guesses"] = {
            "user":top_guesses_stats[0].to_json(),
            "stat":top_guesses_stats[4]
        }
    
    fast_guesser_stats =map_stats.order_by(
        case(
            (func.sum(UserMapStats.total_guesses) == 0, None),
            else_=func.sum(UserMapStats.total_time) / func.sum(UserMapStats.total_guesses)
        )
    ).first()
    
    if fast_guesser_stats:
        ret["other"]["fast_guesser"] = {
            "user":fast_guesser_stats[0].to_json(),
            "stat":fast_guesser_stats[1]/fast_guesser_stats[4]
        }
    
    best_average_stats = map_stats.order_by(
        desc(
            case(
                (func.sum(UserMapStats.total_guesses) == 0, 0),
                else_=func.sum(UserMapStats.total_score) / func.sum(UserMapStats.total_guesses)
            )
        )
    ).first()
    
    if best_average_stats:
        ret["other"]["best_average"] = {
            "user":best_average_stats[0].to_json(),
            "stat":best_average_stats[2]/best_average_stats[4]
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
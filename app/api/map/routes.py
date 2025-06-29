from flask import Blueprint,request, jsonify
from sqlalchemy import Float, and_, case, cast, desc, func, literal_column, or_

from api.account.auth import login_required
from models.session import BaseRules, Guess, Round, Session
from models.db import db
from models.user import User
from models.map import GameMap, MapEditor
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
    editable = not not request.args.get("editable")
    nmpz = request.args.get("nmpz") == "true" if request.args.get("nmpz") else None
    
    maps = (
        db.session.query(
            GameMap,
            func.coalesce(func.sum(MapStats.total_score),0).label("total_score"),
            func.coalesce(func.sum(MapStats.total_guesses), 0).label("total_guesses")
        )
        .outerjoin(MapStats, GameMap.id == MapStats.map_id)
        .join(GameMap.creator)
        .filter(
            or_(
                GameMap.name.ilike(f"%{name}%"),
                GameMap.uuid == name,
                User.username.ilike(f"%{name}%")
            )
        )
    )
    
    if not user.is_admin and editable:
        maps = maps.outerjoin(MapEditor, GameMap.id == MapEditor.map_id).filter(
            or_(
                GameMap.creator_id == user.id,
                and_(
                    MapEditor.user_id == user.id,
                    MapEditor.permission_level > 0
                )
            )
        )
    
    if nmpz != None:
        maps = maps.filter(MapStats.nmpz == nmpz)
        
    maps = (
        maps.group_by(GameMap.id)
        .order_by(
            case(
                (GameMap.creator_id == user.id, 0),
                (GameMap.creator_id == 42, 1),  
                else_=2
            ),
            desc(literal_column("total_guesses"))
        ).paginate(page=page,per_page=per_page)
    )
    
    
    
    ret = []
    for map,score,guess in maps:
        ret.append({
            "name":map.name,
            "id":map.uuid,
            "creator":map.creator.to_json(),
            "average_score":score/guess if guess != 0 else 0,
            "average_generation_time": map.generation.total_generation_time/map.generation.total_loads if map.generation != None and map.generation.total_loads != 0 else 0,
            "total_guesses": guess,
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
    
    five_ks = Guess.query.filter_by(score=5000).join(Round).join(Session).join(BaseRules).filter(BaseRules.map_id == map.id)
    if nmpz != None:
        five_ks = five_ks.filter(BaseRules.nmpz == nmpz)
    
    number_of_5ks = five_ks.count()
    ret["other"]["5ks"] = number_of_5ks
    
    if number_of_5ks > 0:
        most_5ks_entry = (
            five_ks.with_entities(Guess.user_id, func.count(Guess.id).label("count"))
            .group_by(Guess.user_id)
            .order_by(func.count(Guess.id).desc())
            .first()
        )
        
        ret["other"]["most_5ks"] = {
            "user": User.query.filter_by(id=most_5ks_entry.user_id).first().to_json(),
            "stat": most_5ks_entry.count
        }
        fastest_5k = five_ks.order_by(Guess.time).first()
        ret["other"]["fastest_5k"] = {
            "user":fastest_5k.user.to_json(),
            "stat":fastest_5k.time,
        }
    else:
        highest_score = Guess.query.join(Round).join(Session).join(BaseRules).filter(BaseRules.map_id == map.id).order_by(Guess.score.desc())
        if nmpz != None:
            highest_score = highest_score.filter(BaseRules.nmpz == nmpz)
        highest_score = highest_score.first()
        
        if highest_score:
            ret["other"]["highest_score"] = {
                "user":highest_score.user.to_json(),
                "stat":highest_score.score,
            }
        
            highest_k = highest_score.score // 1000
            fastest_nk = Guess.query.join(Round).join(Session).join(BaseRules).filter(BaseRules.map_id == map.id, Guess.score > highest_k * 1000).order_by(Guess.time)
            if nmpz != None:
                fastest_nk = fastest_nk.filter(BaseRules.nmpz == nmpz)
            fastest_nk = fastest_nk.first()
            if fastest_nk:
                ret["other"]["fastest_nk"] = {
                    "user":fastest_nk.user.to_json(),
                    "stat":fastest_nk.time,
                }
    print(ret)

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
    nmpz = data.get("nmpz").lower() == "true" if data.get("nmpz") else None
    
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
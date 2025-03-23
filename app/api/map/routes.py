from decimal import Decimal
from flask import Blueprint,request, jsonify
from sqlalchemy import case
from api.auth.auth import login_required
from models import Guess, Round, Session, db,GameMap,MapStats,MapBound,Bound, UserMapStats
from api.map.map import map_add_bound,bound_recalculate
from utils import coord_at, float_equals
map_bp = Blueprint("map",__name__)

@map_bp.route("/create",methods=["POST"])
@login_required
def create_map(user):
    name=request.get_json().get("name")
    if not name:
        return jsonify({"error":"provided: name"}),400
    
    map = GameMap(creator_id=user.id,name=name)
    db.session.add(map)
    db.session.flush()
    map_stats = MapStats(map_id=map.id)
    db.session.add(map_stats)
    
    db.session.commit()
    return jsonify({"map_id":map.uuid}),200


@map_bp.route("bound/add",methods=["POST"])
@login_required
def add_bound(user):
    data = request.get_json()
    if data.get("start") and data.get("end"):
        if "lat" in data.get("start"):
            s_lat,s_lng = data.get("start").get("lat"),data.get("start").get("lng")
            e_lat,e_lng = data.get("end").get("lat"),data.get("end").get("lng")
        else:
            s_lat,s_lng = data.get("start")
            e_lat,e_lng = data.get("end")
    else:
        s_lat, s_lng, e_lat, e_lng = data.get("s_lat"),data.get("s_lng"),data.get("e_lat"),data.get("e_lng")
    
    weight = data.get("weight")
    weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if map.creator_id != user.id and not user.is_admin:
        return jsonify({"error":"Don't have access to the map"}),403
    
    if s_lat == None or s_lng == None or e_lat == None and e_lng == None:
        return jsonify({"error":"please provided these arguments: s_lat, s_lng, e_lat and e_lng"}),400
    
    if not (-90 <= s_lat <= e_lat <= 90 and -180 <= s_lng <= e_lng <= 180):
        return jsonify({"error":"invalid input"}),400
    
    res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
    
    return jsonify(res[0]),res[1]

@map_bp.route("bound/remove",methods=["DELETE"])
@login_required
def remove_bound(user):
    data = request.get_json()
    map_id = data.get("id")
    if data.get("start") and data.get("end"):
        if "lat" in data.get("start"):
            s_lat,s_lng = data.get("start").get("lat"),data.get("start").get("lng")
            e_lat,e_lng = data.get("end").get("lat"),data.get("end").get("lng")
        else:
            s_lat,s_lng = data.get("start")
            e_lat,e_lng = data.get("end")
    else:
        s_lat, s_lng, e_lat, e_lng = data.get("s_lat"),data.get("s_lng"),data.get("e_lat"),data.get("e_lng")
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    user_stats = UserMapStats.query.filter_by(user_id=user.id,map_id=map.id).first()
    if map.creator_id != user.id and not user.is_admin:
        return jsonify({"error":"Don't have access to the map"}),403
    
    if s_lat == None or s_lng == None or e_lat == None and e_lng == None or not map_id:
        return jsonify({"error":"please provided these arguments: s_lat, s_lng, e_lat and e_lng"}),400
    
    bound = Bound.query.filter(
        coord_at(Bound.start_latitude,s_lat),
        coord_at(Bound.start_longitude,s_lng),
        coord_at(Bound.end_latitude,e_lat),
        coord_at(Bound.end_longitude,e_lng)
    ).first()
    if not bound:
        return {"error":"Cannot find bound"},404
    
    mapbound = MapBound.query.filter_by(bound_id=bound.id,map_id=map.id).first()
    if not mapbound:
        return {"error":"Cannot find map bound"},404
    
    weight = mapbound.weight
    map.total_weight -= weight
    
    db.session.delete(mapbound)
    db.session.flush()
    if float_equals(bound.start_latitude,map.start_latitude) or float_equals(bound.start_longitude,map.start_longitude) or float_equals(bound.end_latitude,map.end_latitude) or float_equals(bound.end_longitude,map.end_longitude):
        bound_recalculate(map)
    db.session.commit()
    
    return jsonify({"message":"bound removed"}),200

@map_bp.route("/search",methods=["GET"])
@login_required
def get_all_maps(user):
    name = request.args.get("name","")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    query = GameMap.query.filter(GameMap.name.ilike(f"%{name}%"))
    maps = query.join(MapStats).order_by(MapStats.total_guesses.desc()).paginate(page=page,per_page=per_page)
    return jsonify(
    {
        "maps":[{
                "name":map.name,
                "id":map.uuid, 
                "creator":map.creator.to_json(),
                "average_score":map.stats.total_score/map.stats.total_guesses if map.stats.total_guesses != 0 else 0,
                "average_generation_time": map.stats.total_generation_time/map.stats.total_loads if map.stats.total_loads != 0 else 0,
                "total_guesses": map.stats.total_guesses,
            } for map in maps],
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
    
    user_stats = UserMapStats.query.filter_by(user_id=user.id,map_id=map.id).first()
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
    return jsonify([bound.bound.to_dict() for bound in map.map_bounds]),200

@map_bp.route("/edit",methods=["GET"])
@login_required
def can_edit_map(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    return jsonify({"can_edit": map.creator_id == user.id or user.is_admin}),200
    

@map_bp.route("/leaderboard",methods=["GET"])
@login_required
def get_map_leaderboard(user):
    data = request.args
    map_id = data.get("id")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    if not map_id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=map_id).first_or_404("Cannot find map")
    stats = UserMapStats.query.filter_by(map_id=map.id).filter(UserMapStats.high_session_id != None).order_by(UserMapStats.high_average_score.desc(),UserMapStats.high_round_number.desc(),UserMapStats.high_average_time).paginate(page=page,per_page=per_page)
    return jsonify({"data":[{
            "user":stat.user.to_json(),
            "average_score":stat.high_average_score,
            "average_distance":stat.high_average_distance,
            "average_time":stat.high_average_time,
            "rounds":stat.high_round_number,
        } for stat in stats],
        "pages":stats.pages
    }),200
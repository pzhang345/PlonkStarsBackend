from flask import Blueprint,request, jsonify
from api.auth.auth import login_required
from models import db,GameMap,MapStats
from api.map.map import map_add_bound
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


@map_bp.route("/addbound",methods=["POST"])
@login_required
def add_bound(user):
    data = request.get_json()
    if data.get("start") and data.get("end"):
        s_lat,s_lng = data.get("start")
        e_lat,e_lng = data.get("end")
    else:
        s_lat, s_lng, e_lat, e_lng = data.get("s_lat"),data.get("s_lng"),data.get("e_lat"),data.get("e_lng")
    print(s_lat,s_lng,e_lat,e_lng)
    
    weight = data.get("weight")
    weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    # if map.creator_id != user.id:
    #     return jsonify({"error":"Not your map. Access denied"}),403
    
    if s_lat == None or s_lng == None or e_lat == None and e_lng == None:
        return jsonify({"error":"please provided these arguments: s_lat, s_lng, e_lat and e_lng"}),400
    
    if not (-90 <= s_lat <= e_lat <= 90 and -180 <= s_lng <= e_lng <= 180):
        return jsonify({"error":"invalid input"}),400
    
    res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
    
    return jsonify(res[0]),res[1]

@map_bp.route("/search",methods=["GET"])
@login_required
def get_all_maps(user):
    name = request.args.get("name","")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    query = GameMap.query.filter(GameMap.name.ilike(f"%{name}%"))
    maps = query.paginate(page=page,per_page=per_page)
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
    
@map_bp.route("/info",methods=["GET"])
@login_required
def get_map_info(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    stats = map.stats
    return jsonify({
        "name":map.name,
        "id":map.uuid, 
        "creator":map.creator.to_json(),
        "average_generation_time": stats.total_generation_time/stats.total_loads if stats.total_loads != 0 else 0,
        "average_score": stats.total_score/stats.total_guesses if stats.total_guesses != 0 else 0,
        "average_distance": stats.total_distance/stats.total_guesses if stats.total_guesses != 0 else 0,
        "average_time": stats.total_time/stats.total_guesses if stats.total_guesses != 0 else 0,
        "total_guesses": stats.total_guesses,
        "max_distance": map.max_distance,
        "bounds":[bounds.bound.to_dict() for bounds in map.map_bounds]
    }),200
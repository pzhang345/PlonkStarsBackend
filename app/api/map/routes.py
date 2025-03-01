from flask import Blueprint,request, jsonify
from api.auth.auth import login_required
from models import db,GameMap
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
    db.session.commit()
    
    return jsonify({"map_id":map.uuid}),200


@map_bp.route("/addbound",methods=["POST"])
@login_required
def add_bound(user):
    data = request.get_json()
    s_lat, s_lng, e_lat, e_lng = data.get("s_lat"),data.get("s_lng"),data.get("e_lat"),data.get("e_lng")
    weight = data.get("weight")
    weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if map.creator_id != user.id:
        return jsonify({"error":"Not your map. Access denied"}),403
    
    if s_lat == None or s_lng == None or e_lat == None and e_lng == None:
        return jsonify({"error":"please provided these arguments: s_lat, s_lng, e_lat and e_lng"}),400
    
    if not (-90 <= s_lat <= e_lat <= 90 and -180 <= s_lng <= e_lng <= 180):
        return jsonify({"error":"invalid input"}),400
    
    res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
    
    return jsonify(res[0]),res[1]
from flask import Blueprint,request, jsonify

from api.auth.auth import login_required
from api.map.edit.mapedit import bound_recalculate, can_edit, map_add_bound, get_bound, map_remove_bound
from models import db, Bound, MapBound, MapStats, GameMap
from utils import coord_at, float_equals

map_edit_bp = Blueprint("map_edit",__name__)

@map_edit_bp.route("",methods=["GET"])
@login_required
def can_edit_map(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    return jsonify({"can_edit": can_edit(user,map)}),200

@map_edit_bp.route("/create",methods=["POST"])
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


@map_edit_bp.route("bound/add",methods=["POST"])
@login_required
def add_bound(user):
    data = request.get_json()
    try:
        (s_lat,s_lng),(e_lat,e_lng) = get_bound(data)
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    
    weight = data.get("weight")
    weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
    
    return jsonify(res[0]),res[1]

@map_edit_bp.route("bound/add/all",methods=["POST"])
@login_required
def add_bounds(user):
    data = request.get_json()
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    if not data.get("bounds"):
        return jsonify({"error":"please provided these arguments:bounds"}),400
    bounds = []
    try:
        for bound in data.get("bounds"):
            try:
                (s_lat,s_lng),(e_lat,e_lng) = get_bound(bound)
                weight = data.get("weight")
                weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
                
                res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
                if res[1] == 200:
                    bounds.append(res[0]["bound"])
            except Exception as e:
                pass
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify({"added": bounds}),200

@map_edit_bp.route("bound/remove",methods=["DELETE"])
@login_required
def remove_bound(user):
    data = request.get_json()
    try:
        (s_lat,s_lng),(e_lat,e_lng) = get_bound(data)
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    try:
        ret = map_remove_bound(map,s_lat,s_lng,e_lat,e_lng)
        return jsonify(ret[0]),ret[1]
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400

@map_edit_bp.route("bound/remove/all",methods=["DELETE"])
@login_required
def remove_bounds(user):
    data = request.get_json()
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    ret = []
    try:
        for bound in data.get("bounds"):
            try:
                (s_lat,s_lng),(e_lat,e_lng) = get_bound(bound)
                bound = map_remove_bound(map,s_lat,s_lng,e_lat,e_lng)[0]
                ret += [bound["remove"]]
            except Exception as e:
                pass
    except Exception as e:
        return jsonify({"error":str(e)}),400
    
    return jsonify({"remove":ret}),200

@map_edit_bp.route("/description",methods=["POST"])
@login_required
def edit_description(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    map.description = data.get("description")
    db.session.commit()
    return jsonify({"message":"description updated"}),200
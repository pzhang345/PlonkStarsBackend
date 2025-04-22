from flask import Blueprint,request, jsonify

from api.account.auth import login_required
from api.map.edit.mapedit import bound_recalculate, can_edit, map_add_bound, get_new_bound, map_remove_bound, bound_recalculate,get_bound
from models.db import db
from models.user import User
from models.map import MapBound, GameMap, MapEditor
from fsocket import socketio

map_edit_bp = Blueprint("map_edit",__name__)

@map_edit_bp.route("",methods=["GET"])
@login_required
def can_edit_map(user):
    id = request.args.get("id")
    if not id:
        return jsonify({"error":"provided: id"}),400
    
    map = GameMap.query.filter_by(uuid=id).first_or_404("Cannot find map")
    return jsonify({"permission": can_edit(user,map)}),200

@map_edit_bp.route("/create",methods=["POST"])
@login_required
def create_map(user):
    name=request.get_json().get("name")
    if not name:
        return jsonify({"error":"provided: name"}),400
    
    map = GameMap(creator_id=user.id,name=name)
    db.session.add(map)
    db.session.commit()

    return jsonify({"id":map.uuid}),200

#################################################
# Permission 1                                  #
#################################################

@map_edit_bp.route("bound/add",methods=["POST"])
@login_required
def add_bound(user):
    data = request.get_json()
    try:
        (s_lat,s_lng),(e_lat,e_lng) = get_new_bound(data)
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    
    weight = data.get("weight")
    weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 1:
        return jsonify({"error":"Don't have access to the map"}),403
    
    res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
    
    socketio.emit("add",{"bounds":[res[0]]},namespace="/socket/map/edit",room=map.uuid)
    return jsonify(res[0]),res[1]

@map_edit_bp.route("bound/add/all",methods=["POST"])
@login_required
def add_bounds(user):
    data = request.get_json()
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 1:
        return jsonify({"error":"Don't have access to the map"}),403
    
    if not data.get("bounds"):
        return jsonify({"error":"please provided these arguments:bounds"}),400
    bounds = []
    try:
        for bound in data.get("bounds"):
            try:
                (s_lat,s_lng),(e_lat,e_lng) = get_new_bound(bound)
                weight = data.get("weight")
                weight = max(1,weight) if weight else max(1,(e_lat-s_lat) * (e_lng-s_lng) * 10000)
                
                res = map_add_bound(map,s_lat,s_lng,e_lat,e_lng,weight)
                if res[1] == 200:
                    bounds.append(res[0])
            except Exception as e:
                pass
    except Exception as e:
        return jsonify({"error":str(e)}),400
    
    socketio.emit("add",{"bounds":bounds},namespace="/socket/map/edit",room=map.uuid)
    return jsonify(bounds),200

@map_edit_bp.route("bound/remove",methods=["DELETE"])
@login_required
def remove_bound(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 1:
        return jsonify({"error":"Don't have access to the map"}),403
    
    try:
        mapbound = get_bound(data,map)
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    
    
    try:
        ret = map_remove_bound(map,mapbound)
        socketio.emit("remove",{"bounds":[ret[0]["id"]]},namespace="/socket/map/edit",room=map.uuid)
        return jsonify(ret[0]),ret[1]
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400

@map_edit_bp.route("bound/remove/all",methods=["DELETE"])
@login_required
def remove_bounds(user):
    data = request.get_json()
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 1:
        return jsonify({"error":"Don't have access to the map"}),403
    
    ret = []
    try:
        for bound in data.get("bounds"):
            try:
                mapbound = get_bound(bound,map)
                bound = map_remove_bound(map,mapbound)[0]
                ret += [bound["id"]]
            except Exception as e:
                pass
    except Exception as e:
        return jsonify({"error":str(e)}),400
    
    socketio.emit("remove",{"bounds":ret},namespace="/socket/map/edit",room=map.uuid)
    return jsonify(ret),200

@map_edit_bp.route("bound/reweight",methods=["POST"])
@login_required
def reweight_bound(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 1:
        return jsonify({"error":"Don't have access to the map"}),403
    
    (s_lat,s_lng),(e_lat,e_lng) = get_bound(data)
    weight = data.get("weight")
    if not weight:
        return jsonify({"error":"please provided these arguments: weight"}),400
    
    ret = bound_recalculate(map,s_lat,s_lng,e_lat,e_lng,weight)
    socketio.emit("reweight",{"bounds":[ret]},namespace="/socket/map/edit",room=map.uuid)
    return jsonify(ret[0]),ret[1]
     
#################################################
# Permission 2                                  #
#################################################

@map_edit_bp.route("/description",methods=["POST"])
@login_required
def edit_description(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 2:
        return jsonify({"error":"Don't have access to the map"}),403
    
    map.description = data.get("description")
    db.session.commit()
    return jsonify({"message":"description updated"}),200

@map_edit_bp.route("/name",methods=["POST"])
@login_required
def edit_name(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 2:
        return jsonify({"error":"Don't have access to the map"}),403
    
    map.name = data.get("name")
    db.session.commit()
    return jsonify({"message":"name updated"}),200

#################################################
# Permission 3                                  #
#################################################

@map_edit_bp.route("/delete",methods=["DELETE"])
@login_required
def delete_map(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if can_edit(user,map) < 3:
        return jsonify({"error":"Don't have access to the map"}),403
    mapbounds = map.map_bounds
    for mapbound in mapbounds:
        if MapBound.query.filter_by(bound_id=mapbound.bound_id).count() <= 1:
            db.session.delete(mapbound.bound)
    db.session.delete(map)
    db.session.commit()
    return jsonify({"message":"map deleted"}),200


##################################################
# Can add or remove people with lower permissions#
##################################################

@map_edit_bp.route("/editor/add",methods=["POST"])
@login_required
def add_editor(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    if not can_edit(user,map):
        return jsonify({"error":"Don't have access to the map"}),403
    
    new_editor = User.query.filter_by(username=data.get("username")).first()
    if not new_editor or new_editor.id == user.id:
        return jsonify({"error":"provided valid username"}),400
    
    permission = data.get("permission")
    if can_edit(user,map) <= permission:
        return jsonify({"error":"Not high enough permission"}),400
    
    
    editor = MapEditor.query.filter_by(map_id=map.id,user_id=new_editor.id).first()
    if not editor:
        editor = MapEditor(map_id=map.id,user_id=new_editor.id)
        db.session.add(editor)
    
    editor.permission_level = permission
    db.session.commit()
    return jsonify({"message":"editor added"}),200

@map_edit_bp.route("/editor/remove",methods=["DELETE"])
@login_required
def remove_editor(user):
    data = request.get_json()
    
    map = GameMap.query.filter_by(uuid=data.get("id")).first_or_404("Cannot find map")
    
    remove_editor = User.query.filter_by(username=data.get("username")).first()
    if not remove_editor:
        return jsonify({"error":"provided valid username"}),400
    
    editor = MapEditor.query.filter_by(map_id=map.id,user_id=remove_editor.id).first()
    if not editor:
        return jsonify({"error":"provided valid map editor"}),400
    
    if can_edit(user,map) <= editor.permission_level:
        return jsonify({"error":"Not high enough permission"}),400
    
    db.session.delete(editor)
    db.session.commit()
    return jsonify({"message":"editor deleted"}),200
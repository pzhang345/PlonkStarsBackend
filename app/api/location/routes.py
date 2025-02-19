from flask import Blueprint, request, jsonify

from api.location.generate import generate_location,db_location
from models import db, Guess,GameMap,Bound
from api.auth.auth import login_required

location_bp = Blueprint("location",__name__)

@location_bp.route("/generate",methods=["GET"])
@login_required
def generateLocation(user):
    try:
        new_coord = generate_location(GameMap.query.first())
    except Exception as e:
        return jsonify({"error":str(e)}),400
    return jsonify({
        "id":new_coord.id,
        "lat":new_coord.latitude,
        "lng":new_coord.longitude
    }),200

@location_bp.route("/get",methods=["GET"])
# @login_required
def getLocation():
    try:
        location = db_location(Bound.query.first())
        return jsonify({
        "id": location.id,
        "lat": location.latitude,
        "lng": location.longitude,
    }),200
    except Exception as e:
        return jsonify({"error": str(e)}), 404


# @location_bp.route("/guess",methods=["POST"])
# @login_required
# def guess(user):
#     data = request.get_json()
#     guess = Guess(location_id=data.get("loc_id"),user_id=user.id,latitude=data.get("lat"),longitude=data.get("lng"))
#     db.session.add(guess)
#     db.session.commit()
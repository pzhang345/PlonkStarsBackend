from flask import Blueprint, request, jsonify

from api.location.generate import generate
from models import db,SVLocation, Guess
from api.auth.auth import login_required
import random

location_bp = Blueprint("location",__name__)

@location_bp.route("/generate",methods=["GET"])
@login_required
def generateLocation(current_user):
    gen = generate()
    new_coord = SVLocation(latitude=gen["lat"],longitude=gen["lng"])

    db.session.add(new_coord)
    db.session.commit()

    return jsonify({
        "id":new_coord.id,
        "lat":new_coord.latitude,
        "lng":new_coord.longitude
    }),200

@location_bp.route("/get",methods=["GET"])
@login_required
def getLocation(current_user):
    row_count = db.session.query(SVLocation).count()
    if row_count == 0:
        return jsonify({"error": "No items found in the database"}), 404
    
    random_index = random.randint(0, row_count - 1)
    random_coord = SVLocation.query.offset(random_index).first()

    
    return jsonify({
        "id": random_coord.id,
        "lat": random_coord.latitude,
        "lng": random_coord.longitude,
    }),200

@location_bp.route("/guess",methods=["POST"])
@login_required
def guess(current_user):
    data = request.get_json()
    guess = Guess(location_id=data["loc_id"],user_id=current_user.id,latitude=data["lat"],longitude=data["lng"])
    db.session.add(guess)
    db.session.commit()
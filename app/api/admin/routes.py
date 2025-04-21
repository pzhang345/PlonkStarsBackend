from flask import Blueprint,request, jsonify
from sqlalchemy import Float, cast, func

from api.account.auth import login_required
from models.db import db
from models.map import GameMap
from models.session import Guess, Round, Session
from models.stats import MapStats, UserMapStats
from models.user import User, UserCosmetics

admin_bp = Blueprint("admin_bp",__name__)

@admin_bp.route("/usercosmetics/initialize",methods=["POST"])
@login_required
def initialize_user_cosmetics(user):
    if not user.is_admin:
        return jsonify({"error":"You are not an admin"}),403
    users = User.query.all()
    for user in users:
        if not user.cosmetics:
            cosmetics = UserCosmetics(user_id = user.id)
            db.session.add(cosmetics)
    db.session.commit()
    return jsonify({"message":"User cosmetics initialized"}),200

@admin_bp.route("/scores/recalculate",methods=["POST"])
@login_required
def recalculate_scores(user):
    if not user.is_admin:
        return jsonify({"error":"You are not an admin"}),403
    data = request.get_json(silent=True)
    
    map_id = data.get("id") if data else None
    
    all_scores = (
        db.session.query(
            User,
            GameMap,
            Session.nmpz.label("nmpz"),
            func.sum(cast(Guess.score,Float)).label("total_score"),
            func.sum(cast(Guess.distance,Float)).label("total_distance"),
            func.sum(cast(Guess.time,Float)).label("total_time"),
            func.count(Guess.id).label("total_guesses"),
        )
        .join(User, Guess.user_id == User.id)
        .join(Round, Guess.round_id == Round.id)
        .join(Session, Round.session_id == Session.id)
        .join(GameMap, Session.map_id == GameMap.id)
    )
    
    map_query = MapStats.query
    if map_id:
        all_scores = all_scores.filter(GameMap.uuid == map_id)
        map_query = map_query.filter_by(map_id=map_id)
    
    for stats in map_query:
        stats.total_score = 0
        stats.total_guesses = 0
        stats.total_time = 0
        stats.total_distance = 0
    db.session.flush()
    
    all_scores = all_scores.group_by(User.id, GameMap.id, Session.nmpz)
    
    keys = set()
    for user,map,nmpz,score,distance,time,guess in all_scores:
        user_map_stats = UserMapStats.query.filter_by(user_id=user.id, map_id=map.id, nmpz=nmpz).first()
        if user_map_stats is None:
            user_map_stats = UserMapStats(
                user_id=user.id,
                map_id=map.id,
                nmpz=nmpz,
                total_score=0,
                total_guesses=0,
                total_time=0,
                total_distance=0
            )
            db.session.add(user_map_stats)
        user_map_stats.total_score = score
        user_map_stats.total_guesses = guess
        user_map_stats.total_time = time
        user_map_stats.total_distance = distance
        
        
        map_stats = MapStats.query.filter_by(map_id=map.id, nmpz=nmpz).first()
        if map_stats is None:
            map_stats = MapStats(
                map_id=map.id,
                nmpz=nmpz,
                total_score=0,
                total_guesses=0,
                total_time=0,
                total_distance=0
            )
            db.session.add(map_stats)
        
        map_stats.total_score += score
        map_stats.total_guesses += guess
        map_stats.total_time += time
        map_stats.total_distance += distance
        keys.add((user.id,map.id,nmpz))
        
    for user_stat in UserMapStats.query.all():
        key = (user_stat.user_id, user_stat.map_id, user_stat.nmpz)
        if key not in keys:
            db.session.delete(user_stat)

    db.session.commit()
    return jsonify({"message":"Scores recalculated"}),200
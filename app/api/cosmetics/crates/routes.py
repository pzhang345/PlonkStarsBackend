import random

from flask import Blueprint, request, jsonify
from sqlalchemy import func

from models.db import db
from models.cosmetics import Cosmetics, CosmeticsOwnership, Tier, UserCoins
from models.crates import Crate
from api.account.auth import login_required

crates_bp = Blueprint("crates_bp", __name__)


dupe_refund = {
    Tier.COMMON: 100,
    Tier.UNCOMMON: 300,
    Tier.RARE: 750,
    Tier.EPIC: 1500,
    Tier.LEGENDARY: 4000,
}

@crates_bp.route("/buy", methods=["POST"])
@login_required()
def buy_crate(user):
    data = request.get_json()
    crate_name = data.get("crate")
    crate = Crate.query.filter_by(name=crate_name).first_or_404()
    user_coins = UserCoins.query.filter_by(user_id=user.id).first()
    if user_coins.coins < crate.price:
        return jsonify({"message": "Not enough coins to purchase this crate"}), 403
    
    user_coins.coins -= crate.price


    item_rarity = None
    roll = random.randint(1,crate.total_weight)
    for items in crate.items:
        roll -= items.weight
        if roll <= 0:
            item_rarity = items
            break
    
    if not item_rarity:
        db.session.commit()
        return jsonify({"coins": user_coins.coins}), 200
    random_func = func.rand() if db.engine.dialect.name == 'mysql' else func.random()
    
    
    # Could use this one instead if we want to make it so all the item in a tier are dropped before getting the fallback reward
    # owned_cosmetic_ids = db.session.query(CosmeticsOwnership.cosmetics_id).filter_by(user_id=user.id)
    # item = Cosmetics.query.filter(
    #     and_(Cosmetics.tier == item_rarity.tier, ~Cosmetics.id.in_(owned_cosmetic_ids))
    # ).order_by(random_func).all()
    
    item = Cosmetics.query.filter_by(tier=item_rarity.tier).order_by(random_func).first()
    if not item:
        user_coins.coins += dupe_refund[item_rarity.tier]
        db.session.commit()
        return jsonify({
            "message": "No items available in this tier",
            "tier": item_rarity.tier.name,
            "refund": dupe_refund[item_rarity.tier],
            "coins": user_coins.coins
        }), 200
    
    
    if CosmeticsOwnership.query.filter_by(user_id=user.id,cosmetics_id=item.id).first():
        # User already owns this item, refund coins
        user_coins.coins += dupe_refund[item.tier]
        db.session.commit()
        return jsonify({
            "cosmetic": item.to_json(),
            "refund": dupe_refund[item.tier],
            "coins": user_coins.coins,
        }), 200
    
    db.session.add(CosmeticsOwnership(
        user_id=user.id,
        cosmetics_id=item.id
    ))
    db.session.commit()
    
    return jsonify({
        "cosmetic": item.to_json(),
        "coins": user_coins.coins
    }), 200
    
@crates_bp.route("/shop", methods=["GET"])
@login_required()
def get_crates(user):
    crates = Crate.query.order_by(Crate.price).all()
    return jsonify([
        {
            "name": crate.name,
            "description": crate.description,
            "image": crate.image,
            "price": crate.price,
            "items": [
                {
                    "tier": item.tier.name,
                    "weight": item.weight/crate.total_weight,
                } for item in crate.items
            ]
        }
        for crate in crates]
    ), 200
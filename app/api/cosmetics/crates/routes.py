import random

from flask import Blueprint, request, jsonify
from sqlalchemy import and_

from models.db import db
from models.cosmetics import Cosmetics, CosmeticsOwnership, UserCoins
from api.account.auth import login_required

crates_bp = Blueprint("crates_bp", __name__)

@crates_bp.route("/buy", methods=["POST"])
@login_required
def buy_crate(user):
    data = request.get_json()
    crate_name = data.get("name")
    crate_price = data.get("price")
    crate_percentages = data.get("percentages")
    crate_coin_min = data.get("coinsMin", 0)
    crate_coin_max = data.get("coinsMax", 0)

    if crate_price is None or crate_percentages is None:
        return jsonify({"message": "Missing crate information"}), 403

    user_coins = UserCoins.query.filter_by(user_id=user.id).first()
    if not user_coins or user_coins.coins < crate_price:
        return jsonify({"message": "Not enough coins to purchase this crate"}), 403

    # Roll outcome
    roll = random.random()
    cumulative = 0
    result_tier = "COINS"  # Default in case none match

    for tier, chance in crate_percentages.items():
        cumulative += chance
        if roll <= cumulative:
            result_tier = tier
            break

    reward = None
    duplicate = False

    if result_tier == "COINS":
        reward = random.randint(crate_coin_min, crate_coin_max)
        user_coins.coins += reward
    else:
        owned_cosmetic_ids = db.session.query(CosmeticsOwnership.cosmetics_id).filter_by(user_id=user.id)
        possible_cosmetics = Cosmetics.query.filter(
            and_(Cosmetics.tier == result_tier, ~Cosmetics.id.in_(owned_cosmetic_ids))
        ).all()

        if not possible_cosmetics:
            # User already owns all cosmetics in this tier
            duplicate = True
            # Duplicate compensation based on tier (percentage of crate price)
            duplicate_returns = {
                "COMMON": 0.05,
                "UNCOMMON": 0.15,
                "RARE": 0.3,
                "EPIC": 0.7,
                "LEGENDARY": 1.6,
            }
            reward = int(crate_price * duplicate_returns.get(result_tier, 0.01))
            user_coins.coins += reward
        else:
            cosmetic = random.choice(possible_cosmetics)
            ownership = CosmeticsOwnership(user_id=user.id, cosmetics_id=cosmetic.id)
            db.session.add(ownership)
            reward = cosmetic

    user_coins.coins -= crate_price
    db.session.add(user_coins)
    db.session.commit()

    return jsonify({
        "cosmetic": reward.to_json() if hasattr(reward, 'to_json') else None,
        "coins": reward if isinstance(reward, int) else None,
        "duplicate": duplicate,
        "tier": result_tier,
    }), 200
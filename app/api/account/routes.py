from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt

from models.db import db
from models.user import User, UserCosmetics
from api.account.auth import generate_token,login_required

bcrypt = Bcrypt()
account_bp = Blueprint("account",__name__)

########################################################
#                       AUTH                           #
########################################################
@account_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": "Username already exists"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.flush()
    
    new_cosmetics = UserCosmetics(user_id=new_user.id)
    db.session.add(new_cosmetics)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 200

@account_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()

    if user and bcrypt.check_password_hash(user.password, password):
        # Generate JWT token if credentials are valid
        token = generate_token(user)
        return jsonify({
            "message": "Login successful",
            "token": token
        }), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401
    
########################################################
#                      PROFILE                         #
########################################################

@account_bp.route("/profile",methods=["GET"])
@login_required
def get_profile(user):
    data = request.args
    username = data.get("username")
    if username:
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_json()),200

# Delete account route
@account_bp.route("/delete", methods=["DELETE"])
@login_required
def delete_account(user):
    # Delete the user from the database
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted successfully"}), 200

# Avatar customize route
@account_bp.route("/profile/avatar-customize", methods=["PUT"])
@login_required
def avatar_customize(user):
    data = request.get_json()
    hue = data.get("hue")
    saturation = data.get("saturation")
    brightness = data.get("brightness")

    if hue is None or saturation is None or brightness is None:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Update the user's avatar settings in the database
    user.cosmetics.hue = hue
    user.cosmetics.saturation = saturation
    user.cosmetics.brightness = brightness
    db.session.commit()
    
    return jsonify({"message": "Avatar customization updated successfully"}), 200
    
    
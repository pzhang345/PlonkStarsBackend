from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt

from models.db import db
from models.user import Cosmetics, CosmeticsOwnership, User, UserCosmetics, Cosmetic_Type
from models.map import GameMap
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
    face = data.get("face")
    body = data.get("body")
    hat = data.get("hat")

    if hue is None or saturation is None or brightness is None:
        return jsonify({"error": "Missing required parameters"}), 400

    # Helper to check ownership
    def owns_cosmetic(image_name):
        if not image_name:
            return True  # Null (unequipped) is always allowed
        return db.session.query(CosmeticsOwnership).filter_by(
            user_id=user.id,
            cosmetics_image=image_name
        ).first() is not None

    # Check ownership of each equipped item
    if face and not owns_cosmetic(face["image"]):
        return jsonify({"error": f"You do not own the face cosmetic"}), 403
    if body and not owns_cosmetic(body["image"]):
        return jsonify({"error": f"You do not own the body cosmetic"}), 403
    if hat and not owns_cosmetic(hat["image"]):
        return jsonify({"error": f"You do not own the hat cosmetic"}), 403

    # Update user cosmetics
    user.cosmetics.hue = hue
    user.cosmetics.saturation = saturation
    user.cosmetics.brightness = brightness
    user.cosmetics.face = face["image"] if face else None
    user.cosmetics.body = body["image"] if body else None
    user.cosmetics.hat = hat["image"] if hat else None

    db.session.commit()
    return jsonify({"message": "Avatar changes saved!"}), 200


@account_bp.route("/profile/cosmetics", methods=["GET"])
@login_required
def get_cosmetic_ownership(user):

    # Create subquery
    owned_cosmetic_images_subq = db.session.query(
        CosmeticsOwnership.cosmetics_image
    ).filter_by(user_id=user.id).subquery()

    # Use select() when using in_()
    owned_select = db.select(owned_cosmetic_images_subq)

    # Owned cosmetics by type
    owned_faces = Cosmetics.query.filter(
        Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.FACE
    ).all()

    owned_body = Cosmetics.query.filter(
        Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.BODY
    ).all()

    owned_hats = Cosmetics.query.filter(
        Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.HAT
    ).all()

    # Unowned cosmetics by type
    unowned_faces = Cosmetics.query.filter(
        ~Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.FACE
    ).all()

    unowned_body = Cosmetics.query.filter(
        ~Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.BODY
    ).all()

    unowned_hats = Cosmetics.query.filter(
        ~Cosmetics.image.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.HAT
    ).all()
    
    return jsonify({
        "owned_faces": [cosmetic.to_json() for cosmetic in owned_faces],
        "unowned_faces": [cosmetic.to_json() for cosmetic in unowned_faces],
        "owned_bodies": [cosmetic.to_json() for cosmetic in owned_body],
        "unowned_bodies": [cosmetic.to_json() for cosmetic in unowned_body],
        "owned_hats": [cosmetic.to_json() for cosmetic in owned_hats],
        "unowned_hats": [cosmetic.to_json() for cosmetic in unowned_hats],
    }), 200


    
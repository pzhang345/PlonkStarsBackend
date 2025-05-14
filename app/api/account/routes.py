from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt

from models.db import db
from models.user import User
from models.cosmetics import Cosmetics, CosmeticsOwnership, UserCosmetics, Cosmetic_Type
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
    cosmetic = user.cosmetics

    # Helper to check ownership
    def owns_cosmetic(image_name):
        if not image_name:
            return None  # Null (unequipped) is always allowed
        item = Cosmetics.query.join(CosmeticsOwnership, Cosmetics.id == CosmeticsOwnership.cosmetics_id).filter(
            CosmeticsOwnership.user_id==user.id,
            Cosmetics.image==image_name
        ).first()
        
        return item.id if item else -1

    # Check ownership of each equipped item
    face_cos = owns_cosmetic(face["image"]) if face else None
    body_cos = owns_cosmetic(body["image"]) if body else None
    hat_cos = owns_cosmetic(hat["image"]) if hat else None
    if face_cos == -1:
        return jsonify({"error": f"You do not own the face cosmetic"}), 403
    if body_cos == -1:
        return jsonify({"error": f"You do not own the body cosmetic"}), 403
    if hat_cos == -1:
        return jsonify({"error": f"You do not own the hat cosmetic"}), 403

    # Update user cosmetics
    cosmetic.hue = user.cosmetics.hue if hue == None else hue
    cosmetic.saturation = user.cosmetics.saturation if saturation == None else saturation
    cosmetic.brightness = user.cosmetics.brightness if brightness == None else brightness
    cosmetic.face = face_cos
    cosmetic.body = body_cos
    cosmetic.hat = hat_cos

    db.session.commit()
    return jsonify({"message": "Avatar changes saved!"}), 200


@account_bp.route("/profile/cosmetics", methods=["GET"])
@login_required
def get_cosmetic_ownership(user):

    # Create subquery
    owned_cosmetic_images_subq = db.session.query(
        CosmeticsOwnership.cosmetics_id
    ).join(Cosmetics, CosmeticsOwnership.cosmetics_id == Cosmetics.id).filter_by(user_id=user.id).subquery()

    # Use select() when using in_()
    owned_select = db.select(owned_cosmetic_images_subq)

    # Owned cosmetics by type
    owned_faces = Cosmetics.query.filter(
        Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.FACE
    )

    owned_body = Cosmetics.query.filter(
        Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.BODY
    )

    owned_hats = Cosmetics.query.filter(
        Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.HAT
    )

    # Unowned cosmetics by type
    unowned_faces = Cosmetics.query.filter(
        ~Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.FACE
    )

    unowned_body = Cosmetics.query.filter(
        ~Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.BODY
    )

    unowned_hats = Cosmetics.query.filter(
        ~Cosmetics.id.in_(owned_select),
        Cosmetics.type == Cosmetic_Type.HAT
    )
    
    return jsonify({
        "owned_faces": [cosmetic.to_json() for cosmetic in owned_faces],
        "unowned_faces": [cosmetic.to_json() for cosmetic in unowned_faces],
        "owned_bodies": [cosmetic.to_json() for cosmetic in owned_body],
        "unowned_bodies": [cosmetic.to_json() for cosmetic in unowned_body],
        "owned_hats": [cosmetic.to_json() for cosmetic in owned_hats],
        "unowned_hats": [cosmetic.to_json() for cosmetic in unowned_hats],
    }), 200


    
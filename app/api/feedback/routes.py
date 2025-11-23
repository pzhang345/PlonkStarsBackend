from flask import Blueprint, request, jsonify

from models.db import db
from api.account.auth import get_user_from_token
from models.feedback import Feedback

feedback_bp = Blueprint("feedback",__name__)

@feedback_bp.route("/submit", methods=["POST"])
def submit_feedback():
    token = request.headers.get("Authorization")
    user = get_user_from_token(token)
    
    data = request.get_json()
    message = data.get("message")

    if message == None or len(message) > 2048:
        return jsonify({"error": "invalid message"}), 400

    new_feedback = Feedback(user_id=user.id if user else None, message=message)
    db.session.add(new_feedback)
    db.session.commit()

    return jsonify({"message": "Feedback submitted successfully"}), 200
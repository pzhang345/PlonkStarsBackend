from functools import wraps
import jwt
from datetime import datetime, timedelta
import pytz
from flask import request, jsonify

from config import Config
from models.user import User

JWT_SECRET_KEY = Config.SECRET_KEY

def generate_token(user):
    payload = {
        "sub": str(user.id),
        "name": user.username,
        "exp": datetime.now(tz=pytz.utc) + timedelta(days=30) 
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")
    return token

def decode(token):
    token = token.replace("Bearer ", "")
    decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"], verify=True)
    return decoded_token

def get_user_from_token(token):
    if not token:
        return None
    try:
        decoded_token = decode(token)
        # Extract the user ID (sub) from the decoded token
        user_id = decoded_token.get("sub")

        if not user_id:
            return None
        
    except Exception as e:
        return None
    
    return User.query.filter_by(id=int(user_id)).first()

# Decorator to check for JWT token
def login_required(allow_demo=False):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = request.headers.get("Authorization")
            if token == "demo":
                if allow_demo:
                    user = User.query.filter_by(username="demo").first()
                    return f(user, *args, **kwargs)
                else:
                    return jsonify({"error": "login required"}), 403
            
            user = get_user_from_token(token)
            if not user:
                return jsonify({"error": "login required"}), 403
            return f(user, *args, **kwargs)
        return decorated_function
    return decorator

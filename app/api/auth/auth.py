from functools import wraps
import jwt
import datetime
from flask import request, jsonify
from config import Config
from models.user import User

# Secret key for JWT (same as in config)
JWT_SECRET_KEY = Config.JWT_SECRET_KEY

# Function to generate JWT token
def generate_token(user):
    payload = {
        'sub': str(user.id),  # Subject: typically the user ID
        'exp': datetime.datetime.now() + datetime.timedelta(days=1)  # Token expiration time (e.g., 1 day)
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')  # Using HS256 algorithm
    return token


# Decorator to check for JWT token
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token is missing!'}), 403

        try:
            # Remove "Bearer " prefix from token
            token = token.replace('Bearer ', '')
            # Decode the token
            print(token)
            decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
            print(decoded_token)

            # Extract the user ID (sub) from the decoded token
            current_user_id = decoded_token.get('sub')

            if not current_user_id:
                return jsonify({'message': 'Invalid token! No user ID (sub) found in token'}), 403
            
        except Exception as e:
            return jsonify({'message': 'Token is invalid or expired!'}), 403

        # Check if the user exists in the database
        user = User.query.filter_by(id=int(current_user_id)).first()
        
        if not user:
            return jsonify({'message': 'User not found in database'}), 404

        return f(user, *args, **kwargs)
    return decorated_function

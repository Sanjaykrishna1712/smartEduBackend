from functools import wraps
from flask import request, jsonify, make_response
from flask_jwt_extended import JWTManager, create_access_token, verify_jwt_in_request, get_jwt
from datetime import datetime, timedelta
import jwt
import os

jwt_manager = JWTManager()

def generate_token(user_data, expires_delta=timedelta(hours=24)):
    """Generate JWT token for user"""
    payload = {
        'user_id': user_data.get('user_id'),
        'email': user_data.get('email'),
        'role': user_data.get('role', 'student'),
        'name': user_data.get('name', ''),
        'school_code': user_data.get('school_code', ''),
        'exp': datetime.utcnow() + expires_delta,
        'iat': datetime.utcnow()
    }
    
    secret_key = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
    token = jwt.encode(payload, secret_key, algorithm='HS256')
    return token

def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token is missing',
                'message': 'Authentication required'
            }), 401
        
        try:
            secret_key = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
            data = jwt.decode(token, secret_key, algorithms=['HS256'])
            request.current_user = data
        except jwt.ExpiredSignatureError:
            return jsonify({
                'success': False,
                'error': 'Token has expired',
                'message': 'Please login again'
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                'success': False,
                'error': 'Invalid token',
                'message': 'Authentication failed'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

def role_required(required_role):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated_function(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({
                    'success': False,
                    'error': 'Authentication required'
                }), 401
            
            user_role = request.current_user.get('role', 'student')
            
            # Check role hierarchy
            role_hierarchy = {
                'superadmin': 4,
                'admin': 3,
                'principal': 2,
                'teacher': 1,
                'student': 0
            }
            
            current_role_level = role_hierarchy.get(user_role, 0)
            required_role_level = role_hierarchy.get(required_role, 0)
            
            if current_role_level < required_role_level:
                return jsonify({
                    'success': False,
                    'error': f'Insufficient permissions. Required role: {required_role}',
                    'message': 'You do not have permission to access this resource'
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
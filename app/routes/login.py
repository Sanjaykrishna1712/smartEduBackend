from flask import Blueprint, request, jsonify, make_response
from datetime import datetime, timedelta
import os
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
import re

# Create blueprint
login_bp = Blueprint('login', __name__)

# JWT Secret Key (use environment variable in production)
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# MongoDB connection setup
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')

def get_mongo_client():
    """Get MongoDB client"""
    return MongoClient(MONGO_URI)

def get_db():
    """Get MongoDB database"""
    client = get_mongo_client()
    return client[DATABASE_NAME]

def close_mongo_client(client):
    """Close MongoDB connection"""
    if client:
        client.close()

def serialize_document(doc):
    """Convert ObjectId to string for JSON serialization"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add("Access-Control-Allow-Origin", "https://smartedufrontend.onrender.com")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    """Check if password matches hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def generate_token(user_id, user_role, additional_data=None):
    """Generate JWT token with additional user data"""
    payload = {
        'user_id': user_id,
        'user_role': user_role,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    
    # Add additional data to payload if provided
    if additional_data:
        payload.update(additional_data)
    
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception as e:
        print(f"❌ Error decoding token: {e}")
        return None

# ==================== TEACHER LOGIN ====================

@login_bp.route('/auth/teacher-login', methods=['POST', 'OPTIONS'])
def teacher_login():
    """Handle teacher login with MongoDB verification"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for teacher-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        print("=== TEACHER LOGIN DEBUG START ===")
        
        # Get the raw request data
        raw_data = request.get_data(as_text=True)
        print(f"📥 Raw request data: {raw_data}")
        
        data = request.get_json()
        print(f"📥 Parsed JSON data: {data}")
        
        email = data.get('email', '').lower().strip() if data else ''
        password = data.get('password', '').strip() if data else ''
        
        print(f"📧 Email received: {email}")
        print(f"🔑 Password received: {password}")
        
        if not email or not password:
            print("❌ Missing email or password")
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        if not validate_email(email):
            print("❌ Invalid email format")
            response = jsonify({
                'success': False,
                'error': 'Invalid email format'
            })
            return add_cors_headers(response), 400
        
        print("🔄 Attempting MongoDB connection...")
        try:
            client = get_mongo_client()
            print("✅ MongoDB client created")
            db = get_db()
            print(f"✅ Database accessed: {DATABASE_NAME}")
            collection = db.teachers
            print(f"✅ Collection accessed: teachers")
            
            # Test if collection exists
            collections = db.list_collection_names()
            print(f"📋 Available collections: {collections}")
            
        except Exception as mongo_error:
            print(f"❌ MongoDB connection error: {str(mongo_error)}")
            response = jsonify({
                'success': False,
                'error': f'Database connection error: {str(mongo_error)}'
            })
            return add_cors_headers(response), 500
        
        print(f"🔍 Searching for teacher with email: {email}")
        teacher = collection.find_one({'email': email})
        
        if not teacher:
            print(f"❌ No teacher found for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        print(f"✅ Teacher found: {teacher.get('name', 'Unknown')}")
        
        # Check if teacher is active
        is_active = teacher.get('is_active', True)
        status = teacher.get('status', '')
        print(f"📊 Teacher status - is_active: {is_active}, status: {status}")
        
        if not is_active and status != 'active':
            print(f"❌ Teacher account not active")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is not active. Please contact your school administrator.'
            })
            return add_cors_headers(response), 403
        
        stored_password = teacher.get('password', '')
        print(f"🔐 Stored password (first 5 chars): {stored_password[:5] if stored_password else 'None'}")
        print(f"🔐 Provided password (first 5 chars): {password[:5]}")
        
        if password != stored_password:
            print(f"❌ Password mismatch")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        print("✅ Password verified successfully")
        
        # Update last login
        collection.update_one(
            {'_id': teacher['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )
        print("✅ Last login updated")
        
        teacher_data = serialize_document(teacher)
        client.close()
        print("✅ MongoDB connection closed")
        
        # Generate token
        token_additional_data = {
            'school_id': teacher_data.get('school_id', ''),
            'school_name': teacher_data.get('school_name', ''),
            'employee_id': teacher_data.get('employee_id', ''),
            'name': teacher_data.get('name', ''),
        }
        
        token = generate_token(str(teacher['_id']), 'teacher', token_additional_data)
        print("✅ JWT token generated")
        
        # Prepare response
        response_data = {
            'success': True,
            'message': 'Teacher login successful',
            'data': {
                'teacher': {
                    '_id': teacher_data['_id'],
                    'email': teacher_data['email'],
                    'name': teacher_data.get('name', ''),
                    'employee_id': teacher_data.get('employee_id', ''),
                },
                'school': {
                    'school_id': teacher_data.get('school_id', ''),
                    'school_name': teacher_data.get('school_name', ''),
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Teacher login successful for: {teacher_data['email']}")
        print("=== TEACHER LOGIN DEBUG END ===\n")
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f" ERROR in teacher login: {str(e)}")
        print(f" Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}',
            'error_type': type(e).__name__
        })
        return add_cors_headers(response), 500

# ==================== STUDENT LOGIN ====================

@login_bp.route('/auth/student-login', methods=['POST', 'OPTIONS'])
def student_login():
    """Handle student login with MongoDB verification"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for student-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Student login attempt with data: {data}")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        if not validate_email(email):
            response = jsonify({
                'success': False,
                'error': 'Invalid email format'
            })
            return add_cors_headers(response), 400
        
        client = get_mongo_client()
        db = get_db()
        collection = db.students
        
        student = collection.find_one({'email': email})
        
        if not student:
            print(f"❌ No student found for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        if not student.get('is_active', True) and student.get('status', '') != 'active':
            print(f"❌ Student account not active for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is not active. Please contact your school administrator.'
            })
            return add_cors_headers(response), 403
        
        stored_password = student.get('initial_password', '')
        
        if password != stored_password:
            print(f"❌ Password mismatch for student email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        collection.update_one(
            {'_id': student['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )
        
        student_data = serialize_document(student)
        client.close()
        
        # CRITICAL: Get school_id from student document
        school_id = student_data.get('school_id', '')
        if not school_id:
            # Try to get it from other fields
            school_id = student_data.get('school_code', '')
        
        print(f"🔑 Student school_id: {school_id}")
        print(f"🔑 Student class: {student_data.get('class', '')}")
        
        # Prepare additional data for token - MUST include school_id and class
        token_additional_data = {
            'school_id': school_id,  # This is REQUIRED!
            'school_name': student_data.get('school_name', ''),
            'student_id': student_data.get('student_id', ''),
            'name': student_data.get('name', ''),
            'roll_number': student_data.get('roll_number', ''),
            'class': student_data.get('class', ''),  # This is REQUIRED for quizzes filtering!
            'section': student_data.get('section', ''),
            'phone': student_data.get('phone', ''),
            'date_of_birth': student_data.get('date_of_birth', ''),
            'gender': student_data.get('gender', ''),
            'address': student_data.get('address', ''),
            'parent_name': student_data.get('parent_name', ''),
            'parent_phone': student_data.get('parent_phone', ''),
            'parent_email': student_data.get('parent_email', ''),
            'parent_occupation': student_data.get('parent_occupation', ''),
            'blood_group': student_data.get('blood_group', ''),
            'medical_conditions': student_data.get('medical_conditions', ''),
            'admission_date': student_data.get('admission_date', ''),
            'attendance': student_data.get('attendance', 0),
            'performance': student_data.get('performance', 0),
            'status': student_data.get('status', '')
        }
        
        # Generate token with additional data
        token = generate_token(str(student['_id']), 'student', token_additional_data)
        
        # Debug: Decode token to verify it contains school_id
        try:
            decoded = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            print(f"✅ Generated token contains school_id: {decoded.get('school_id')}")
            print(f"✅ Generated token contains class: {decoded.get('class')}")
        except:
            print("⚠️ Could not decode generated token")
        
        # Prepare comprehensive response data
        response_data = {
            'success': True,
            'message': 'Student login successful',
            'data': {
                'student': {
                    '_id': student_data['_id'],
                    'email': student_data['email'],
                    'name': student_data.get('name', ''),
                    'student_id': student_data.get('student_id', ''),
                    'roll_number': student_data.get('roll_number', ''),
                    'class': student_data.get('class', ''),
                    'section': student_data.get('section', ''),
                    'school_id': school_id,  # Include in response too
                    'school_name': student_data.get('school_name', ''),
                    'phone': student_data.get('phone', ''),
                    'date_of_birth': student_data.get('date_of_birth', ''),
                    'gender': student_data.get('gender', ''),
                    'address': student_data.get('address', ''),
                    'parent_name': student_data.get('parent_name', ''),
                    'parent_phone': student_data.get('parent_phone', ''),
                    'parent_email': student_data.get('parent_email', ''),
                    'parent_occupation': student_data.get('parent_occupation', ''),
                    'blood_group': student_data.get('blood_group', ''),
                    'medical_conditions': student_data.get('medical_conditions', ''),
                    'admission_date': student_data.get('admission_date', ''),
                    'attendance': student_data.get('attendance', 0),
                    'performance': student_data.get('performance', 0),
                    'status': student_data.get('status', ''),
                    'created_by': student_data.get('created_by', ''),
                    'created_at': student_data.get('created_at', ''),
                    'updated_at': student_data.get('updated_at', ''),
                    'last_login': student_data.get('last_login', '')
                },
                'school': {
                    'school_id': school_id,
                    'school_name': student_data.get('school_name', ''),
                    'school_code': student_data.get('school_code', '')
                },
                'academic': {
                    'current_class': student_data.get('class', ''),
                    'section': student_data.get('section', ''),
                    'academic_year': datetime.now().year
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Student login successful for: {student_data['email']}")
        print(f"✅ Token generated with school_id: {school_id}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in student login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500
# ==================== SUPER ADMIN LOGIN ====================

@login_bp.route('/auth/superadmin-login', methods=['POST', 'OPTIONS'])
def superadmin_login():
    """Handle super admin login"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for superadmin-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Super admin login attempt")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        # Remove: superadmin_code = data.get('superadminCode', '').strip()
        
        if not email or not password:
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        SUPER_ADMINS = {
            'admin@gmail.com': {
                'password': 'admin',
                'name': 'System Administrator',
                'superadmin_code': 'SUPER001',
                'role': 'superadmin',
                'permissions': ['*']
            }
        }
        
        if email not in SUPER_ADMINS:
            print(f"❌ No super admin found for email: {email}")
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        admin_info = SUPER_ADMINS[email]
        
        # REMOVE superadmin code check since frontend won't send it
        # if superadmin_code and superadmin_code != admin_info['superadmin_code']:
        #     print(f"❌ Super admin code mismatch for: {email}")
        #     response = jsonify({
        #         'success': False,
        #         'error': 'Invalid super admin code'
        #     })
        #     return add_cors_headers(response), 401
        
        if password != admin_info['password']:
            print(f"❌ Password mismatch for super admin: {email}")
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        # Prepare additional data for token
        token_additional_data = {
            'name': admin_info['name'],
            'superadmin_code': admin_info['superadmin_code'],
            'permissions': admin_info['permissions']
        }
        
        # Generate token with additional data
        token = generate_token(f"superadmin_{email}", 'superadmin', token_additional_data)
        
        # Prepare comprehensive response data
        response_data = {
            'success': True,
            'message': 'Super admin login successful',
            'data': {
                'superadmin': {
                    'email': email,
                    'name': admin_info['name'],
                    'superadmin_code': admin_info['superadmin_code'],
                    'role': admin_info['role'],
                    'permissions': admin_info['permissions']
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Super admin login successful for: {email}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in super admin login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== PRINCIPAL LOGIN ====================

@login_bp.route('/auth/principal-login', methods=['POST', 'OPTIONS'])
def principal_login():
    """Handle principal login with MongoDB verification"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for principal-login")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        print(f"📥 Principal login attempt with data: {data}")
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '').strip()
        # Remove: principal_code = data.get('principalCode', '').strip()
        
        if not email or not password:
            response = jsonify({
                'success': False,
                'error': 'Email and password are required'
            })
            return add_cors_headers(response), 400
        
        if not validate_email(email):
            response = jsonify({
                'success': False,
                'error': 'Invalid email format'
            })
            return add_cors_headers(response), 400
        
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        # SIMPLIFY query - only use email
        query = {'email': email}
        # Remove: if principal_code: query = {'$or': [{'email': email}, {'principal_code': principal_code}]}
        
        school_contact = collection.find_one(query)
        
        if not school_contact:
            print(f"❌ No school contact found for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'No account found with these credentials'
            })
            return add_cors_headers(response), 404
        
        if not school_contact.get('is_approved', False):
            print(f"❌ Account not approved for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is pending approval. Please contact support.'
            })
            return add_cors_headers(response), 403
        
        if not school_contact.get('is_active', False):
            print(f"❌ Account not active for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Your account is not active. Please contact support.'
            })
            return add_cors_headers(response), 403
        
        stored_password = school_contact.get('initial_password_plain', '')
        stored_hashed_password = school_contact.get('hashed_password', '')
        
        password_valid = False
        
        if stored_hashed_password:
            password_valid = check_password(password, stored_hashed_password)
        elif stored_password:
            password_valid = (password == stored_password)
        else:
            password_valid = False
        
        if not password_valid:
            print(f"❌ Password mismatch for email: {email}")
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid credentials'
            })
            return add_cors_headers(response), 401
        
        collection.update_one(
            {'_id': school_contact['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )
        
        principal = serialize_document(school_contact)
        client.close()
        
        school_id = principal.get('school_id', '')
        if not school_id:
            school_id = principal.get('school_code', '')
        if not school_id and principal.get('school_name', ''):
            school_name = principal['school_name']
            school_id = ''.join(word[:3].upper() for word in school_name.split()[:2])
        
        # Prepare additional data for token
        token_additional_data = {
            'school_id': school_id,
            'school_name': principal.get('school_name', ''),
            'principal_name': principal.get('principal_name', ''),
            'principal_code': principal.get('principal_code', ''),
            'school_type': principal.get('school_type', ''),
            'student_count': principal.get('student_count', ''),
            'address': principal.get('address', ''),
            'city': principal.get('city', ''),
            'state': principal.get('state', ''),
            'country': principal.get('country', ''),
            'accepted_plan': principal.get('accepted_plan', 'basic')
        }
        
        # Generate token with additional data
        token = generate_token(str(school_contact['_id']), 'principal', token_additional_data)
        
        response_data = {
            'success': True,
            'message': 'Login successful',
            'data': {
                'principal': {
                    '_id': principal['_id'],
                    'email': principal['email'],
                    'principal_name': principal['principal_name'],
                    'school_name': principal['school_name'],
                    'principal_code': principal.get('principal_code', ''),
                    'school_id': school_id
                },
                'school': {
                    'school_id': school_id,
                    'school_name': principal['school_name'],
                    'school_type': principal['school_type'],
                    'student_count': principal.get('student_count', ''),
                    'address': principal.get('address', ''),
                    'city': principal.get('city', ''),
                    'state': principal.get('state', ''),
                    'country': principal.get('country', ''),
                    'is_approved': principal['is_approved'],
                    'is_active': principal['is_active'],
                    'accepted_plan': principal.get('accepted_plan', 'basic')
                },
                'token': token,
                'expires_in': JWT_EXPIRATION_HOURS * 3600
            }
        }
        
        print(f"✅ Principal login successful for: {principal['email']}, school_id: {school_id}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in principal login: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Login failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== TOKEN VERIFICATION ====================

@login_bp.route('/auth/verify-token', methods=['POST', 'OPTIONS'])
def verify_token():
    """Verify JWT token"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for verify-token")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        
        if not token:
            response = jsonify({
                'success': False,
                'error': 'Token is required'
            })
            return add_cors_headers(response), 400
        
        payload = decode_token(token)
        
        if not payload:
            response = jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            })
            return add_cors_headers(response), 401
        
        response_data = {
            'success': True,
            'message': 'Token is valid',
            'data': {
                'user_id': payload.get('user_id'),
                'user_role': payload.get('user_role'),
                'expires_at': payload.get('exp'),
                'additional_data': {k: v for k, v in payload.items() if k not in ['user_id', 'user_role', 'exp', 'iat']}
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error verifying token: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Token verification failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== LOGOUT ====================

@login_bp.route('/auth/logout', methods=['POST', 'OPTIONS'])
def logout():
    """Handle logout (invalidate token on client side)"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for logout")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        response_data = {
            'success': True,
            'message': 'Logout successful'
        }
        
        print("✅ User logged out successfully")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in logout: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Logout failed: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== CHANGE PASSWORD ====================

@login_bp.route('/auth/change-password', methods=['POST', 'OPTIONS'])
def change_password():
    """Change password for principals"""
    if request.method == 'OPTIONS':
        print("🔄 Handling OPTIONS preflight request for change-password")
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not token or not current_password or not new_password:
            response = jsonify({
                'success': False,
                'error': 'All fields are required'
            })
            return add_cors_headers(response), 400
        
        if len(new_password) < 8:
            response = jsonify({
                'success': False,
                'error': 'New password must be at least 8 characters long'
            })
            return add_cors_headers(response), 400
        
        payload = decode_token(token)
        if not payload or payload.get('user_role') != 'principal':
            response = jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            })
            return add_cors_headers(response), 401
        
        user_id = payload.get('user_id')
        
        client = get_mongo_client()
        db = get_db()
        collection = db.school_contacts
        
        principal = collection.find_one({'_id': ObjectId(user_id)})
        
        if not principal:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'User not found'
            })
            return add_cors_headers(response), 404
        
        stored_password = principal.get('initial_password', '')
        stored_hashed_password = principal.get('hashed_password', '')
        
        current_password_valid = False
        
        if stored_hashed_password:
            current_password_valid = check_password(current_password, stored_hashed_password)
        elif stored_password:
            current_password_valid = (current_password == stored_password)
        
        if not current_password_valid:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Current password is incorrect'
            })
            return add_cors_headers(response), 401
        
        new_hashed_password = hash_password(new_password)
        
        collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'hashed_password': new_hashed_password,
                'password_changed_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        response_data = {
            'success': True,
            'message': 'Password changed successfully'
        }
        
        print(f"✅ Password changed for user: {user_id}")
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error changing password: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to change password: {str(e)}'
        })
        return add_cors_headers(response), 500

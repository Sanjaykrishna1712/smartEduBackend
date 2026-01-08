# app/routes/students.py
from flask import Blueprint, request, jsonify, make_response, send_file
from datetime import datetime, timedelta
import os
import re
import bcrypt
import jwt
import pandas as pd
from io import BytesIO
from bson import ObjectId
from pymongo import MongoClient
import uuid
import math
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename

# Create blueprint
students_bp = Blueprint('students', __name__)

# Configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'

# Email configuration
EMAIL_HOST = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('SMTP_PORT', 587))
EMAIL_USER = os.getenv('SMTP_USERNAME', '')
EMAIL_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', '')
FROM_NAME = os.getenv('FROM_NAME', 'School Admin')

# Allowed file extensions for bulk upload
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
UPLOAD_FOLDER = 'uploads/students'

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# MongoDB connection functions
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

# JWT Token functions
def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Helper functions
def serialize_document(doc):
    """Convert ObjectId to string for JSON serialization"""
    if doc and '_id' in doc:
        doc['_id'] = str(doc['_id'])
    
    # Convert datetime objects to string
    for key, value in doc.items():
        if isinstance(value, datetime):
            doc[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            doc[key] = str(value)
    
    return doc

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add("Access-Control-Allow-Origin", "http://localhost:5173")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Requested-With")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    response.headers.add("Access-Control-Expose-Headers", "Content-Disposition")
    return response

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def generate_student_id(school_code=None):
    """Generate unique student ID"""
    if school_code:
        return f"{school_code}-STU{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
    return f"STU{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"

def generate_password():
    """Generate random password"""
    return str(uuid.uuid4().hex[:8])

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def send_welcome_email(student_email, student_name, student_id, password, school_name="Our School"):
    """Send welcome email to student with credentials"""
    try:
        if not EMAIL_USER or not EMAIL_PASSWORD:
            print("📧 Email credentials not configured")
            return False
        
        subject = f"Welcome to {school_name} - Student Account Created"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4f46e5; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }}
                .credentials {{ background-color: #e8f4fd; padding: 15px; border-left: 4px solid #4f46e5; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
                .important {{ color: #d32f2f; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to {school_name}</h1>
                </div>
                <div class="content">
                    <p>Dear {student_name},</p>
                    <p>Your student account has been successfully created. Here are your login credentials:</p>
                    
                    <div class="credentials">
                        <h3>Your Login Details:</h3>
                        <p><strong>Student ID:</strong> {student_id}</p>
                        <p><strong>Email:</strong> {student_email}</p>
                        <p><strong>Temporary Password:</strong> {password}</p>
                    </div>
                    
                    <p class="important">Important: Please change your password after your first login.</p>
                    
                    <p>You can access your account at: <a href="http://localhost:5173/login">School Portal</a></p>
                    
                    <p>If you have any questions or need assistance, please contact the school administration.</p>
                    
                    <p>Best regards,<br>
                    {school_name} Administration</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>" 
        msg['To'] = student_email
        
        # Attach HTML version
        part2 = MIMEText(html_content, 'html')
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        
        print(f"📧 Email sent to {student_email}")
        return True
    except Exception as e:
        print(f"Error sending email to {student_email}: {str(e)}")
        return False

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_school_id_from_request():
    """Extract school_id from request with multiple fallbacks"""
    school_id = None
    
    # 1. Check Authorization header first (most reliable)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        payload = decode_token(token)
        if payload:
            school_id = payload.get('school_id', '').strip()
    
    # 2. Check query parameter
    if not school_id:
        school_id = request.args.get('school_id', '').strip()
    
    # 3. Check JSON body
    if not school_id and request.method in ['POST', 'PUT', 'DELETE']:
        try:
            data = request.get_json(silent=True) or {}
            school_id = data.get('school_id', '').strip()
        except:
            pass
    
    # 4. Check form data
    if not school_id and request.method == 'POST':
        school_id = request.form.get('school_id', '').strip()
    
    print(f"🔍 Extracted school_id: {school_id}")
    return school_id

# ==================== GET ALL STUDENTS ====================
@students_bp.route('/students', methods=['GET', 'OPTIONS'])
def get_all_students():
    """Get all students with filtering and pagination"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '').strip()
        student_class = request.args.get('class', '').strip()
        section = request.args.get('section', '').strip()
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        
        # Get school_id
        school_id = get_school_id_from_request()
        
        print(f"📋 Fetching students for school: {school_id}")
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required. Provide ?school_id=YOUR_SCHOOL_ID or include in Authorization token.'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query - MUST include school_id
        query = {'school_id': school_id}
        
        # Apply filters
        if search and search != 'undefined' and search != '':
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'roll_number': {'$regex': search, '$options': 'i'}},
                {'student_id': {'$regex': search, '$options': 'i'}},
                {'parent_name': {'$regex': search, '$options': 'i'}},
                {'parent_phone': {'$regex': search, '$options': 'i'}}
            ]
        
        if status and status != 'undefined' and status != 'all' and status != '':
            query['status'] = status
        
        if student_class and student_class != 'undefined' and student_class != 'all' and student_class != '':
            query['class'] = student_class
        
        if section and section != 'undefined' and section != 'all' and section != '':
            query['section'] = section
        
        print(f"🔍 MongoDB query: {query}")
        
        # Get total count
        total = db.students.count_documents(query)
        print(f"📊 Total students found: {total}")
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Define sort
        sort_direction = 1 if sort_order == 'asc' else -1
        sort_field = sort_by if sort_by in ['name', 'created_at', 'admission_date', 'roll_number'] else 'created_at'
        
        # Fetch students
        students_cursor = db.students.find(query)\
            .sort(sort_field, sort_direction)\
            .skip(skip)\
            .limit(limit)
        
        students = list(students_cursor)
        print(f"📋 Fetched {len(students)} students")
        
        # Serialize documents
        students = [serialize_document(student) for student in students]
        
        # Remove sensitive data from response
        for student in students:
            student.pop('hashed_password', None)
            student.pop('initial_password', None)
        
        client.close()
        
        response = jsonify({
            'success': True,
            'data': students,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': math.ceil(total / limit) if limit > 0 else 1
            }
        })
        
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error fetching students: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'Failed to fetch students: {str(e)}'
        }), 500

# ==================== ADD SINGLE STUDENT ====================

@students_bp.route('/students', methods=['POST', 'OPTIONS'])
def add_student():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)

    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Required fields
        required_fields = ['name', 'email', 'class', 'section']
        missing = [f for f in required_fields if not data.get(f)]
        if missing:
            return jsonify({'success': False, 'error': f"Missing fields: {', '.join(missing)}"}), 400

        email = data['email'].strip().lower()
        if not validate_email(email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400

        client = get_mongo_client()
        db = get_db()

        # Global email uniqueness
        if db.students.find_one({'email': email}):
            client.close()
            return jsonify({'success': False, 'error': 'Email already registered'}), 400

        school_id = data.get('school_id', '') or get_school_id_from_request()
        school_name = "Default School"
        school_code = "SCH"

        student_id = generate_student_id(school_code)
        password = generate_password()

        student_doc = {
            'student_id': student_id,
            'name': data['name'].strip(),
            'email': email,
            'phone': data.get('phone', ''),
            'roll_number': data.get('roll_number', student_id),
            'class': str(data['class']).strip(),
            'section': str(data['section']).strip().upper(),
            'status': data.get('status', 'active'),
            'initial_password': password,
            'school_id': school_id,
            'school_name': school_name,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

        result = db.students.insert_one(student_doc)
        client.close()

        # 🔔 SEND EMAIL (Safe)
        try:
            send_welcome_email(
                student_email=email,
                student_name=data['name'],
                student_id=student_id,
                password=password,
                school_name=school_name
            )
        except Exception as e:
            print(f"📧 Email failed for {email}: {e}")

        student_doc.pop('initial_password', None)
        student_doc['_id'] = str(result.inserted_id)

        return add_cors_headers(jsonify({
            'success': True,
            'message': 'Student added & email sent',
            'data': student_doc
        })), 201

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ==================== GET STUDENT BY ID ====================
@students_bp.route('/students/<student_id>', methods=['GET', 'OPTIONS'])
def get_student(student_id):
    """Get a specific student by ID"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        print(f"📋 Getting student {student_id}")
        
        # Get school_id
        school_id = get_school_id_from_request()
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find student with school check
        student = db.students.find_one({
            '$or': [
                {'student_id': student_id, 'school_id': school_id},
                {'_id': ObjectId(student_id) if ObjectId.is_valid(student_id) else None, 'school_id': school_id}
            ]
        })
        
        if not student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Student not found or not authorized for this school'
            }), 404
        
        # Serialize document
        student_data = serialize_document(student)
        
        # Remove sensitive data
        student_data.pop('initial_password', None)
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': student_data
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch student: {str(e)}'
        }), 500

# ==================== UPDATE STUDENT ====================
@students_bp.route('/students/<student_id>', methods=['PUT', 'OPTIONS'])
def update_student(student_id):
    """Update student information"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        # Get school_id
        school_id = get_school_id_from_request()
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find student with school check
        student = db.students.find_one({
            '$or': [
                {'student_id': student_id, 'school_id': school_id},
                {'_id': ObjectId(student_id) if ObjectId.is_valid(student_id) else None, 'school_id': school_id}
            ]
        })
        
        if not student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Student not found or not authorized for this school'
            }), 404
        
        # Prepare update data
        update_data = {}
        
        # Fields that can be updated
        update_fields = [
            'name', 'phone', 'class', 'section', 'date_of_birth', 'gender',
            'address', 'parent_name', 'parent_phone', 'parent_email',
            'parent_occupation', 'blood_group', 'medical_conditions',
            'attendance', 'performance', 'status'
        ]
        
        for field in update_fields:
            if field in data:
                update_data[field] = data[field]
        
        # Email can only be updated if not already taken in same school
        if 'email' in data:
            new_email = data['email'].strip().lower()
            if new_email != student['email']:
                existing = db.students.find_one({
                    'email': new_email,
                    'school_id': school_id,
                    '_id': {'$ne': student['_id']}
                })
                if existing:
                    client.close()
                    return jsonify({
                        'success': False,
                        'error': 'Email already exists in this school'
                    }), 400
                update_data['email'] = new_email
        
        update_data['updated_at'] = datetime.utcnow()
        
        # Update student
        result = db.students.update_one(
            {'_id': student['_id']},
            {'$set': update_data}
        )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Student updated successfully'
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update student: {str(e)}'
        }), 500

# ==================== DELETE STUDENT ====================
@students_bp.route('/students/<student_id>', methods=['DELETE', 'OPTIONS'])
def delete_student(student_id):
    """Delete a student"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get school_id
        school_id = get_school_id_from_request()
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Find student with school check
        student = db.students.find_one({
            '$or': [
                {'student_id': student_id, 'school_id': school_id},
                {'_id': ObjectId(student_id) if ObjectId.is_valid(student_id) else None, 'school_id': school_id}
            ]
        })
        
        if not student:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Student not found or not authorized for this school'
            }), 404
        
        # Delete student
        result = db.students.delete_one({'_id': student['_id']})
        
        # Update school student count
        if result.deleted_count > 0:
            db.schools.update_one(
                {'school_id': school_id},
                {'$inc': {'student_count': -1}}
            )
        
        client.close()
        
        if result.deleted_count > 0:
            return jsonify({
                'success': True,
                'message': 'Student deleted successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete student'
            }), 500
        
    except Exception as e:
        print(f"❌ Error deleting student: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete student: {str(e)}'
        }), 500

# ==================== BULK IMPORT STUDENTS ====================
@students_bp.route('/students/bulk-import', methods=['POST', 'OPTIONS'])
def bulk_import_students():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)

    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['file']
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
        df.columns = df.columns.str.strip().str.lower()

        required = ['name', 'email', 'class', 'section']
        if any(col not in df.columns for col in required):
            os.remove(filepath)
            return jsonify({'success': False, 'error': 'Missing required columns'}), 400

        client = get_mongo_client()
        db = get_db()

        success, failed = 0, 0
        errors = []

        school_id = request.form.get('school_id', '')
        school_name = "Default School"
        school_code = "SCH"

        for idx, row in df.iterrows():
            try:
                email = str(row['email']).strip().lower()
                name = str(row['name']).strip()

                if db.students.find_one({'email': email}):
                    failed += 1
                    errors.append(f"Row {idx+2}: Email exists")
                    continue

                student_id = generate_student_id(school_code)
                password = generate_password()

                student_doc = {
                    'student_id': student_id,
                    'name': name,
                    'email': email,
                    'class': str(row['class']),
                    'section': str(row['section']).upper(),
                    'status': 'active',
                    'initial_password': password,
                    'school_id': school_id,
                    'school_name': school_name,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }

                db.students.insert_one(student_doc)

                # 🔔 SEND EMAIL (Safe)
                try:
                    send_welcome_email(
                        student_email=email,
                        student_name=name,
                        student_id=student_id,
                        password=password,
                        school_name=school_name
                    )
                except Exception as e:
                    print(f"📧 Email failed for {email}: {e}")

                success += 1

            except Exception as e:
                failed += 1
                errors.append(f"Row {idx+2}: {str(e)}")

        os.remove(filepath)
        client.close()

        return jsonify({
            'success': True,
            'message': 'Bulk import completed',
            'data': {
                'success_count': success,
                'failed_count': failed,
                'errors': errors[:10]
            }
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ==================== BULK DELETE STUDENTS ====================
@students_bp.route('/students/bulk-delete', methods=['POST', 'OPTIONS'])
def bulk_delete_students():
    """Bulk delete students"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        student_ids = data.get('student_ids', [])
        
        # Get school_id
        school_id = get_school_id_from_request()
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required'
            }), 400
        
        if not student_ids or not isinstance(student_ids, list):
            return jsonify({
                'success': False,
                'error': 'No student IDs provided'
            }), 400
        
        print(f"🗑️ Bulk deleting {len(student_ids)} students for school: {school_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Convert string IDs to ObjectId
        object_ids = []
        for sid in student_ids:
            if ObjectId.is_valid(sid):
                object_ids.append(ObjectId(sid))
        
        # Delete students with school check
        result = db.students.delete_many({
            '_id': {'$in': object_ids},
            'school_id': school_id
        })
        
        # Update school student count
        if result.deleted_count > 0:
            db.schools.update_one(
                {'school_id': school_id},
                {'$inc': {'student_count': -result.deleted_count}}
            )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {result.deleted_count} students',
            'data': {
                'deleted_count': result.deleted_count
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in bulk delete: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete students: {str(e)}'
        }), 500

# ==================== DOWNLOAD TEMPLATE ====================
@students_bp.route('/students/template', methods=['GET', 'OPTIONS'])
def download_template():
    """Download bulk import template"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Create comprehensive template data
        template_data = [
            {
                'name': 'John Doe',
                'email': 'john.doe@school.edu',
                'class': '10',
                'section': 'A',
                'roll_number': '2024001',
                'phone': '+1234567890',
                'date_of_birth': '2008-05-15',
                'gender': 'male',
                'address': '123 Main Street',
                'parent_name': 'Mr. John Doe Sr.',
                'parent_phone': '+1234567890',
                'parent_email': 'parent@email.com',
                'parent_occupation': 'Engineer',
                'blood_group': 'O+',
                'medical_conditions': 'None',
                'admission_date': '2024-01-15',
                'attendance': 95.5,
                'performance': 88.7,
                'status': 'active'
            },
            {
                'name': 'Jane Smith',
                'email': 'jane.smith@school.edu',
                'class': '11',
                'section': 'B',
                'roll_number': '2024002',
                'phone': '+1987654321',
                'date_of_birth': '2007-03-20',
                'gender': 'female',
                'address': '456 Oak Avenue',
                'parent_name': 'Mrs. Jane Smith',
                'parent_phone': '+1987654321',
                'parent_email': 'parent2@email.com',
                'parent_occupation': 'Teacher',
                'blood_group': 'A+',
                'medical_conditions': 'Asthma',
                'admission_date': '2024-01-15',
                'attendance': 92.3,
                'performance': 91.2,
                'status': 'active'
            }
        ]
        
        # Create DataFrame
        df = pd.DataFrame(template_data)
        
        # Create Excel file with instructions
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Add instructions sheet
            instructions_data = [
                ['IMPORTANT: Column names MUST be lowercase as shown in the template'],
                ['REQUIRED COLUMNS: name, email, class, section'],
                ['OPTIONAL COLUMNS: roll_number, phone, date_of_birth, gender, address, parent_name, parent_phone, parent_email, parent_occupation, blood_group, medical_conditions, admission_date, attendance, performance, status'],
                [''],
                ['VALID VALUES:'],
                ['- gender: male, female, other'],
                ['- status: active, inactive, graduated, transferred'],
                ['- blood_group: A+, A-, B+, B-, AB+, AB-, O+, O-'],
                ['- attendance, performance: numbers between 0-100'],
                ['- date_of_birth, admission_date: YYYY-MM-DD format']
            ]
            
            instructions_df = pd.DataFrame(instructions_data)
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False, header=False)
            
            # Add template sheet
            df.to_excel(writer, sheet_name='Students Template', index=False)
        
        output.seek(0)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers.set('Content-Disposition', 'attachment', filename='students_import_template.xlsx')
        
        return response
        
    except Exception as e:
        print(f"❌ Error generating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to generate template: {str(e)}'
        }), 500

# ==================== GET STUDENT STATISTICS ====================
@students_bp.route('/students/statistics', methods=['GET', 'OPTIONS'])
def get_student_statistics():
    """Get student statistics and analytics"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        print("📊 Getting student statistics")
        
        # Get school_id
        school_id = get_school_id_from_request()
        
        if not school_id:
            return jsonify({
                'success': False,
                'error': 'School ID is required'
            }), 400
        
        print(f"📊 Getting statistics for school: {school_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query - filter by school
        query = {'school_id': school_id}
        
        # Total students count
        total_students = db.students.count_documents(query)
        
        # Status counts
        active_students = db.students.count_documents({**query, 'status': 'active'})
        inactive_students = db.students.count_documents({**query, 'status': 'inactive'})
        graduated_students = db.students.count_documents({**query, 'status': 'graduated'})
        transferred_students = db.students.count_documents({**query, 'status': 'transferred'})
        
        # Count by class
        class_pipeline = [
            {'$match': query},
            {'$group': {'_id': '$class', 'count': {'$sum': 1}}},
            {'$sort': {'_id': 1}}
        ]
        class_stats = list(db.students.aggregate(class_pipeline))
        
        # Count by gender
        gender_pipeline = [
            {'$match': {**query, 'gender': {'$exists': True, '$ne': ''}}},
            {'$group': {'_id': '$gender', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        gender_stats = list(db.students.aggregate(gender_pipeline))
        
        # Average attendance and performance
        stats_pipeline = [
            {'$match': query},
            {'$group': {
                '_id': None,
                'avg_attendance': {'$avg': '$attendance'},
                'avg_performance': {'$avg': '$performance'},
                'top_performers': {
                    '$sum': {
                        '$cond': [{'$gte': ['$performance', 90]}, 1, 0]
                    }
                },
                'low_performers': {
                    '$sum': {
                        '$cond': [{'$lt': ['$performance', 50]}, 1, 0]
                    }
                }
            }}
        ]
        performance_stats = list(db.students.aggregate(stats_pipeline))
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'school_id': school_id,
                'total_students': total_students,
                'status_counts': {
                    'active': active_students,
                    'inactive': inactive_students,
                    'graduated': graduated_students,
                    'transferred': transferred_students
                },
                'class_distribution': class_stats,
                'gender_distribution': gender_stats,
                'performance_stats': performance_stats[0] if performance_stats else {}
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch statistics: {str(e)}'
        }), 500

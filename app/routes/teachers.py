# app/routes/teachers.py
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
from functools import wraps
import random
import string
from werkzeug.utils import secure_filename
import math  # Add this at the top
from flask_cors import CORS  # If using Flask-CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# Create blueprint
teachers_bp = Blueprint('teachers', __name__)

# Configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'

# Allowed file extensions for bulk upload
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
UPLOAD_FOLDER = 'uploads/teachers'

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
def send_bulk_import_emails(teachers):
    """Send email notifications to imported teachers"""
    
    # Email configuration (configure these in environment variables)
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', 'your-email@gmail.com')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', 'your-app-password')
    FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@school.edu')
    
    print(f"📧 Preparing to send emails to {len(teachers)} teachers")
    
    try:
        # Connect to SMTP server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        sent_count = 0
        
        for teacher in teachers:
            try:
                # Create email
                msg = MIMEMultipart()
                msg['From'] = FROM_EMAIL
                msg['To'] = teacher['email']
                msg['Subject'] = 'Your Teacher Account Details - School Management System'
                
                # Email body
                body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                    <h2>Welcome to School Management System</h2>
                    
                    <p>Dear {teacher['name']},</p>
                    
                    <p>Your teacher account has been created successfully. Here are your login details:</p>
                    
                    <table style="border-collapse: collapse; width: 100%; max-width: 500px; margin: 20px 0;">
                        <tr>
                            <td style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2;">
                                <strong>Employee ID:</strong>
                            </td>
                            <td style="border: 1px solid #ddd; padding: 8px;">
                                {teacher['employee_id']}
                            </td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2;">
                                <strong>Email:</strong>
                            </td>
                            <td style="border: 1px solid #ddd; padding: 8px;">
                                {teacher['email']}
                            </td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2;">
                                <strong>Temporary Password:</strong>
                            </td>
                            <td style="border: 1px solid #ddd; padding: 8px;">
                                <strong>{teacher['temp_password']}</strong>
                            </td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2;">
                                <strong>Subject:</strong>
                            </td>
                            <td style="border: 1px solid #ddd; padding: 8px;">
                                {teacher['subject']}
                            </td>
                        </tr>
                        <tr>
                            <td style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2;">
                                <strong>School ID:</strong>
                            </td>
                            <td style="border: 1px solid #ddd; padding: 8px;">
                                {teacher['school_id']}
                            </td>
                        </tr>
                    </table>
                    
                    <p><strong>Important Security Notice:</strong></p>
                    <ul>
                        <li>This is a temporary password</li>
                        <li>Please change your password after first login</li>
                        <li>Do not share your password with anyone</li>
                        <li>For security reasons, this password will expire in 7 days</li>
                    </ul>
                    
                    <p><strong>Login URL:</strong> <a href="http://your-school-domain.com/login">Click here to login</a></p>
                    
                    <p>Best regards,<br>
                    School Administration Team</p>
                    
                    <hr style="margin-top: 30px;">
                    <p style="font-size: 12px; color: #666;">
                        This is an automated email. Please do not reply to this message.
                    </p>
                </body>
                </html>
                """
                
                msg.attach(MIMEText(body, 'html'))
                
                # Send email
                server.send_message(msg)
                sent_count += 1
                print(f"📧 Email sent to {teacher['email']}")
                
            except Exception as e:
                print(f"❌ Failed to send email to {teacher['email']}: {e}")
                continue
        
        # Close SMTP connection
        server.quit()
        
        print(f"✅ Sent {sent_count} out of {len(teachers)} emails successfully")
        return sent_count
        
    except Exception as e:
        print(f"❌ SMTP connection error: {e}")
        return 0
# JWT Token functions
def generate_token(user_id, user_role, school_id=None):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'user_role': user_role,
        'school_id': school_id,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
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

# Authentication decorator
def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({
                'success': False,
                'error': 'Token is missing'
            }), 401
        
        # Decode token
        payload = decode_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Invalid or expired token'
            }), 401
        
        # Add user info to request
        request.user_id = payload.get('user_id')
        request.user_role = payload.get('user_role')
        request.school_id = payload.get('school_id')
        
        return f(*args, **kwargs)
    return decorated

# Add CORS headers helper function
def add_cors_headers(response):
    """Add CORS headers to response - Flask-CORS already handles this, but we'll keep it for safety"""
    return response

# Validation functions (keep your existing functions)
def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate phone number format"""
    pattern = r'^[\+]?[1-9][\d]{0,15}$'
    return re.match(pattern, phone) is not None

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    """Check if password matches hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

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

def generate_employee_id(school_code, count):
    """Generate unique employee ID"""
    year = datetime.now().year
    return f"{school_code}T{year}{str(count).zfill(4)}"

def generate_temp_password():
    """Generate a temporary password"""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(random.choice(chars) for _ in range(10))

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== TEACHER REGISTRATION/ADDITION ====================

# ==================== TEACHER REGISTRATION/ADDITION WITH EMAIL ====================

@teachers_bp.route('/teachers/register', methods=['POST', 'OPTIONS'])
def register_teacher():
    """Register a new teacher (Admin/Principal only) WITH EMAIL"""
    
    # Handle OPTIONS preflight request
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        print(f"📥 Registering teacher with data: {data}")
        
        # Validate required fields
        required_fields = ['name', 'email', 'subject']
        missing_fields = [field for field in required_fields if field not in data or not str(data[field]).strip()]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Validate email
        email = data['email'].strip().lower()
        if not validate_email(email):
            return jsonify({
                'success': False,
                'error': 'Invalid email format'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if email already exists
        if db.teachers.find_one({'email': email}):
            client.close()
            return jsonify({
                'success': False,
                'error': 'Email already registered'
            }), 400
        
        # Generate employee ID
        school_code = 'SCH'  # Default school code
        teacher_count = db.teachers.count_documents({})
        employee_id = generate_employee_id(school_code, teacher_count + 1)
        
        # Generate temporary password
        temp_password = generate_temp_password()
        hashed_password = hash_password(temp_password)
        
        # Handle date_of_birth safely
        date_of_birth = None
        if data.get('date_of_birth'):
            try:
                date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }), 400
        
        # Get school_id from data or use default
        school_id = data.get('school_id', 'test_school_id')
        
        # Prepare teacher document
        teacher_doc = {
            'employee_id': employee_id,
            'school_id': school_id,
            'school_code': school_code,
            'school_name': data.get('school_name', 'IntelliLearn School'),
            'name': data['name'].strip(),
            'email': email,
            'phone': data.get('phone', '').strip(),
            'password': temp_password,
            'subject': data['subject'].strip(),
            'classes': data.get('classes', []),
            'status': data.get('status', 'active'),
            'join_date': datetime.utcnow(),
            'qualifications': data.get('qualifications', []),
            'experience': int(data.get('experience', 0)) if data.get('experience') else 0,
            'address': data.get('address', ''),
            'date_of_birth': date_of_birth,
            'emergency_contact': data.get('emergency_contact', ''),
            'gender': data.get('gender', ''),
            'blood_group': data.get('blood_group', ''),
            'designation': data.get('designation', 'Teacher'),
            'department': data.get('department', ''),
            'salary': float(data['salary']) if data.get('salary') else None,
            'role': 'teacher',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert teacher
        result = db.teachers.insert_one(teacher_doc)
        teacher_id = str(result.inserted_id)
        
        client.close()
        
        # ============ SEND EMAIL TO TEACHER ============
        email_sent = False
        email_error = None
        
        try:
            # Get email configuration from environment variables
            SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
            SMTP_USERNAME = os.getenv('SMTP_USERNAME')
            SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
            FROM_EMAIL = os.getenv('FROM_EMAIL', 'SanjayKrishna12172004@gmail.com')
            FROM_NAME = os.getenv('FROM_NAME', 'IntelliLearn Admin')
            
            print(f"📧 Attempting to send email to {email}")
            print(f"📧 Using SMTP: {SMTP_SERVER}:{SMTP_PORT}")
            print(f"📧 Username: {SMTP_USERNAME}")
            print(f"📧 Password configured: {'Yes' if SMTP_PASSWORD else 'No'}")
            
            # Validate email configuration
            if not SMTP_USERNAME or not SMTP_PASSWORD:
                raise Exception("SMTP username or password not configured in environment variables")
            
            # Create email
            msg = MIMEMultipart()
            msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
            msg['To'] = email
            msg['Subject'] = 'Welcome to IntelliLearn - Your Teacher Account Details'
            
            # HTML Email template
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to IntelliLearn</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        background-color: #f9f9f9;
                    }}
                    .header {{
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        padding: 30px;
                        text-align: center;
                        border-radius: 10px 10px 0 0;
                        color: white;
                    }}
                    .content {{
                        background-color: white;
                        padding: 30px;
                        border-radius: 0 0 10px 10px;
                        border: 1px solid #e0e0e0;
                    }}
                    .credentials {{
                        background-color: #f8f9fa;
                        border-left: 4px solid #007bff;
                        padding: 20px;
                        margin: 20px 0;
                        border-radius: 5px;
                    }}
                    .warning {{
                        background-color: #fff3cd;
                        border-left: 4px solid #ffc107;
                        padding: 15px;
                        margin: 20px 0;
                        border-radius: 5px;
                        color: #856404;
                    }}
                    .login-btn {{
                        display: inline-block;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 25px;
                        font-weight: bold;
                        margin: 20px 0;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin: 15px 0;
                    }}
                    table td {{
                        padding: 10px;
                        border-bottom: 1px solid #eee;
                    }}
                    table td:first-child {{
                        font-weight: bold;
                        color: #555;
                        width: 40%;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid #eee;
                        color: #666;
                        font-size: 12px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1 style="margin: 0; font-size: 24px;">Welcome to IntelliLearn!</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Your AI-Powered School Management System</p>
                </div>
                
                <div class="content">
                    <p style="font-size: 16px;">Dear <strong>{data['name'].strip()}</strong>,</p>
                    
                    <p>Your teacher account has been successfully created on the IntelliLearn platform. Below are your login credentials:</p>
                    
                    <div class="credentials">
                        <h3 style="margin-top: 0; color: #007bff;">Your Account Details</h3>
                        <table>
                            <tr>
                                <td>Employee ID:</td>
                                <td><strong>{employee_id}</strong></td>
                            </tr>
                            <tr>
                                <td>Email Address:</td>
                                <td>{email}</td>
                            </tr>
                            <tr>
                                <td>Temporary Password:</td>
                                <td style="color: #dc3545; font-weight: bold; font-size: 18px;">{temp_password}</td>
                            </tr>
                            <tr>
                                <td>Subject:</td>
                                <td>{data['subject'].strip()}</td>
                            </tr>
                            <tr>
                                <td>Designation:</td>
                                <td>{data.get('designation', 'Teacher')}</td>
                            </tr>
                            <tr>
                                <td>School:</td>
                                <td>{data.get('school_name', 'IntelliLearn School')}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div class="warning">
                        <h4 style="margin-top: 0;">⚠️ Important Security Notice:</h4>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li>This is a <strong>temporary password</strong></li>
                            <li>Please change your password immediately after first login</li>
                            <li>Never share your password with anyone</li>
                            <li>For security, this temporary password expires in 7 days</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="https://smartedufrontend.onrender.com/login" class="login-btn">
                            Click Here to Login
                        </a>
                        <p style="font-size: 14px; color: #666; margin-top: 10px;">
                            Or visit: https://smartedufrontend.onrender.com/login
                        </p>
                    </div>
                    
                    <p style="font-size: 14px; color: #777;">
                        If you have any questions or need assistance, please contact the school administration or 
                        reply to this email.
                    </p>
                </div>
                
                <div class="footer">
                    <p>
                        This is an automated message. Please do not reply directly to this email.<br>
                        &copy; {datetime.now().year} IntelliLearn. All rights reserved.<br>
                        <small>IntelliLearn - AI-Powered School Management System</small>
                    </p>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            # Connect to SMTP server with timeout
            print(f"🔗 Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
            server.set_debuglevel(1)  # Enable debug output
            
            print("🔐 Starting TLS...")
            server.starttls()
            
            print(f"🔑 Logging in as: {SMTP_USERNAME}")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            
            print(f"📤 Sending email to: {email}")
            server.send_message(msg)
            
            print("✅ Email sent successfully")
            server.quit()
            
            email_sent = True
            print(f"✅ Email sent successfully to {email}")
            
        except smtplib.SMTPAuthenticationError as auth_error:
            email_error = f"SMTP Authentication failed: {str(auth_error)}"
            print(f"❌ Authentication failed: {auth_error}")
            print("ℹ️ Please check your Gmail App Password")
            
        except smtplib.SMTPException as smtp_error:
            email_error = f"SMTP Error: {str(smtp_error)}"
            print(f"❌ SMTP Error: {smtp_error}")
            
        except Exception as e:
            email_error = f"Email sending failed: {str(e)}"
            print(f"❌ Email error: {e}")
            import traceback
            traceback.print_exc()
        
        # ============ CREATE RESPONSE ============
        response_data = {
            'success': True,
            'message': 'Teacher registered successfully',
            'data': {
                'teacher_id': teacher_id,
                'employee_id': employee_id,
                'name': teacher_doc['name'],
                'email': email,
                'temp_password': temp_password,
                'email_sent': email_sent,
                'email_error': email_error,
                'login_url': 'https://smartedufrontend.onrender.com/login',
                'instructions': 'Please share these credentials with the teacher.' + 
                               (' Email was sent successfully.' if email_sent else 
                                ' Email failed to send. Please share credentials manually.')
            }
        }
        
        print(f"✅ Teacher registered successfully: {employee_id}")
        
        return jsonify(response_data), 201
        
    except Exception as e:
        print(f"❌ Error registering teacher: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'Failed to register teacher: {str(e)}'
        }), 500
# ==================== GET ALL TEACHERS ====================

# ==================== GET ALL TEACHERS ====================

@teachers_bp.route('/teachers', methods=['GET', 'OPTIONS'])
def get_all_teachers():
    """Get all teachers with filtering and pagination - WITH SCHOOL FILTER"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        # Get query parameters with defaults
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '').strip()
        subject = request.args.get('subject', '').strip()
        sort_by = request.args.get('sortBy', 'name')
        sort_order = request.args.get('sortOrder', 'asc')
        
        # NEW: Get school_id from query parameters or token
        school_id = request.args.get('school_id', '').strip()
        
        # If school_id not in query params, try to get from token
        if not school_id:
            # Check if token exists in headers
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                payload = decode_token(token)
                if payload:
                    school_id = payload.get('school_id', '')
        
        print(f"📋 Received params: page={page}, limit={limit}, search='{search}', status='{status}', subject='{subject}', school_id='{school_id}'")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query - MUST include school_id if provided
        query = {}
        
        # Add school filter if school_id is provided
        if school_id:
            query['school_id'] = school_id
            print(f"🏫 Filtering teachers by school: {school_id}")
        
        # Apply filters only if they have valid values (not empty or 'undefined')
        if search and search != 'undefined':
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'employee_id': {'$regex': search, '$options': 'i'}},
                {'subject': {'$regex': search, '$options': 'i'}}
            ]
        
        if status and status != 'undefined' and status != 'all':
            query['status'] = status
        
        if subject and subject != 'undefined' and subject != 'all':
            query['subject'] = subject
        
        # Debug: Print query
        print(f"🔍 MongoDB query: {query}")
        
        # Get total count
        total = db.teachers.count_documents(query)
        print(f"📊 Total teachers found: {total}")
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Define sort
        sort_direction = 1 if sort_order == 'asc' else -1
        sort_field = sort_by if sort_by in ['name', 'join_date', 'experience', 'created_at'] else 'name'
        
        # Fetch teachers
        teachers_cursor = db.teachers.find(query)\
            .sort(sort_field, sort_direction)\
            .skip(skip)\
            .limit(limit)
        
        teachers = list(teachers_cursor)
        print(f"📋 Fetched {len(teachers)} teachers")
        
        # Serialize documents
        teachers = [serialize_document(teacher) for teacher in teachers]
        
        # Remove password from response
        for teacher in teachers:
            teacher.pop('password', None)
        
        client.close()
        
        response = jsonify({
            'success': True,
            'data': {
                'teachers': teachers,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': math.ceil(total / limit) if limit > 0 else 1
                }
            }
        })
        
        return response, 200
        
    except Exception as e:
        print(f"❌ Error fetching teachers: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'Failed to fetch teachers: {str(e)}'
        }), 500

# ==================== UPDATE TEACHER ====================

@teachers_bp.route('/teachers/<teacher_id>', methods=['PUT'])
def update_teacher(teacher_id):
    """Update teacher information"""
    try:
        data = request.get_json()
        
        print(f"📝 Updating teacher {teacher_id}")
        
        # Validate required fields if present
        if 'email' in data:
            email = data['email'].strip().lower()
            if not validate_email(email):
                return jsonify({
                    'success': False,
                    'error': 'Invalid email format'
                }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if teacher exists
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check if email already exists (if email is being changed)
        if 'email' in data:
            existing = db.teachers.find_one({
                'email': data['email'].strip().lower(),
                '_id': {'$ne': ObjectId(teacher_id)}
            })
            if existing:
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Email already exists for another teacher'
                }), 400
        
        # Prepare update data
        update_data = {}
        
        # Process each field
        if 'name' in data:
            update_data['name'] = data['name'].strip()
        
        if 'email' in data:
            update_data['email'] = data['email'].strip().lower()
        
        if 'phone' in data:
            update_data['phone'] = data['phone'].strip()
        
        if 'subject' in data:
            update_data['subject'] = data['subject'].strip()
        
        if 'classes' in data:
            if isinstance(data['classes'], str):
                update_data['classes'] = [cls.strip() for cls in data['classes'].split(',') if cls.strip()]
            elif isinstance(data['classes'], list):
                update_data['classes'] = [str(cls).strip() for cls in data['classes']]
        
        if 'status' in data:
            update_data['status'] = data['status'].strip()
        
        if 'qualifications' in data:
            if isinstance(data['qualifications'], str):
                update_data['qualifications'] = [q.strip() for q in data['qualifications'].split(',') if q.strip()]
            elif isinstance(data['qualifications'], list):
                update_data['qualifications'] = [str(q).strip() for q in data['qualifications']]
        
        if 'experience' in data:
            try:
                update_data['experience'] = int(data['experience'])
            except ValueError:
                pass
        
        if 'address' in data:
            update_data['address'] = data['address'].strip()
        
        if 'date_of_birth' in data and data['date_of_birth']:
            try:
                update_data['date_of_birth'] = datetime.strptime(data['date_of_birth'], '%Y-%m-%d')
            except ValueError:
                pass
        
        if 'emergency_contact' in data:
            update_data['emergency_contact'] = data['emergency_contact'].strip()
        
        if 'gender' in data:
            update_data['gender'] = data['gender'].strip()
        
        if 'blood_group' in data:
            update_data['blood_group'] = data['blood_group'].strip()
        
        if 'designation' in data:
            update_data['designation'] = data['designation'].strip()
        
        if 'department' in data:
            update_data['department'] = data['department'].strip()
        
        if 'salary' in data:
            try:
                update_data['salary'] = float(data['salary'])
            except ValueError:
                pass
        
        if 'school_id' in data:
            update_data['school_id'] = data['school_id'].strip()
            # Update school code as well
            if len(update_data['school_id']) >= 3:
                update_data['school_code'] = update_data['school_id'][:3].upper()
        
        # Add update timestamp
        update_data['updated_at'] = datetime.utcnow()
        
        # Update teacher
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Teacher updated successfully',
                'data': {
                    'teacher_id': teacher_id,
                    'updated_fields': list(update_data.keys())
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'message': 'No changes made to teacher',
                'data': {'teacher_id': teacher_id}
            }), 200
        
    except Exception as e:
        print(f"❌ Error updating teacher: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'Failed to update teacher: {str(e)}'
        }), 500

# ==================== DELETE TEACHER ====================

@teachers_bp.route('/teachers/<teacher_id>', methods=['DELETE', 'OPTIONS'])
def delete_teacher(teacher_id):
    """Delete a teacher"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        # @token_required for production
        print(f"🗑️ Deleting teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if teacher exists
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Delete teacher
        result = db.teachers.delete_one({'_id': ObjectId(teacher_id)})
        
        print(f"✅ Delete result: {result.deleted_count} documents deleted")
        
        client.close()
        
        if result.deleted_count > 0:
            return jsonify({
                'success': True,
                'message': 'Teacher deleted successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete teacher'
            }), 500
        
    except Exception as e:
        print(f"❌ Error deleting teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete teacher: {str(e)}'
        }), 500

# ==================== BULK IMPORT TEACHERS ====================

# ==================== BULK IMPORT TEACHERS ====================

@teachers_bp.route('/teachers/bulk-import', methods=['POST', 'OPTIONS'])
def bulk_import_teachers():
    """Bulk import teachers from Excel/CSV file"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print("📤 Starting bulk import...")
        
        # Get school_id from form data or request
        school_id = request.form.get('school_id', 'test_school_id')
        print(f"🏫 School ID: {school_id}")
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'File type not allowed. Please upload Excel (.xlsx, .xls) or CSV files.'
            }), 400
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(f"💾 File saved to: {filepath}")
        
        # Read file based on extension
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
        except Exception as e:
            os.remove(filepath)
            return jsonify({
                'success': False,
                'error': f'Failed to read file: {str(e)}'
            }), 400
        
        print(f"📊 File read successfully. Shape: {df.shape}")
        print(f"📋 Columns: {list(df.columns)}")
        
        # Required columns
        required_columns = ['name', 'email', 'subject', 'school_id']  # Added school_id as required
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            os.remove(filepath)
            return jsonify({
                'success': False,
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Process each row
        success_count = 0
        error_count = 0
        errors = []
        imported_teachers = []  # Store imported teachers for email sending
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['name']) or pd.isna(row['email']):
                    continue
                
                email = str(row['email']).strip().lower()
                name = str(row['name']).strip()
                
                # Check if email already exists
                if db.teachers.find_one({'email': email}):
                    errors.append(f"Row {index + 2}: Email {email} already exists")
                    error_count += 1
                    continue
                
                # Get school code (use school_id from row if available)
                row_school_id = str(row['school_id']).strip() if pd.notna(row.get('school_id')) else school_id
                
                # Generate school code from school_id (first 3 chars)
                school_code = row_school_id[:3].upper() if len(row_school_id) >= 3 else 'SCH'
                
                # Get teacher count for this school for ID generation
                teacher_count = db.teachers.count_documents({'school_id': row_school_id})
                
                # Generate employee ID
                teacher_count += 1
                employee_id = generate_employee_id(school_code, teacher_count)
                
                # Generate temporary password
                temp_password = generate_temp_password()
                hashed_password = hash_password(temp_password)
                
                # Parse classes if provided
                classes = []
                if 'classes' in row and pd.notna(row['classes']):
                    classes = [cls.strip() for cls in str(row['classes']).split(',') if cls.strip()]
                
                # Parse qualifications if provided
                qualifications = []
                if 'qualifications' in row and pd.notna(row['qualifications']):
                    qualifications = [q.strip() for q in str(row['qualifications']).split(',') if q.strip()]
                
                # Handle date_of_birth safely
                date_of_birth = None
                if 'date_of_birth' in row and pd.notna(row['date_of_birth']):
                    try:
                        if isinstance(row['date_of_birth'], str):
                            date_of_birth = datetime.strptime(row['date_of_birth'], '%Y-%m-%d')
                        elif isinstance(row['date_of_birth'], pd.Timestamp):
                            date_of_birth = row['date_of_birth'].to_pydatetime()
                    except (ValueError, AttributeError) as e:
                        print(f"⚠️ Could not parse date for {name}: {e}")
                
                # Prepare teacher document
                teacher_doc = {
                    'employee_id': employee_id,
                    'school_id': row_school_id,
                    'school_code': school_code,
                    'school_name': 'Test School',  # You might want to fetch this from schools collection
                    'name': name,
                    'email': email,
                    'phone': str(row.get('phone', '')).strip() if pd.notna(row.get('phone')) else '',
                    'password': hashed_password,
                    'subject': str(row['subject']).strip(),
                    'classes': classes,
                    'status': str(row.get('status', 'active')).strip().lower(),
                    'join_date': datetime.utcnow(),
                    'qualifications': qualifications,
                    'experience': int(float(row.get('experience', 0))) if pd.notna(row.get('experience')) else 0,
                    'address': str(row.get('address', '')).strip() if pd.notna(row.get('address')) else '',
                    'date_of_birth': date_of_birth,
                    'emergency_contact': str(row.get('emergency_contact', '')).strip() if pd.notna(row.get('emergency_contact')) else '',
                    'gender': str(row.get('gender', '')).strip() if pd.notna(row.get('gender')) else '',
                    'blood_group': str(row.get('blood_group', '')).strip() if pd.notna(row.get('blood_group')) else '',
                    'designation': str(row.get('designation', 'Teacher')).strip() if pd.notna(row.get('designation')) else 'Teacher',
                    'department': str(row.get('department', '')).strip() if pd.notna(row.get('department')) else '',
                    'salary': float(row['salary']) if 'salary' in row and pd.notna(row['salary']) else None,
                    'role': 'teacher',
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                # Insert teacher
                result = db.teachers.insert_one(teacher_doc)
                teacher_id = str(result.inserted_id)
                
                # Store teacher data for email
                imported_teachers.append({
                    'teacher_id': teacher_id,
                    'name': name,
                    'email': email,
                    'employee_id': employee_id,
                    'temp_password': temp_password,
                    'subject': teacher_doc['subject'],
                    'school_id': row_school_id
                })
                
                success_count += 1
                print(f"✅ Added teacher {index + 1}: {name} ({email})")
                
            except Exception as row_error:
                error_msg = f"Row {index + 2}: {str(row_error)}"
                errors.append(error_msg)
                error_count += 1
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
        
        # Clean up temp file
        os.remove(filepath)
        
        # Send emails to imported teachers (in background)
        try:
            send_bulk_import_emails(imported_teachers)
        except Exception as email_error:
            print(f"⚠️ Failed to send emails: {email_error}")
            errors.append(f"Emails not sent: {str(email_error)}")
        
        client.close()
        
        print(f"✅ Import completed: {success_count} successful, {error_count} failed")
        
        return jsonify({
            'success': True,
            'message': f'Bulk import completed. Success: {success_count}, Failed: {error_count}',
            'data': {
                'count': success_count,
                'success_count': success_count,
                'error_count': error_count,
                'imported_teachers': imported_teachers,  # Return imported teachers data
                'errors': errors[:10]  # Return first 10 errors
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in bulk import: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Clean up temp file if exists
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        
        return jsonify({
            'success': False,
            'error': f'Failed to import teachers: {str(e)}'
        }), 500

# ==================== DOWNLOAD BULK IMPORT TEMPLATE ====================

@teachers_bp.route('/teachers/bulk-import/template', methods=['GET'])
def download_import_template():
    """Download bulk import template"""
    try:
        # Create comprehensive template data
        template_data = [
            {
                'school_id': 'SCH001',  # REQUIRED - Must match existing school ID
                'name': 'Dr. Sarah Johnson',  # REQUIRED
                'email': 'sarah.johnson@school.edu',  # REQUIRED
                'phone': '+1234567890',
                'subject': 'Mathematics',  # REQUIRED
                'classes': '10-A,10-B,11-A',  # Comma-separated
                'status': 'active',  # active/inactive
                'qualifications': 'Ph.D in Mathematics,M.Ed',  # Comma-separated
                'experience': 8,
                'address': '123 Math Street',
                'date_of_birth': '1985-03-15',  # YYYY-MM-DD format
                'emergency_contact': '+1987654321',
                'gender': 'female',
                'blood_group': 'A+',
                'designation': 'Senior Teacher',
                'department': 'Science',
                'salary': 65000
            },
            {
                'school_id': 'SCH001',
                'name': 'Mr. Robert Chen',
                'email': 'robert.chen@school.edu',
                'phone': '+1987654321',
                'subject': 'Physics',
                'classes': '9-A,9-B',
                'status': 'active',
                'qualifications': 'M.Sc Physics',
                'experience': 6,
                'address': '456 Physics Avenue',
                'date_of_birth': '1988-07-22',
                'emergency_contact': '+1234567890',
                'gender': 'male',
                'blood_group': 'B+',
                'designation': 'Teacher',
                'department': 'Science',
                'salary': 55000
            }
        ]
        
        # Create DataFrame
        df = pd.DataFrame(template_data)
        
        # Create Excel file with instructions
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Add instructions sheet
            instructions_df = pd.DataFrame({
                'Field': ['school_id', 'name', 'email', 'subject', 'status', 'date_of_birth', 'classes', 'qualifications'],
                'Required': ['YES', 'YES', 'YES', 'YES', 'NO', 'NO', 'NO', 'NO'],
                'Format': ['Existing school ID', 'Full name', 'Valid email', 'Subject name', 'active/inactive', 'YYYY-MM-DD', 'Comma-separated', 'Comma-separated'],
                'Example': ['SCH001', 'Dr. Sarah Johnson', 'teacher@school.edu', 'Mathematics', 'active', '1985-03-15', '10-A,10-B', 'M.Sc,B.Ed']
            })
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False)
            
            # Add template sheet
            df.to_excel(writer, sheet_name='Teachers Template', index=False)
        
        output.seek(0)
        
        # Create response
        response = make_response(output.getvalue())
        response.headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers.set('Content-Disposition', 'attachment', filename='teachers_import_template.xlsx')
        
        return response
        
    except Exception as e:
        print(f"❌ Error generating template: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to generate template: {str(e)}'
        }), 500

# ==================== EXPORT TEACHERS ====================
# ==================== EXPORT TEACHERS ====================

@teachers_bp.route('/teachers/export', methods=['GET', 'OPTIONS'])
def export_teachers():
    """Export teachers to Excel - WITH SCHOOL FILTER"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print("📤 Exporting teachers...")
        
        # NEW: Get school_id from query parameters or token
        school_id = request.args.get('school_id', '').strip()
        
        # If school_id not in query params, try to get from token
        if not school_id:
            # Check if token exists in headers
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                payload = decode_token(token)
                if payload:
                    school_id = payload.get('school_id', '')
        
        print(f"🏫 Exporting teachers for school: {school_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query - filter by school if school_id provided
        query = {}
        if school_id:
            query['school_id'] = school_id
        
        # Fetch teachers with school filter
        teachers_cursor = db.teachers.find(query)
        teachers = list(teachers_cursor)
        
        print(f"📊 Found {len(teachers)} teachers for export")
        
        # Prepare data for export
        export_data = []
        for teacher in teachers:
            teacher_data = serialize_document(teacher)
            export_data.append({
                'Employee ID': teacher_data.get('employee_id', ''),
                'Name': teacher_data.get('name', ''),
                'Email': teacher_data.get('email', ''),
                'Phone': teacher_data.get('phone', ''),
                'Subject': teacher_data.get('subject', ''),
                'Classes': ', '.join(teacher_data.get('classes', [])),
                'Status': teacher_data.get('status', ''),
                'Join Date': teacher_data.get('join_date', ''),
                'Qualifications': ', '.join(teacher_data.get('qualifications', [])),
                'Experience (years)': teacher_data.get('experience', 0),
                'Address': teacher_data.get('address', ''),
                'Date of Birth': teacher_data.get('date_of_birth', ''),
                'Emergency Contact': teacher_data.get('emergency_contact', ''),
                'Gender': teacher_data.get('gender', ''),
                'Blood Group': teacher_data.get('blood_group', ''),
                'Designation': teacher_data.get('designation', ''),
                'Department': teacher_data.get('department', ''),
                'Salary': teacher_data.get('salary', ''),
                'School ID': teacher_data.get('school_id', ''),
                'School Name': teacher_data.get('school_name', '')
            })
        
        client.close()
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Teachers Export', index=False)
        
        output.seek(0)
        
        # Generate filename with school_id
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if school_id:
            filename = f'teachers_export_{school_id}_{timestamp}.xlsx'
        else:
            filename = f'teachers_export_{timestamp}.xlsx'
        
        # Create response
        response = make_response(output.getvalue())
        response.headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers.set('Content-Disposition', 'attachment', filename=filename)
        response.headers.set('Access-Control-Expose-Headers', 'Content-Disposition')
        
        print(f"✅ Export completed: {filename}")
        return response
        
    except Exception as e:
        print(f"❌ Error exporting teachers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to export teachers: {str(e)}'
        }), 500
# ==================== GET SINGLE TEACHER ====================

@teachers_bp.route('/teachers/<teacher_id>', methods=['GET', 'OPTIONS'])
def get_teacher(teacher_id):
    """Get a specific teacher by ID"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print(f"📋 Getting teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if teacher exists
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Serialize document
        teacher_data = serialize_document(teacher)
        
        # Remove sensitive data
        teacher_data.pop('password', None)
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': teacher_data
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch teacher: {str(e)}'
        }), 500

# ==================== GET TEACHER STATISTICS ====================
# ==================== GET TEACHER STATISTICS ====================

@teachers_bp.route('/teachers/statistics', methods=['GET', 'OPTIONS'])
def get_teacher_statistics():
    """Get teacher statistics and analytics - WITH SCHOOL FILTER"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print("📊 Getting teacher statistics")
        
        # NEW: Get school_id from query parameters or token
        school_id = request.args.get('school_id', '').strip()
        
        # If school_id not in query params, try to get from token
        if not school_id:
            # Check if token exists in headers
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                payload = decode_token(token)
                if payload:
                    school_id = payload.get('school_id', '')
        
        print(f"📊 Getting statistics for school: {school_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query - filter by school if school_id provided
        query = {}
        if school_id:
            query['school_id'] = school_id
        
        # Total teachers count
        total_teachers = db.teachers.count_documents(query)
        
        # Active/inactive counts
        active_teachers = db.teachers.count_documents({**query, 'status': 'active'})
        inactive_teachers = db.teachers.count_documents({**query, 'status': 'inactive'})
        
        # Count by subject
        subjects_pipeline = [
            {'$match': query} if query else {'$match': {}},
            {'$group': {'_id': '$subject', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        subjects_stats = list(db.teachers.aggregate(subjects_pipeline))
        
        # Count by designation
        designation_pipeline = [
            {'$match': query} if query else {'$match': {}},
            {'$group': {'_id': '$designation', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        designation_stats = list(db.teachers.aggregate(designation_pipeline))
        
        # Average experience
        experience_pipeline = [
            {'$match': {**query, 'experience': {'$exists': True, '$ne': None}}},
            {'$group': {
                '_id': None,
                'avg_experience': {'$avg': '$experience'},
                'max_experience': {'$max': '$experience'},
                'min_experience': {'$min': '$experience'},
                'total_experience': {'$sum': '$experience'}
            }}
        ]
        experience_stats = list(db.teachers.aggregate(experience_pipeline))
        
        # Monthly growth (teachers added per month)
        current_year = datetime.now().year
        monthly_growth_pipeline = [
            {'$match': {**query, 'join_date': {'$exists': True, '$gte': datetime(current_year, 1, 1)}}},
            {'$group': {
                '_id': {'$month': '$join_date'},
                'count': {'$sum': 1}
            }},
            {'$sort': {'_id': 1}}
        ]
        monthly_growth = list(db.teachers.aggregate(monthly_growth_pipeline))
        
        # Count by gender
        gender_stats = list(db.teachers.aggregate([
            {'$match': {**query, 'gender': {'$exists': True, '$ne': ''}}},
            {'$group': {'_id': '$gender', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]))
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'school_id': school_id,
                'total_teachers': total_teachers,
                'active_teachers': active_teachers,
                'inactive_teachers': inactive_teachers,
                'subjects_distribution': subjects_stats,
                'designation_distribution': designation_stats,
                'experience_stats': experience_stats[0] if experience_stats else {},
                'monthly_growth': monthly_growth,
                'gender_distribution': gender_stats
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching statistics: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch statistics: {str(e)}'
        }), 500
# ==================== UPDATE TEACHER STATUS ====================

@teachers_bp.route('/teachers/<teacher_id>/status', methods=['PATCH', 'OPTIONS'])
def update_teacher_status(teacher_id):
    """Update teacher status (active/inactive)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status or new_status not in ['active', 'inactive']:
            return jsonify({
                'success': False,
                'error': 'Invalid status. Must be "active" or "inactive"'
            }), 400
        
        print(f"🔄 Updating teacher {teacher_id} status to {new_status}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if teacher exists
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Update status
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': {
                'status': new_status,
                'updated_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': f'Teacher status updated to {new_status}'
            }), 200
        else:
            return jsonify({
                'success': True,
                'message': 'No changes made'
            }), 200
        
    except Exception as e:
        print(f"❌ Error updating status: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update status: {str(e)}'
        }), 500

# ==================== SEARCH TEACHERS ====================

# ==================== SEARCH TEACHERS ====================

@teachers_bp.route('/teachers/search', methods=['GET', 'OPTIONS'])
def search_teachers():
    """Advanced search for teachers with multiple criteria - WITH SCHOOL FILTER"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        # Get query parameters
        query = request.args.get('q', '').strip()
        subject = request.args.get('subject', '').strip()
        designation = request.args.get('designation', '').strip()
        status = request.args.get('status', '').strip()
        min_experience = request.args.get('min_experience')
        max_experience = request.args.get('max_experience')
        limit = int(request.args.get('limit', 20))
        
        # NEW: Get school_id from query parameters or token
        school_id = request.args.get('school_id', '').strip()
        
        # If school_id not in query params, try to get from token
        if not school_id:
            # Check if token exists in headers
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                payload = decode_token(token)
                if payload:
                    school_id = payload.get('school_id', '')
        
        print(f"🔍 Searching teachers: q={query}, subject={subject}, school_id={school_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build search query - MUST include school_id if provided
        search_query = {}
        
        # Add school filter if school_id is provided
        if school_id:
            search_query['school_id'] = school_id
        
        # Text search
        if query:
            search_query['$or'] = [
                {'name': {'$regex': query, '$options': 'i'}},
                {'email': {'$regex': query, '$options': 'i'}},
                {'employee_id': {'$regex': query, '$options': 'i'}},
                {'subject': {'$regex': query, '$options': 'i'}}
            ]
        
        # Filter by subject
        if subject:
            search_query['subject'] = {'$regex': subject, '$options': 'i'}
        
        # Filter by designation
        if designation:
            search_query['designation'] = {'$regex': designation, '$options': 'i'}
        
        # Filter by status
        if status:
            search_query['status'] = status
        
        # Filter by experience range
        if min_experience or max_experience:
            experience_filter = {}
            if min_experience:
                experience_filter['$gte'] = int(min_experience)
            if max_experience:
                experience_filter['$lte'] = int(max_experience)
            search_query['experience'] = experience_filter
        
        print(f"🔍 MongoDB search query: {search_query}")
        
        # Execute search
        teachers_cursor = db.teachers.find(search_query).limit(limit)
        teachers = list(teachers_cursor)
        
        # Serialize documents
        teachers = [serialize_document(teacher) for teacher in teachers]
        
        # Remove password from response
        for teacher in teachers:
            teacher.pop('password', None)
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'teachers': teachers,
                'count': len(teachers),
                'school_id': school_id  # Return the school_id used for filtering
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error searching teachers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to search teachers: {str(e)}'
        }), 500

# ==================== GET TEACHERS BY SCHOOL ====================

@teachers_bp.route('/teachers/school/<school_id>', methods=['GET', 'OPTIONS'])
def get_teachers_by_school(school_id):
    """Get all teachers belonging to a specific school"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print(f"🏫 Getting teachers for school {school_id}")
        
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        status = request.args.get('status', '').strip()
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Build query
        query = {'school_id': school_id}
        
        if status and status != 'all':
            query['status'] = status
        
        # Get total count
        total = db.teachers.count_documents(query)
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Fetch teachers
        teachers_cursor = db.teachers.find(query)\
            .sort('name', 1)\
            .skip(skip)\
            .limit(limit)
        
        teachers = list(teachers_cursor)
        
        # Serialize documents
        teachers = [serialize_document(teacher) for teacher in teachers]
        
        # Remove password from response
        for teacher in teachers:
            teacher.pop('password', None)
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'teachers': teachers,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit
                }
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching school teachers: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch school teachers: {str(e)}'
        }), 500

# ==================== UPDATE TEACHER PASSWORD ====================

@teachers_bp.route('/teachers/<teacher_id>/password', methods=['PATCH', 'OPTIONS'])
def update_teacher_password(teacher_id):
    """Update teacher password (admin or teacher themselves)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not new_password:
            return jsonify({
                'success': False,
                'error': 'New password is required'
            }), 400
        
        print(f"🔐 Updating password for teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Check current password if provided (for self-update)
        if current_password:
            if not check_password(current_password, teacher['password']):
                client.close()
                return jsonify({
                    'success': False,
                    'error': 'Current password is incorrect'
                }), 400
        
        # Hash new password
        hashed_password = hash_password(new_password)
        
        # Update password
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': {
                'password': hashed_password,
                'updated_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Password updated successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update password'
            }), 500
        
    except Exception as e:
        print(f"❌ Error updating password: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to update password: {str(e)}'
        }), 500

# ==================== RESET TEACHER PASSWORD ====================

@teachers_bp.route('/teachers/<teacher_id>/reset-password', methods=['POST', 'OPTIONS'])
def reset_teacher_password(teacher_id):
    """Reset teacher password (admin only)"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print(f"🔄 Resetting password for teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Generate new temporary password
        temp_password = generate_temp_password()
        hashed_password = hash_password(temp_password)
        
        # Update password
        result = db.teachers.update_one(
            {'_id': ObjectId(teacher_id)},
            {'$set': {
                'password': hashed_password,
                'updated_at': datetime.utcnow()
            }}
        )
        
        client.close()
        
        if result.modified_count > 0:
            return jsonify({
                'success': True,
                'message': 'Password reset successfully',
                'data': {
                    'email': teacher['email'],
                    'temp_password': temp_password
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to reset password'
            }), 500
        
    except Exception as e:
        print(f"❌ Error resetting password: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to reset password: {str(e)}'
        }), 500

# ==================== GET TEACHER DASHBOARD ====================

# ==================== GET TEACHER DASHBOARD ====================

@teachers_bp.route('/teachers/<teacher_id>/dashboard', methods=['GET', 'OPTIONS'])
def get_teacher_dashboard(teacher_id):
    """Get dashboard data for a specific teacher - UPDATED WITH SCHOOL FILTER"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print(f"📊 Getting dashboard for teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        school_id = teacher.get('school_id', '')
        
        # Get classes count
        class_count = len(teacher.get('classes', []))
        
        # Get student count (assuming students are linked to classes)
        student_count = 0
        if teacher.get('classes'):
            # Query students collection for students in these classes
            student_query = {'class': {'$in': teacher['classes']}}
            if school_id:
                student_query['school_id'] = school_id
            student_count = db.students.count_documents(student_query)
        
        # Get assignments count with school filter
        assignment_count = 0
        try:
            assignment_query = {'teacher_id': teacher_id}
            if school_id:
                assignment_query['school_id'] = school_id
            assignment_count = db.assignments.count_documents(assignment_query)
        except:
            pass
        
        # Get upcoming schedules/events with school filter
        upcoming_events = []
        try:
            event_query = {'teacher_id': teacher_id}
            if school_id:
                event_query['school_id'] = school_id
            upcoming_events = list(db.events.find({
                **event_query,
                'start_date': {'$gte': datetime.utcnow()}
            }).sort('start_date', 1).limit(5))
            upcoming_events = [serialize_document(event) for event in upcoming_events]
        except:
            pass
        
        # Get recent activities with school filter
        recent_activities = []
        try:
            activity_query = {'user_id': teacher_id, 'user_type': 'teacher'}
            if school_id:
                activity_query['school_id'] = school_id
            recent_activities = list(db.activity_logs.find(activity_query)
                .sort('timestamp', -1).limit(10))
            recent_activities = [serialize_document(activity) for activity in recent_activities]
        except:
            pass
        
        # Performance metrics (if applicable)
        performance_metrics = {
            'attendance_rate': 95,
            'student_satisfaction': 4.5,
            'assignment_completion': 88,
            'class_engagement': 92
        }
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'teacher_info': {
                    'name': teacher['name'],
                    'subject': teacher['subject'],
                    'designation': teacher.get('designation', 'Teacher'),
                    'experience': teacher.get('experience', 0),
                    'school_id': school_id
                },
                'stats': {
                    'classes': class_count,
                    'students': student_count,
                    'assignments': assignment_count,
                    'upcoming_events': len(upcoming_events)
                },
                'upcoming_events': upcoming_events,
                'recent_activities': recent_activities,
                'performance_metrics': performance_metrics
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching dashboard: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch dashboard: {str(e)}'
        }), 500

# ==================== BULK UPDATE TEACHERS ====================

@teachers_bp.route('/teachers/bulk-update', methods=['POST', 'OPTIONS'])
def bulk_update_teachers():
    """Bulk update multiple teachers"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        data = request.get_json()
        teacher_ids = data.get('teacher_ids', [])
        update_data = data.get('update_data', {})
        
        if not teacher_ids:
            return jsonify({
                'success': False,
                'error': 'No teacher IDs provided'
            }), 400
        
        if not update_data:
            return jsonify({
                'success': False,
                'error': 'No update data provided'
            }), 400
        
        print(f"🔄 Bulk updating {len(teacher_ids)} teachers")
        
        # Convert string IDs to ObjectId
        object_ids = [ObjectId(tid) for tid in teacher_ids if ObjectId.is_valid(tid)]
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Add update timestamp
        update_data['updated_at'] = datetime.utcnow()
        
        # Perform bulk update
        result = db.teachers.update_many(
            {'_id': {'$in': object_ids}},
            {'$set': update_data}
        )
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': f'Updated {result.modified_count} teachers successfully',
            'data': {
                'matched_count': result.matched_count,
                'modified_count': result.modified_count
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error in bulk update: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to bulk update teachers: {str(e)}'
        }), 500

# ==================== GET TEACHER ACTIVITY LOG ====================

@teachers_bp.route('/teachers/<teacher_id>/activity-log', methods=['GET', 'OPTIONS'])
def get_teacher_activity_log(teacher_id):
    """Get activity log for a specific teacher"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        print(f"📋 Getting activity log for teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if teacher exists
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        # Build query for activity logs
        query = {'user_id': teacher_id, 'user_type': 'teacher'}
        
        # Date range filter
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                query['timestamp'] = {'$gte': start_datetime}
            except ValueError:
                pass
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                if 'timestamp' in query:
                    query['timestamp']['$lte'] = end_datetime
                else:
                    query['timestamp'] = {'$lte': end_datetime}
            except ValueError:
                pass
        
        # Get total count
        total = db.activity_logs.count_documents(query) if 'activity_logs' in db.list_collection_names() else 0
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Fetch activity logs
        activities = []
        if 'activity_logs' in db.list_collection_names():
            activities_cursor = db.activity_logs.find(query)\
                .sort('timestamp', -1)\
                .skip(skip)\
                .limit(limit)
            activities = list(activities_cursor)
            activities = [serialize_document(activity) for activity in activities]
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'activities': activities,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit if limit > 0 else 1
                }
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching activity log: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch activity log: {str(e)}'
        }), 500
@teachers_bp.route('/teachers/add', methods=['POST', 'OPTIONS'])
def add_teacher():
    """Add a new teacher (simple version for frontend)"""
    
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        print(f"📥 Adding teacher: {data}")
        
        # Validate required fields
        required_fields = ['name', 'email', 'subject']
        missing_fields = [field for field in required_fields if field not in data or not str(data[field]).strip()]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        # Validate email
        email = data['email'].strip().lower()
        if not validate_email(email):
            return jsonify({
                'success': False,
                'error': 'Invalid email format'
            }), 400
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Check if email exists
        if db.teachers.find_one({'email': email}):
            client.close()
            return jsonify({
                'success': False,
                'error': 'Email already exists'
            }), 400
        
        # Generate employee ID
        teacher_count = db.teachers.count_documents({})
        employee_id = f"SCH{datetime.now().year}{str(teacher_count + 1).zfill(4)}"
        
        # Create teacher document
        teacher_doc = {
            'employee_id': employee_id,
            'name': data['name'].strip(),
            'email': email,
            'phone': data.get('phone', ''),
            'subject': data['subject'].strip(),
            'classes': data.get('classes', []),
            'status': data.get('status', 'active'),
            'qualifications': data.get('qualifications', []),
            'experience': int(data.get('experience', 0)),
            'address': data.get('address', ''),
            'date_of_birth': data.get('date_of_birth', ''),
            'gender': data.get('gender', ''),
            'blood_group': data.get('blood_group', ''),
            'designation': data.get('designation', 'Teacher'),
            'department': data.get('department', ''),
            'salary': float(data.get('salary', 0)) if data.get('salary') else 0,
            'school_id': data.get('school_id', ''),
            'join_date': datetime.utcnow(),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert into database
        result = db.teachers.insert_one(teacher_doc)
        teacher_id = str(result.inserted_id)
        
        client.close()
        
        return jsonify({
            'success': True,
            'message': 'Teacher added successfully',
            'data': {
                'id': teacher_id,
                'employee_id': employee_id,
                'name': teacher_doc['name'],
                'email': email
            }
        }), 201
        
    except Exception as e:
        print(f"❌ Error adding teacher: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to add teacher: {str(e)}'
        }), 500
# ==================== GET TEACHER DASHBOARD WITH SCHOOL CONTEXT ====================

@teachers_bp.route('/teachers/<teacher_id>/school-dashboard', methods=['GET', 'OPTIONS'])
def get_teacher_school_dashboard(teacher_id):
    """Get dashboard data for a specific teacher with school context"""
    if request.method == 'OPTIONS':
        response = make_response()
        return response
    
    try:
        print(f"📊 Getting school dashboard for teacher {teacher_id}")
        
        # Connect to MongoDB
        client = get_mongo_client()
        db = get_db()
        
        # Get teacher
        teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        if not teacher:
            client.close()
            return jsonify({
                'success': False,
                'error': 'Teacher not found'
            }), 404
        
        school_id = teacher.get('school_id', '')
        
        # Get school info if available
        school_info = {}
        if school_id:
            school = db.schools.find_one({'school_id': school_id})
            if school:
                school_info = {
                    'school_id': school.get('school_id', ''),
                    'school_name': school.get('name', ''),
                    'address': school.get('address', ''),
                    'phone': school.get('phone', ''),
                    'email': school.get('email', '')
                }
        
        # Get total teachers in the same school
        school_teachers_count = db.teachers.count_documents({'school_id': school_id}) if school_id else 0
        
        # Get teachers by subject in the same school
        school_subjects = list(db.teachers.aggregate([
            {'$match': {'school_id': school_id}} if school_id else {'$match': {}},
            {'$group': {'_id': '$subject', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 5}
        ]))
        
        # Get classes count for this teacher
        class_count = len(teacher.get('classes', []))
        
        # Get student count (assuming students are linked to classes and same school)
        student_count = 0
        if teacher.get('classes'):
            # Query students collection for students in these classes and same school
            student_query = {'class': {'$in': teacher['classes']}}
            if school_id:
                student_query['school_id'] = school_id
            student_count = db.students.count_documents(student_query)
        
        # Get assignments count (if you have assignments collection)
        assignment_count = 0
        try:
            assignment_count = db.assignments.count_documents({
                'teacher_id': teacher_id,
                'school_id': school_id
            })
        except:
            pass
        
        client.close()
        
        return jsonify({
            'success': True,
            'data': {
                'teacher_info': {
                    'name': teacher['name'],
                    'subject': teacher['subject'],
                    'designation': teacher.get('designation', 'Teacher'),
                    'experience': teacher.get('experience', 0),
                    'employee_id': teacher.get('employee_id', '')
                },
                'school_info': school_info,
                'stats': {
                    'classes': class_count,
                    'students': student_count,
                    'assignments': assignment_count,
                    'school_teachers': school_teachers_count
                },
                'school_subjects': school_subjects,
                'school_id': school_id
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching school dashboard: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch school dashboard: {str(e)}'
        }), 500

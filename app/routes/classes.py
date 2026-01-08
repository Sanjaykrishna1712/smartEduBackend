# app/routes/classes.py
from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
import os
import jwt
import math
from bson import ObjectId
from pymongo import MongoClient

# Create blueprint
classes_bp = Blueprint('classes', __name__)

# Configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'

# MongoDB connection
def get_db():
    client = MongoClient(MONGO_URI)
    return client[DATABASE_NAME]

# Helper functions
def serialize_document(doc):
    """Convert MongoDB document to JSON serializable format"""
    if not doc:
        return None
    
    result = dict(doc)
    
    if '_id' in result:
        result['id'] = str(result['_id'])
        del result['_id']
    
    for key, value in result.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
    
    if 'courses' not in result:
        result['courses'] = []
    if 'subjects' not in result:
        result['subjects'] = []
    
    return result

def validate_object_id(id_str):
    """Validate if string is a valid ObjectId"""
    try:
        return ObjectId(id_str)
    except:
        return None

def decode_token(token):
    """Decode and verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_school_id_from_request():
    """Extract school_id from request"""
    school_id = None
    
    # Check Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        payload = decode_token(token)
        if payload:
            school_id = payload.get('school_id', '').strip()
            print(f"✅ Extracted school_id from token: {school_id}")
    
    # Check query parameter
    if not school_id:
        school_id = request.args.get('school_id', '').strip()
        if school_id:
            print(f"✅ Extracted school_id from query: {school_id}")
    
    # Check JSON body
    if not school_id and request.method in ['POST', 'PUT', 'DELETE']:
        try:
            data = request.get_json(silent=True) or {}
            school_id = data.get('school_id', '').strip()
            if school_id:
                print(f"✅ Extracted school_id from body: {school_id}")
        except:
            pass
    
    return school_id

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers.add('Access-Control-Allow-Origin', 'https://smartedufrontend.onrender.com')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With,Accept,Origin')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Max-Age', '86400')
    return response

# ==================== OPTIONS HANDLERS ====================

@classes_bp.route('/classes', methods=['OPTIONS'])
def handle_classes_options():
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/classes/<string:class_id>', methods=['OPTIONS'])
def handle_single_class_options(class_id):
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/subjects', methods=['OPTIONS'])
def handle_subjects_options():
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/subjects/<string:subject_id>', methods=['OPTIONS'])
def handle_single_subject_options(subject_id):
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/dashboard/stats', methods=['OPTIONS'])
def handle_dashboard_options():
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/courses', methods=['OPTIONS'])
def handle_courses_options():
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/courses/<string:course_id>', methods=['OPTIONS'])
def handle_single_course_options(course_id):
    response = make_response()
    return add_cors_headers(response)

@classes_bp.route('/seed-subjects', methods=['OPTIONS'])
def handle_seed_subjects_options():
    response = make_response()
    return add_cors_headers(response)

# ==================== ROUTES ====================

# Get all classes
@classes_bp.route('/classes', methods=['GET'])
def get_classes():
    """Get all classes for a school"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        # Get school_id from JWT token
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required. Include in Authorization token.'
            })
            return add_cors_headers(response), 400
        
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        search = request.args.get('search', '').strip()
        grade = request.args.get('grade', '').strip()
        
        db = get_db()
        
        # Build query
        query = {'school_id': school_id}
        
        if search and search != 'undefined' and search != '':
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'code': {'$regex': search, '$options': 'i'}},
                {'grade': {'$regex': search, '$options': 'i'}}
            ]
        
        if grade and grade != 'undefined' and grade != 'all' and grade != '':
            query['grade'] = grade
        
        # Get total count
        total = db.classes.count_documents(query)
        
        # Calculate pagination
        skip = (page - 1) * limit
        
        # Fetch classes
        classes_cursor = db.classes.find(query)\
            .sort('grade', 1)\
            .skip(skip)\
            .limit(limit)
        
        classes = list(classes_cursor)
        
        # Serialize and get student counts
        serialized_classes = []
        for cls in classes:
            serialized_cls = serialize_document(cls)
            
            # Get student count for this class
            student_count = db.students.count_documents({
                'class': cls.get('grade', ''),
                'school_id': school_id
            })
            serialized_cls['students'] = student_count
            
            serialized_classes.append(serialized_cls)
        
        response = jsonify({
            'success': True,
            'classes': serialized_classes,
            'total': total,
            'page': page,
            'limit': limit,
            'school_id': school_id
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error in get_classes: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Get single class
@classes_bp.route('/classes/<string:class_id>', methods=['GET'])
def get_class(class_id):
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        obj_id = validate_object_id(class_id)
        if not obj_id:
            response = jsonify({
                'success': False,
                'message': 'Invalid class ID'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Find class
        class_obj = db.classes.find_one({
            '_id': obj_id,
            'school_id': school_id
        })
        
        if not class_obj:
            response = jsonify({
                'success': False,
                'message': 'Class not found'
            })
            return add_cors_headers(response), 404
        
        # Serialize class
        serialized_class = serialize_document(class_obj)
        
        # Get student count
        student_count = db.students.count_documents({
            'class': class_obj.get('grade', ''),
            'school_id': school_id
        })
        serialized_class['students'] = student_count
        
        response = jsonify({
            'success': True,
            'class': serialized_class,
            'student_count': student_count,
            'school_id': school_id
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in get_class: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Create class
@classes_bp.route('/classes', methods=['POST'])
def create_class():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data:
            response = jsonify({
                'success': False,
                'message': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        school_id = get_school_id_from_request()
        
        if not school_id:
            school_id = data.get('school_id', '')
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        if 'grade' not in data or not data['grade']:
            response = jsonify({
                'success': False,
                'message': 'Grade is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Generate class code
        grade = data['grade']
        class_count = db.classes.count_documents({
            'grade': grade,
            'school_id': school_id
        }) + 1
        
        school_prefix = school_id[:3].upper() if len(school_id) >= 3 else "SCH"
        class_code = f'{school_prefix}{grade.zfill(2)}{class_count:03d}'
        class_name = f"Class {grade}"
        
        # Process subjects
        subjects = data.get('subjects', [])
        processed_subjects = []
        
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists in this school
                subject_obj = db.subjects.find_one({
                    '_id': ObjectId(subject_id),
                    'school_id': school_id
                })
                if subject_obj:
                    processed_subjects.append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', '')
                    })
        
        # Create class document
        class_doc = {
            'code': class_code,
            'name': class_name,
            'grade': grade,
            'capacity': data.get('capacity', 30),
            'academic_year': data.get('academic_year', '2024-2025'),
            'students': 0,
            'description': data.get('description', ''),
            'courses': data.get('courses', []),
            'subjects': processed_subjects,
            'school_id': school_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert class
        result = db.classes.insert_one(class_doc)
        created_class = db.classes.find_one({'_id': result.inserted_id})
        serialized_class = serialize_document(created_class)
        
        response = jsonify({
            'success': True,
            'message': 'Class created successfully',
            'class': serialized_class
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"Error in create_class: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Get subjects
@classes_bp.route('/subjects', methods=['GET'])
def get_subjects():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Get query parameters
        search = request.args.get('search', '').strip()
        
        # Build query
        query = {'school_id': school_id}
        
        if search and search != 'undefined' and search != '':
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'code': {'$regex': search, '$options': 'i'}}
            ]
        
        # Fetch subjects
        subjects = list(db.subjects.find(query).sort('name', 1))
        serialized_subjects = [serialize_document(subject) for subject in subjects]
        
        response = jsonify({
            'success': True,
            'subjects': serialized_subjects,
            'total': len(serialized_subjects),
            'school_id': school_id
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in get_subjects: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Create subject
@classes_bp.route('/subjects', methods=['POST'])
def create_subject():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data:
            response = jsonify({
                'success': False,
                'message': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        school_id = get_school_id_from_request()
        
        if not school_id:
            school_id = data.get('school_id', '')
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        if 'name' not in data or not data['name']:
            response = jsonify({
                'success': False,
                'message': 'Subject name is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Check if subject exists
        existing_subject = db.subjects.find_one({
            'name': data['name'],
            'school_id': school_id
        })
        
        if existing_subject:
            response = jsonify({
                'success': False,
                'message': 'Subject already exists'
            })
            return add_cors_headers(response), 400
        
        # Generate subject code
        subject_count = db.subjects.count_documents({'school_id': school_id}) + 1
        school_prefix = school_id[:3].upper() if len(school_id) >= 3 else "SCH"
        subject_code = data.get('code', f'{school_prefix}SUB{subject_count:03d}')
        
        # Create subject document
        subject_doc = {
            'name': data['name'],
            'code': subject_code,
            'description': data.get('description', ''),
            'credits': data.get('credits', 0),
            'school_id': school_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert subject
        result = db.subjects.insert_one(subject_doc)
        created_subject = db.subjects.find_one({'_id': result.inserted_id})
        serialized_subject = serialize_document(created_subject)
        
        response = jsonify({
            'success': True,
            'message': 'Subject created successfully',
            'subject': serialized_subject
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"Error in create_subject: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Get dashboard stats
@classes_bp.route('/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Get counts
        class_count = db.classes.count_documents({'school_id': school_id})
        student_count = db.students.count_documents({'school_id': school_id})
        subject_count = db.subjects.count_documents({'school_id': school_id})
        
        # Try to get teacher count
        teacher_count = 0
        if 'teachers' in db.list_collection_names():
            teacher_count = db.teachers.count_documents({'school_id': school_id})
        
        response = jsonify({
            'success': True,
            'stats': {
                'classes': class_count,
                'students': student_count,
                'teachers': teacher_count,
                'subjects': subject_count
            },
            'school_id': school_id
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in get_dashboard_stats: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500
# Update class subjects
@classes_bp.route('/classes/<string:class_id>/subjects', methods=['PUT'])
def update_class_subjects(class_id):
    """Update subjects for a specific class"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data:
            response = jsonify({
                'success': False,
                'message': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        obj_id = validate_object_id(class_id)
        if not obj_id:
            response = jsonify({
                'success': False,
                'message': 'Invalid class ID'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Verify class exists and belongs to school
        class_obj = db.classes.find_one({
            '_id': obj_id,
            'school_id': school_id
        })
        
        if not class_obj:
            response = jsonify({
                'success': False,
                'message': 'Class not found'
            })
            return add_cors_headers(response), 404
        
        # Process subjects
        subjects = data.get('subjects', [])
        processed_subjects = []
        
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists in this school
                subject_obj = db.subjects.find_one({
                    '_id': ObjectId(subject_id),
                    'school_id': school_id
                })
                if subject_obj:
                    processed_subjects.append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', ''),
                        'description': subject_obj.get('description', ''),
                        'credits': subject_obj.get('credits', 0)
                    })
        
        # Update class with new subjects
        update_data = {
            'subjects': processed_subjects,
            'updated_at': datetime.utcnow()
        }
        
        # Update the class
        db.classes.update_one(
            {'_id': obj_id, 'school_id': school_id},
            {'$set': update_data}
        )
        
        # Get updated class
        updated_class = db.classes.find_one({'_id': obj_id})
        serialized_class = serialize_document(updated_class)
        
        response = jsonify({
            'success': True,
            'message': 'Class subjects updated successfully',
            'class': serialized_class
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in update_class_subjects: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500
# Update class
@classes_bp.route('/classes/<string:class_id>', methods=['PUT'])
def update_class(class_id):
    """Update a class"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data:
            response = jsonify({
                'success': False,
                'message': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        obj_id = validate_object_id(class_id)
        if not obj_id:
            response = jsonify({
                'success': False,
                'message': 'Invalid class ID'
            })
            return add_cors_headers(response), 400
        
        if 'grade' not in data or not data['grade']:
            response = jsonify({
                'success': False,
                'message': 'Grade is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Verify class exists and belongs to school
        existing_class = db.classes.find_one({
            '_id': obj_id,
            'school_id': school_id
        })
        
        if not existing_class:
            response = jsonify({
                'success': False,
                'message': 'Class not found'
            })
            return add_cors_headers(response), 404
        
        # Process subjects
        subjects = data.get('subjects', [])
        processed_subjects = []
        
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists in this school
                subject_obj = db.subjects.find_one({
                    '_id': ObjectId(subject_id),
                    'school_id': school_id
                })
                if subject_obj:
                    processed_subjects.append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', '')
                    })
        
        # Update class document
        update_data = {
            'grade': data['grade'],
            'name': f"Class {data['grade']}",
            'capacity': data.get('capacity', 30),
            'academic_year': data.get('academic_year', '2024-2025'),
            'description': data.get('description', ''),
            'courses': data.get('courses', []),
            'subjects': processed_subjects,
            'updated_at': datetime.utcnow()
        }
        
        # Update class
        db.classes.update_one(
            {'_id': obj_id, 'school_id': school_id},
            {'$set': update_data}
        )
        
        # Get updated class
        updated_class = db.classes.find_one({'_id': obj_id})
        serialized_class = serialize_document(updated_class)
        
        response = jsonify({
            'success': True,
            'message': 'Class updated successfully',
            'class': serialized_class
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in update_class: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

# Delete class
@classes_bp.route('/classes/<string:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """Delete a class"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        obj_id = validate_object_id(class_id)
        if not obj_id:
            response = jsonify({
                'success': False,
                'message': 'Invalid class ID'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Verify class exists and belongs to school
        existing_class = db.classes.find_one({
            '_id': obj_id,
            'school_id': school_id
        })
        
        if not existing_class:
            response = jsonify({
                'success': False,
                'message': 'Class not found'
            })
            return add_cors_headers(response), 404
        
        # Delete the class
        result = db.classes.delete_one({'_id': obj_id, 'school_id': school_id})
        
        if result.deleted_count == 1:
            response = jsonify({
                'success': True,
                'message': 'Class deleted successfully'
            })
            return add_cors_headers(response), 200
        else:
            response = jsonify({
                'success': False,
                'message': 'Failed to delete class'
            })
            return add_cors_headers(response), 400
        
    except Exception as e:
        print(f"Error in delete_class: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500
# Add this to your classes.py file
# Add this to your classes.py file
# app/routes/classes.py
# Update the get_courses function to NOT auto-seed:

# app/routes/classes.py
# Update the get_courses function:

@classes_bp.route('/courses', methods=['GET'])
def get_courses():
    """Get courses by grade"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        grade = request.args.get('grade', '').strip()
        
        db = get_db()
        
        # Build query
        query = {'school_id': school_id}
        if grade and grade != 'undefined' and grade != '':
            query['grade'] = grade
        
        # Check if courses collection exists
        if 'courses' not in db.list_collection_names():
            response = jsonify({
                'success': True,
                'courses': [],
                'total': 0,
                'school_id': school_id,
                'message': 'No courses collection found'
            })
            return add_cors_headers(response), 200
        
        # Fetch courses
        courses = list(db.courses.find(query).sort('name', 1))
        serialized_courses = [serialize_document(course) for course in courses]
        
        response = jsonify({
            'success': True,
            'courses': serialized_courses,
            'total': len(serialized_courses),
            'school_id': school_id
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"Error in get_courses: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

def seed_default_courses(school_id, grade_filter=None):
    """Seed default courses with subjects for grades 1-12"""
    db = get_db()
    
    # Define subjects for different grade levels
    grade_subjects = {
        # Primary School (Grades 1-5)
        '1': ['English', 'Mathematics', 'Environmental Studies', 'Drawing', 'Physical Education'],
        '2': ['English', 'Mathematics', 'Environmental Studies', 'Drawing', 'Physical Education'],
        '3': ['English', 'Mathematics', 'Science', 'Social Studies', 'Drawing', 'Physical Education'],
        '4': ['English', 'Mathematics', 'Science', 'Social Studies', 'Computer Basics', 'Physical Education'],
        '5': ['English', 'Mathematics', 'Science', 'Social Studies', 'Computer Basics', 'Physical Education'],
        
        # Middle School (Grades 6-8)
        '6': ['English', 'Mathematics', 'Science', 'Social Studies', 'Computer Science', 'Second Language', 'Physical Education'],
        '7': ['English', 'Mathematics', 'Science', 'Social Studies', 'Computer Science', 'Second Language', 'Physical Education'],
        '8': ['English', 'Mathematics', 'Science', 'Social Studies', 'Computer Science', 'Second Language', 'Physical Education'],
        
        # High School (Grades 9-12)
        '9': ['English', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Social Studies', 'Computer Science', 'Second Language', 'Physical Education'],
        '10': ['English', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Social Studies', 'Computer Science', 'Second Language', 'Physical Education'],
        '11': ['English', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Computer Science', 'Second Language', 'Physical Education'],
        '12': ['English', 'Mathematics', 'Physics', 'Chemistry', 'Biology', 'Computer Science', 'Second Language', 'Physical Education']
    }
    
    # Define course categories
    course_categories = {
        'core': ['English', 'Mathematics', 'Science', 'Social Studies'],
        'science': ['Physics', 'Chemistry', 'Biology'],
        'languages': ['Second Language'],
        'computers': ['Computer Basics', 'Computer Science'],
        'arts': ['Drawing'],
        'physical': ['Physical Education']
    }
    
    courses_to_seed = []
    course_counter = {}
    
    # Generate courses for each grade
    for grade in range(1, 13):
        grade_str = str(grade)
        
        # Skip if grade filter is specified and doesn't match
        if grade_filter and grade_str != grade_filter:
            continue
            
        subjects = grade_subjects.get(grade_str, [])
        
        # Create core courses
        for subject in subjects:
            # Create a course code
            if grade_str not in course_counter:
                course_counter[grade_str] = 1
            
            course_code = f"{school_id[:3].upper()}{grade_str.zfill(2)}{course_counter[grade_str]:03d}"
            
            # Determine course category
            category = 'general'
            for cat_key, cat_subjects in course_categories.items():
                if subject in cat_subjects:
                    category = cat_key
                    break
            
            # Get subject ID if exists
            subject_id = None
            subject_obj = db.subjects.find_one({
                'name': subject,
                'school_id': school_id
            })
            if subject_obj:
                subject_id = str(subject_obj['_id'])
            
            course_doc = {
                'name': subject,
                'code': course_code,
                'grade': grade_str,
                'description': f"{subject} course for Grade {grade_str}",
                'category': category,
                'credits': 5 if grade_str in ['9', '10', '11', '12'] else 4,
                'subjects': [{
                    'id': subject_id,
                    'name': subject,
                    'code': f"{school_id[:3].upper()}SUB{subject[:3].upper()}"
                }] if subject_id else [],
                'school_id': school_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            courses_to_seed.append(course_doc)
            course_counter[grade_str] += 1
        
        # Create combined courses for higher grades
        if grade_str in ['11', '12']:
            # Science Stream
            science_course = {
                'name': 'Science Stream',
                'code': f"{school_id[:3].upper()}{grade_str.zfill(2)}{course_counter[grade_str]:03d}",
                'grade': grade_str,
                'description': f'Science stream courses for Grade {grade_str}',
                'category': 'science_stream',
                'credits': 20,
                'subjects': [],
                'school_id': school_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            course_counter[grade_str] += 1
            
            # Add science subjects
            for science_subject in ['Physics', 'Chemistry', 'Biology', 'Mathematics']:
                subject_obj = db.subjects.find_one({
                    'name': science_subject,
                    'school_id': school_id
                })
                if subject_obj:
                    science_course['subjects'].append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj['name'],
                        'code': subject_obj.get('code', '')
                    })
            
            courses_to_seed.append(science_course)
            
            # Commerce Stream (for Grade 11-12)
            commerce_course = {
                'name': 'Commerce Stream',
                'code': f"{school_id[:3].upper()}{grade_str.zfill(2)}{course_counter[grade_str]:03d}",
                'grade': grade_str,
                'description': f'Commerce stream courses for Grade {grade_str}',
                'category': 'commerce_stream',
                'credits': 20,
                'subjects': [],
                'school_id': school_id,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            course_counter[grade_str] += 1
            
            # Add commerce subjects
            for commerce_subject in ['Accountancy', 'Business Studies', 'Economics', 'Mathematics']:
                subject_obj = db.subjects.find_one({
                    'name': commerce_subject,
                    'school_id': school_id
                })
                if subject_obj:
                    commerce_course['subjects'].append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj['name'],
                        'code': subject_obj.get('code', '')
                    })
            
            courses_to_seed.append(commerce_course)
    
    # Insert courses into database
    if courses_to_seed:
        db.courses.insert_many(courses_to_seed)
        print(f"✅ Seeded {len(courses_to_seed)} courses for school {school_id}")
    
    # Return courses based on grade filter
    if grade_filter:
        return [course for course in courses_to_seed if course['grade'] == grade_filter]
    
    return courses_to_seed


# Create course endpoint
@classes_bp.route('/courses', methods=['POST'])
def create_course():
    """Create a new course"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        
        if not data:
            response = jsonify({
                'success': False,
                'message': 'No data provided'
            })
            return add_cors_headers(response), 400
        
        school_id = get_school_id_from_request()
        
        if not school_id:
            school_id = data.get('school_id', '')
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        if 'name' not in data or not data['name']:
            response = jsonify({
                'success': False,
                'message': 'Course name is required'
            })
            return add_cors_headers(response), 400
        
        if 'grade' not in data or not data['grade']:
            response = jsonify({
                'success': False,
                'message': 'Grade is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Check if course exists
        existing_course = db.courses.find_one({
            'name': data['name'],
            'grade': data['grade'],
            'school_id': school_id
        })
        
        if existing_course:
            response = jsonify({
                'success': False,
                'message': 'Course already exists for this grade'
            })
            return add_cors_headers(response), 400
        
        # Generate course code
        course_count = db.courses.count_documents({
            'grade': data['grade'],
            'school_id': school_id
        }) + 1
        
        school_prefix = school_id[:3].upper() if len(school_id) >= 3 else "SCH"
        course_code = data.get('code', f'{school_prefix}{data["grade"].zfill(2)}{course_count:03d}')
        
        # Process subjects
        subjects = data.get('subjects', [])
        processed_subjects = []
        
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists in this school
                subject_obj = db.subjects.find_one({
                    '_id': ObjectId(subject_id),
                    'school_id': school_id
                })
                if subject_obj:
                    processed_subjects.append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', ''),
                        'description': subject_obj.get('description', ''),
                        'credits': subject_obj.get('credits', 0)
                    })
        
        # Create course document
        course_doc = {
            'name': data['name'],
            'code': course_code,
            'grade': data['grade'],
            'description': data.get('description', ''),
            'category': data.get('category', 'general'),
            'credits': data.get('credits', 4),
            'subjects': processed_subjects,
            'school_id': school_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert course
        result = db.courses.insert_one(course_doc)
        created_course = db.courses.find_one({'_id': result.inserted_id})
        serialized_course = serialize_document(created_course)
        
        response = jsonify({
            'success': True,
            'message': 'Course created successfully',
            'course': serialized_course
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"Error in create_course: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500



# Seed subjects for all grades
@classes_bp.route('/seed-subjects', methods=['POST'])
def seed_subjects():
    """Seed default subjects for a school"""
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
    
    try:
        school_id = get_school_id_from_request()
        
        if not school_id:
            response = jsonify({
                'success': False,
                'message': 'School ID is required'
            })
            return add_cors_headers(response), 400
        
        db = get_db()
        
        # Default subjects for all grades
        default_subjects = [
            # Core Subjects
            {'name': 'English', 'description': 'English Language and Literature', 'credits': 4},
            {'name': 'Mathematics', 'description': 'Mathematics and Problem Solving', 'credits': 4},
            {'name': 'Science', 'description': 'General Science', 'credits': 4},
            {'name': 'Social Studies', 'description': 'History, Geography, Civics', 'credits': 4},
            
            # Science Subjects
            {'name': 'Physics', 'description': 'Physics and Mechanics', 'credits': 5},
            {'name': 'Chemistry', 'description': 'Chemistry and Reactions', 'credits': 5},
            {'name': 'Biology', 'description': 'Biology and Life Sciences', 'credits': 5},
            
            # Languages
            {'name': 'Second Language', 'description': 'Additional Language Study', 'credits': 3},
            
            # Computer Subjects
            {'name': 'Computer Basics', 'description': 'Basic Computer Skills', 'credits': 3},
            {'name': 'Computer Science', 'description': 'Computer Science and Programming', 'credits': 4},
            
            # Arts
            {'name': 'Drawing', 'description': 'Art and Drawing', 'credits': 2},
            
            # Physical Education
            {'name': 'Physical Education', 'description': 'Sports and Physical Activities', 'credits': 2},
            
            # Environmental Studies
            {'name': 'Environmental Studies', 'description': 'Environment and Nature Studies', 'credits': 3},
            
            # Commerce Subjects (for higher grades)
            {'name': 'Accountancy', 'description': 'Accounting and Finance', 'credits': 5},
            {'name': 'Business Studies', 'description': 'Business and Management', 'credits': 5},
            {'name': 'Economics', 'description': 'Economics and Market Studies', 'credits': 5},
        ]
        
        seeded_subjects = []
        subject_counter = db.subjects.count_documents({'school_id': school_id}) + 1
        
        for subject_data in default_subjects:
            # Check if subject already exists
            existing_subject = db.subjects.find_one({
                'name': subject_data['name'],
                'school_id': school_id
            })
            
            if not existing_subject:
                # Generate subject code
                school_prefix = school_id[:3].upper() if len(school_id) >= 3 else "SCH"
                subject_code = f'{school_prefix}SUB{subject_counter:03d}'
                
                subject_doc = {
                    'name': subject_data['name'],
                    'code': subject_code,
                    'description': subject_data['description'],
                    'credits': subject_data['credits'],
                    'school_id': school_id,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
                
                result = db.subjects.insert_one(subject_doc)
                created_subject = db.subjects.find_one({'_id': result.inserted_id})
                seeded_subjects.append(serialize_document(created_subject))
                subject_counter += 1
        
        # Now seed courses with these subjects
        seed_default_courses(school_id)
        
        response = jsonify({
            'success': True,
            'message': f'Seeded {len(seeded_subjects)} subjects and courses for school {school_id}',
            'subjects': seeded_subjects
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"Error in seed_subjects: {e}")
        response = jsonify({
            'success': False,
            'message': str(e)
        })
        return add_cors_headers(response), 500

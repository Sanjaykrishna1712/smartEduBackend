# src/routers/studentpage.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
import os
from pymongo import MongoClient
from bson import ObjectId
from bson.json_util import dumps
import json
import jwt

# Create blueprint
studentpage_bp = Blueprint('studentpage', __name__)

# MongoDB connection setup
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'SmartEducation')
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-in-production')

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

# src/routers/studentpage.py - Update the add_cors_headers function:

def add_cors_headers(response):
    """Add CORS headers to response ONLY if not already set"""
    # Check if headers are already set
    if 'Access-Control-Allow-Origin' not in response.headers:
        response.headers.add("Access-Control-Allow-Origin", "https://smartedufrontend.onrender.com")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization,X-Requested-With")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS,PATCH")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        response.headers.add("Access-Control-Max-Age", "3600")
    return response
def authenticate_token():
    """Custom authentication function for JWT tokens"""
    # Skip authentication for OPTIONS requests
    if request.method == 'OPTIONS':
        return "options_user", None
    
    auth_header = request.headers.get('Authorization')
    
    if not auth_header:
        return None, 'No authorization header'
    
    try:
        # Extract token from "Bearer <token>"
        token = auth_header.split(' ')[1]
        
        # Decode the token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # Get user_id from token (check both possible field names)
        user_id = payload.get('user_id') or payload.get('id')
        user_role = payload.get('user_role') or payload.get('role')
        
        if not user_id:
            return None, 'No user ID in token'
        
        if user_role != 'student':
            return None, 'Invalid user role'
        
        return user_id, None
    except jwt.ExpiredSignatureError:
        return None, 'Token has expired'
    except jwt.InvalidTokenError as e:
        return None, f'Invalid token: {str(e)}'
    except Exception as e:
        return None, f'Authentication error: {str(e)}'

# ==================== OPTIONS HANDLER (CORS Preflight) ====================

@studentpage_bp.route('/courses', methods=['OPTIONS'])
@studentpage_bp.route('/courses/<course_id>', methods=['OPTIONS'])
@studentpage_bp.route('/courses/<course_id>/modules', methods=['OPTIONS'])
@studentpage_bp.route('/performance', methods=['OPTIONS'])
@studentpage_bp.route('/modules/<module_id>/complete', methods=['OPTIONS'])
def handle_options(course_id=None, module_id=None):
    """Handle OPTIONS requests for CORS"""
    response = jsonify({})
    return add_cors_headers(response)

# ==================== GET STUDENT COURSES ====================

@studentpage_bp.route('/courses', methods=['GET'])
def get_student_courses():
    """Get all courses for the logged-in student"""
    try:
        # Authenticate using custom token validation
        student_id, auth_error = authenticate_token()
        
        if auth_error and student_id != "options_user":
            print(f"❌ Authentication error: {auth_error}")
            response = jsonify({
                'success': False,
                'error': auth_error
            })
            return add_cors_headers(response), 401
        
        print(f"✅ Authenticated student ID: {student_id}")
        
        client = get_mongo_client()
        db = get_db()
        
        # First, get student details
        if not ObjectId.is_valid(student_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid student ID format'
            })
            return add_cors_headers(response), 400
        
        student = db.students.find_one({'_id': ObjectId(student_id)})
        
        if not student:
            client.close()
            print(f"❌ Student not found for ID: {student_id}")
            response = jsonify({
                'success': False,
                'error': 'Student not found'
            })
            return add_cors_headers(response), 404
        
        student_data = serialize_document(student)
        
        # Extract student information
        student_class = student_data.get('class', '')
        student_section = student_data.get('section', '')
        school_id = student_data.get('school_id', '')
        
        print(f"📊 Student Info - Class: {student_class}, Section: {student_section}, School ID: {school_id}")
        
        if not student_class or not school_id:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Student class or school information not found'
            })
            return add_cors_headers(response), 400
        
        # ========== 1. Find the class document from classes collection ==========
        print(f"\n🔍 Looking for class document in 'classes' collection...")
        
        # Try to find class document - match by school_id and grade
        class_doc = db.classes.find_one({
            'school_id': school_id,
            'grade': str(student_class)
        })
        
        if not class_doc:
            # Try alternative field names
            class_doc = db.classes.find_one({
                'school_id': school_id,
                '$or': [
                    {'grade': str(student_class)},
                    {'name': f"Class {student_class}"},
                    {'name': student_class}
                ]
            })
        
        if not class_doc:
            client.close()
            print(f"❌ No class document found for grade {student_class} in school {school_id}")
            response = jsonify({
                'success': True,
                'courses': [],
                'stats': {
                    'total_courses': 0,
                    'active_courses': 0,
                    'completed_courses': 0,
                    'total_progress': 0,
                    'total_hours_spent': 0,
                    'average_gpa': 0,
                    'student_info': {
                        'name': student_data.get('name', ''),
                        'class': student_class,
                        'section': student_section,
                        'roll_number': student_data.get('roll_number', ''),
                        'email': student_data.get('email', '')
                    }
                },
                'message': f'No class found for grade {student_class}'
            })
            return add_cors_headers(response), 200
        
        class_data = serialize_document(class_doc)
        print(f"✅ Found class document: {class_data.get('name')}")
        
        # ========== 2. Extract course IDs from class document ==========
        course_ids = []
        if 'courses' in class_data and class_data['courses']:
            for course_ref in class_data['courses']:
                if isinstance(course_ref, dict):
                    # Handle {'id': '...', 'name': '...', 'code': '...'} format
                    course_id = course_ref.get('id')
                    if course_id:
                        course_ids.append(course_id)
                elif isinstance(course_ref, str):
                    # Handle simple string ID format
                    course_ids.append(course_ref)
        
        print(f"📊 Course IDs from class: {course_ids}")
        
        if not course_ids:
            client.close()
            print(f"⚠️ No course IDs found in class document")
            response = jsonify({
                'success': True,
                'courses': [],
                'stats': {
                    'total_courses': 0,
                    'active_courses': 0,
                    'completed_courses': 0,
                    'total_progress': 0,
                    'total_hours_spent': 0,
                    'average_gpa': 0,
                    'student_info': {
                        'name': student_data.get('name', ''),
                        'class': student_class,
                        'section': student_section,
                        'roll_number': student_data.get('roll_number', ''),
                        'email': student_data.get('email', '')
                    }
                },
                'message': 'No courses assigned to this class'
            })
            return add_cors_headers(response), 200
        
        # ========== 3. Fetch actual course details from courses collection ==========
        print(f"\n🔍 Fetching course details from 'courses' collection...")
        
        courses_list = []
        for course_id in course_ids:
            if ObjectId.is_valid(course_id):
                course = db.courses.find_one({'_id': ObjectId(course_id)})
                if course:
                    courses_list.append(course)
                else:
                    print(f"⚠️ Course not found with ID: {course_id}")
            else:
                print(f"⚠️ Invalid course ID format: {course_id}")
        
        print(f"📊 Found {len(courses_list)} actual courses")
        
        # ========== 4. Process and format courses ==========
        courses = []
        for course in courses_list:
            course_data = serialize_document(course)
            
            # Get teacher details
            teacher_id = course_data.get('teacher_id')
            teacher = None
            if teacher_id and ObjectId.is_valid(teacher_id):
                teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
            
            # Get modules for this course - FIXED: Use count_documents() instead of cursor.count()
            modules_count = db.modules.count_documents({
                'course_id': str(course['_id']),
                'is_active': True
            })
            
            # Get student progress for this course
            progress_data = db.student_progress.find_one({
                'student_id': student_id,
                'course_id': str(course['_id'])
            })
            
            # Calculate progress percentage
            if progress_data:
                completed_modules = len(progress_data.get('completed_modules', []))
                progress_percentage = (completed_modules / modules_count * 100) if modules_count > 0 else 0
            else:
                completed_modules = 0
                progress_percentage = 0
            
            # Determine status based on progress
            if progress_percentage == 100:
                status = 'completed'
            elif progress_percentage > 0:
                status = 'active'
            else:
                status = 'upcoming'
            
            # Get next lesson/module
            next_lesson = None
            if modules_count > completed_modules and progress_data:
                next_module = db.modules.find_one({
                    'course_id': str(course['_id']),
                    'order': completed_modules + 1
                })
                if next_module:
                    next_lesson = next_module.get('title')
            
            # Get course difficulty
            difficulty = course_data.get('difficulty', 'intermediate')
            if difficulty not in ['beginner', 'intermediate', 'advanced']:
                difficulty = 'intermediate'
            
            # Find course name from class document (for better display)
            course_name_in_class = None
            if 'courses' in class_data:
                for course_ref in class_data['courses']:
                    if isinstance(course_ref, dict) and course_ref.get('id') == str(course['_id']):
                        course_name_in_class = course_ref.get('name')
                        break
            
            courses.append({
                'id': course_data['_id'],
                'title': course_name_in_class or course_data.get('course_name', course_data.get('name', 'Untitled Course')),
                'subject': course_data.get('subject', 'General'),
                'instructor': teacher.get('name', 'Unknown Teacher') if teacher else 'Unknown Teacher',
                'progress': round(progress_percentage, 2),
                'duration': course_data.get('duration', '12 weeks'),
                'modules': modules_count,
                'completedModules': completed_modules,
                'difficulty': difficulty,
                'rating': float(course_data.get('rating', 4.5)),
                'enrolledDate': student_data.get('admission_date', datetime.now().isoformat()),
                'nextLesson': next_lesson,
                'status': status,
                'thumbnailColor': course_data.get('thumbnail_color', 'bg-gradient-to-r from-blue-500 to-cyan-500'),
                'description': course_data.get('description', ''),
                'course_code': course_data.get('course_code', ''),
                'start_date': course_data.get('start_date', ''),
                'end_date': course_data.get('end_date', ''),
                'teacher_id': str(teacher['_id']) if teacher else None,
                'teacher_email': teacher.get('email') if teacher else None,
                'class': student_class,
                'section': student_section
            })
        
        client.close()
        
        # ========== 5. Calculate statistics ==========
        total_courses = len(courses)
        active_courses = len([c for c in courses if c['status'] == 'active'])
        completed_courses = len([c for c in courses if c['status'] == 'completed'])
        total_progress = sum(c['progress'] for c in courses) / total_courses if total_courses > 0 else 0
        
        # Calculate total hours spent - FIXED: Use list() instead of cursor.count()
        total_hours_aggregation = list(db.student_activity.aggregate([
            {'$match': {'student_id': student_id}},
            {'$group': {'_id': None, 'total_hours': {'$sum': '$duration_hours'}}}
        ]))
        total_hours_spent = total_hours_aggregation[0]['total_hours'] if total_hours_aggregation else 0
        
        # Get average GPA - FIXED: Use list() instead of cursor
        grades = list(db.grades.find({'student_id': student_id}))
        average_gpa = sum(g['gpa'] for g in grades) / len(grades) if grades else 0
        
        stats = {
            'total_courses': total_courses,
            'active_courses': active_courses,
            'completed_courses': completed_courses,
            'total_progress': round(total_progress, 1),
            'total_hours_spent': round(total_hours_spent, 1),
            'average_gpa': round(average_gpa, 2),
            'student_info': {
                'name': student_data.get('name', ''),
                'class': student_class,
                'section': student_section,
                'roll_number': student_data.get('roll_number', ''),
                'email': student_data.get('email', '')
            }
        }
        
        print(f"✅ Returning {total_courses} courses for student")
        
        response_data = {
            'success': True,
            'courses': courses,
            'stats': stats,
            'debug_info': {
                'student_class': student_class,
                'student_section': student_section,
                'school_id': school_id,
                'class_found': class_data.get('name') if class_data else None,
                'course_ids_in_class': len(course_ids),
                'courses_found': total_courses
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error getting student courses: {str(e)}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': f'Failed to fetch courses: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== GET STUDENT PERFORMANCE ====================

@studentpage_bp.route('/performance', methods=['GET'])
def get_student_performance():
    """Get student performance analytics"""
    try:
        # Authenticate using custom token validation
        student_id, auth_error = authenticate_token()
        
        if auth_error and student_id != "options_user":
            response = jsonify({
                'success': False,
                'error': auth_error
            })
            return add_cors_headers(response), 401
        
        client = get_mongo_client()
        db = get_db()
        
        # Get student details
        if not ObjectId.is_valid(student_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid student ID format'
            })
            return add_cors_headers(response), 400
            
        student = db.students.find_one({'_id': ObjectId(student_id)})
        if not student:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Student not found'
            })
            return add_cors_headers(response), 404
        
        student_data = serialize_document(student)
        
        # Get student class and section (handle different field names)
        student_class = (
            student_data.get('class') or 
            student_data.get('class_level') or 
            student_data.get('grade') or 
            student_data.get('current_class') or
            '11'
        )
        
        student_section = (
            student_data.get('section') or 
            student_data.get('section_name') or 
            student_data.get('stream') or
            'B'
        )
        
        school_id = student_data.get('school_id') or student_data.get('school')
        
        # Get all grades for this student
        grades = list(db.grades.find({'student_id': student_id}))
        
        # Calculate statistics
        total_assignments = len(grades)
        average_score = sum(g['score'] for g in grades) / total_assignments if total_assignments > 0 else 0
        average_gpa = sum(g['gpa'] for g in grades) / total_assignments if total_assignments > 0 else 0
        
        # Get subject-wise performance
        subject_performance = []
        if grades and school_id:
            # Get all courses for this student's class and school
            courses_list = list(db.courses.find({
                'school_id': school_id,
                'class': str(student_class),
                'is_active': True
            }))
            
            for course in courses_list:
                course_data = serialize_document(course)
                course_grades = []
                
                # Check if grades belong to this course via modules
                for grade in grades:
                    if grade.get('module_id'):
                        module = db.modules.find_one({'_id': ObjectId(grade.get('module_id'))})
                        if module and module.get('course_id') == str(course['_id']):
                            course_grades.append(grade)
                
                if course_grades:
                    subject_avg = sum(g['score'] for g in course_grades) / len(course_grades)
                    subject_performance.append({
                        'subject': course_data.get('subject', 'Unknown'),
                        'average_score': round(subject_avg, 2),
                        'total_assignments': len(course_grades)
                    })
        
        # Get attendance
        attendance_records = list(db.attendance.find({'student_id': student_id}))
        
        total_days = len(attendance_records)
        present_days = len([r for r in attendance_records if r.get('status') == 'present'])
        
        attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
        
        # Get recent activity
        recent_activity = list(db.student_activity.find({
            'student_id': student_id
        }).sort('timestamp', -1).limit(10))
        
        formatted_activity = []
        for activity in recent_activity:
            formatted_activity.append({
                'action': activity.get('action'),
                'duration_hours': activity.get('duration_hours', 0),
                'resource_type': activity.get('resource_type'),
                'resource_id': activity.get('resource_id'),
                'timestamp': activity.get('timestamp')
            })
        
        client.close()
        
        response_data = {
            'success': True,
            'performance': {
                'attendance_percentage': round(attendance_percentage, 2),
                'average_score': round(average_score, 2),
                'average_gpa': round(average_gpa, 2),
                'total_assignments': total_assignments,
                'subject_performance': subject_performance,
                'recent_activity': formatted_activity,
                'student_info': {
                    'name': student_data.get('name', student_data.get('fullName', '')),
                    'class': student_class,
                    'section': student_section,
                    'roll_number': student_data.get('roll_number', '')
                }
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error getting student performance: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to fetch performance data: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== GET COURSE MODULES ====================

@studentpage_bp.route('/courses/<course_id>/modules', methods=['GET'])
def get_course_modules(course_id):
    """Get all modules for a specific course"""
    try:
        # Authenticate using custom token validation
        student_id, auth_error = authenticate_token()
        
        if auth_error and student_id != "options_user":
            response = jsonify({
                'success': False,
                'error': auth_error
            })
            return add_cors_headers(response), 401
        
        client = get_mongo_client()
        db = get_db()
        
        # Verify course exists
        if not ObjectId.is_valid(course_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid course ID format'
            })
            return add_cors_headers(response), 400
        
        course = db.courses.find_one({'_id': ObjectId(course_id)})
        if not course:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Course not found'
            })
            return add_cors_headers(response), 404
        
        course_data = serialize_document(course)
        
        # Get student details
        if not ObjectId.is_valid(student_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid student ID format'
            })
            return add_cors_headers(response), 400
            
        student = db.students.find_one({'_id': ObjectId(student_id)})
        if not student:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Student not found'
            })
            return add_cors_headers(response), 404
        
        student_data = serialize_document(student)
        
        # Get student class and section
        student_class = (
            student_data.get('class') or 
            student_data.get('class_level') or 
            student_data.get('grade') or 
            student_data.get('current_class')
        )
        
        student_section = (
            student_data.get('section') or 
            student_data.get('section_name') or 
            student_data.get('stream')
        )
        
        # Check if student is enrolled in this course
        if (student_class and student_class != course_data.get('class')) or \
           (student_section and student_section != course_data.get('section')):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'You are not enrolled in this course'
            })
            return add_cors_headers(response), 403
        
        # Get modules
        modules_list = list(db.modules.find({
            'course_id': course_id,
            'is_active': True
        }).sort('order', 1))
        
        modules = []
        for module in modules_list:
            module_data = serialize_document(module)
            
            # Get student progress for this module
            progress = db.student_progress.find_one({
                'student_id': student_id,
                'course_id': course_id,
                'module_id': str(module['_id'])
            })
            
            # Get grade if available
            grade = db.grades.find_one({
                'student_id': student_id,
                'module_id': str(module['_id'])
            })
            
            modules.append({
                'id': module_data['_id'],
                'title': module_data.get('title', 'Untitled Module'),
                'description': module_data.get('description', ''),
                'type': module_data.get('type', 'reading'),
                'duration': module_data.get('duration', '30 min'),
                'content_url': module_data.get('content_url', ''),
                'resources': module_data.get('resources', []),
                'order': module_data.get('order', 0),
                'completed': bool(progress),
                'completed_at': progress.get('completed_at') if progress else None,
                'score': grade.get('score') if grade else None,
                'grade': grade.get('grade') if grade else None,
                'due_date': module_data.get('due_date'),
                'created_at': module_data.get('created_at')
            })
        
        # Get course progress
        total_modules = len(modules)
        completed_modules = len([m for m in modules if m['completed']])
        progress_percentage = (completed_modules / total_modules * 100) if total_modules > 0 else 0
        
        # Get next module to complete
        next_module = None
        for module in modules:
            if not module['completed']:
                next_module = module
                break
        
        client.close()
        
        response_data = {
            'success': True,
            'modules': modules,
            'course_progress': {
                'total_modules': total_modules,
                'completed_modules': completed_modules,
                'progress_percentage': round(progress_percentage, 2),
                'next_module': next_module
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error getting course modules: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to fetch modules: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== MARK MODULE AS COMPLETE ====================

@studentpage_bp.route('/modules/<module_id>/complete', methods=['POST'])
def mark_module_complete(module_id):
    """Mark a module as complete for the student"""
    try:
        # Authenticate using custom token validation
        student_id, auth_error = authenticate_token()
        
        if auth_error and student_id != "options_user":
            response = jsonify({
                'success': False,
                'error': auth_error
            })
            return add_cors_headers(response), 401
        
        client = get_mongo_client()
        db = get_db()
        
        # Verify module exists
        if not ObjectId.is_valid(module_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid module ID format'
            })
            return add_cors_headers(response), 400
        
        module = db.modules.find_one({'_id': ObjectId(module_id)})
        if not module:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Module not found'
            })
            return add_cors_headers(response), 404
        
        module_data = serialize_document(module)
        course_id = module_data.get('course_id')
        
        # Check if already completed
        existing_progress = db.student_progress.find_one({
            'student_id': student_id,
            'course_id': course_id,
            'module_id': module_id
        })
        
        if existing_progress:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Module already completed'
            })
            return add_cors_headers(response), 400
        
        # Get time spent from request
        time_spent = 0
        if request.is_json:
            data = request.get_json()
            time_spent = data.get('time_spent_minutes', 0)
        
        # Add to progress
        progress_data = {
            'student_id': student_id,
            'course_id': course_id,
            'module_id': module_id,
            'completed_at': datetime.now(),
            'time_spent_minutes': time_spent
        }
        
        db.student_progress.insert_one(progress_data)
        
        # Log activity
        activity_data = {
            'student_id': student_id,
            'action': 'module_completed',
            'resource_type': 'module',
            'resource_id': module_id,
            'duration_hours': time_spent / 60 if time_spent else 0,
            'timestamp': datetime.now()
        }
        
        db.student_activity.insert_one(activity_data)
        
        client.close()
        
        response = jsonify({
            'success': True,
            'message': 'Module marked as complete'
        })
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error marking module complete: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to mark module complete: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== GET COURSE DETAILS ====================

@studentpage_bp.route('/courses/<course_id>', methods=['GET'])
def get_course_details(course_id):
    """Get detailed information about a specific course"""
    try:
        # Authenticate using custom token validation
        student_id, auth_error = authenticate_token()
        
        if auth_error and student_id != "options_user":
            response = jsonify({
                'success': False,
                'error': auth_error
            })
            return add_cors_headers(response), 401
        
        client = get_mongo_client()
        db = get_db()
        
        # Verify course ID format
        if not ObjectId.is_valid(course_id):
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Invalid course ID format'
            })
            return add_cors_headers(response), 400
        
        # Get course
        course = db.courses.find_one({'_id': ObjectId(course_id)})
        if not course:
            client.close()
            response = jsonify({
                'success': False,
                'error': 'Course not found'
            })
            return add_cors_headers(response), 404
        
        course_data = serialize_document(course)
        
        # Get teacher details
        teacher = None
        teacher_id = course_data.get('teacher_id')
        if teacher_id and ObjectId.is_valid(teacher_id):
            teacher = db.teachers.find_one({'_id': ObjectId(teacher_id)})
        
        # Get modules count
        modules_count = db.modules.count_documents({
            'course_id': course_id,
            'is_active': True
        })
        
        # Get student progress
        completed_modules = list(db.student_progress.find({
            'student_id': student_id,
            'course_id': course_id
        }))
        
        progress_percentage = (len(completed_modules) / modules_count * 100) if modules_count > 0 else 0
        
        # Get upcoming assignments
        upcoming_assignments = list(db.assignments.find({
            'course_id': course_id,
            'due_date': {'$gte': datetime.now()}
        }).sort('due_date', 1).limit(5))
        
        assignments_list = []
        for assignment in upcoming_assignments:
            assignments_list.append({
                'id': str(assignment['_id']),
                'title': assignment.get('title'),
                'description': assignment.get('description'),
                'due_date': assignment.get('due_date'),
                'max_score': assignment.get('max_score'),
                'type': assignment.get('type')
            })
        
        # Get course resources
        resources_list = list(db.course_resources.find({
            'course_id': course_id,
            'is_active': True
        }))
        
        resources = []
        for resource in resources_list:
            resources.append({
                'id': str(resource['_id']),
                'title': resource.get('title'),
                'type': resource.get('type'),
                'url': resource.get('url'),
                'size': resource.get('size'),
                'uploaded_at': resource.get('uploaded_at')
            })
        
        client.close()
        
        response_data = {
            'success': True,
            'course': {
                'id': course_data['_id'],
                'title': course_data.get('course_name'),
                'description': course_data.get('description'),
                'subject': course_data.get('subject'),
                'class': course_data.get('class'),
                'section': course_data.get('section'),
                'duration': course_data.get('duration'),
                'difficulty': course_data.get('difficulty', 'intermediate'),
                'rating': float(course_data.get('rating', 4.5)),
                'start_date': course_data.get('start_date'),
                'end_date': course_data.get('end_date'),
                'thumbnail_color': course_data.get('thumbnail_color', 'bg-gradient-to-r from-blue-500 to-cyan-500'),
                'teacher': {
                    'name': teacher.get('name') if teacher else 'Unknown',
                    'email': teacher.get('email') if teacher else None,
                    'phone': teacher.get('phone') if teacher else None
                },
                'modules_count': modules_count,
                'progress_percentage': round(progress_percentage, 2),
                'upcoming_assignments': assignments_list,
                'resources': resources
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response), 200
        
    except Exception as e:
        print(f"❌ Error getting course details: {str(e)}")
        response = jsonify({
            'success': False,
            'error': f'Failed to fetch course details: {str(e)}'
        })
        return add_cors_headers(response), 500

# ==================== AFTER REQUEST CORS ====================

@studentpage_bp.after_request
def after_request(response):
    """Add CORS headers to all responses"""
    return add_cors_headers(response)

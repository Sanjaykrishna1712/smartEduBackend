# app/routes/quiz_routes.py
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
from bson import ObjectId
import jwt
import math
from functools import wraps
# Add this import at the top
from flask import make_response

quiz_bp = Blueprint('quiz', __name__)
# Add this helper function
def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers['Access-Control-Allow-Origin'] = 'https://smartedufrontend.onrender.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# Add OPTIONS method handler for preflight requests
@quiz_bp.route('/quizzes', methods=['OPTIONS'])
def handle_options():
    """Handle CORS preflight requests"""
    response = make_response()
    response.headers['Access-Control-Allow-Origin'] = 'https://smartedufrontend.onrender.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response
# Create blueprint

# Helper function to validate JSON fields
def validate_required_fields(data, required_fields):
    missing_fields = []
    for field in required_fields:
        if field not in data or (isinstance(data[field], str) and not data[field].strip()):
            missing_fields.append(field)
    return missing_fields

# Helper to get school_id from request (same as your students.py)
def get_school_id_from_request():
    """Extract school_id from request with multiple fallbacks"""
    school_id = None
    
    # 1. Check Authorization header first
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            jwt_secret = current_app.config.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
            
            # 👇 ADD DEBUG
            print(f"🔐 [get_school_id] Token check, first 20 chars: {token[:20]}...")
            
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            school_id = payload.get('school_id', '').strip()
            print(f"✅ [get_school_id] School ID from token: '{school_id}'")
        except jwt.InvalidTokenError as e:
            print(f"❌ [get_school_id] JWT decode failed: {str(e)}")
        except Exception as e:
            print(f"❌ [get_school_id] Unexpected error: {str(e)}")
    
    # 2. Check query parameter
    if not school_id:
        school_id = request.args.get('school_id', '').strip()
        if school_id:
            print(f"📋 [get_school_id] Using school_id from query param: '{school_id}'")
    
    # 3. Check JSON body
    if not school_id and request.method in ['POST', 'PUT', 'DELETE']:
        try:
            data = request.get_json(silent=True) or {}
            school_id = data.get('school_id', '').strip()
            if school_id:
                print(f"📋 [get_school_id] Using school_id from JSON body: '{school_id}'")
        except:
            pass
    
    return school_id

def get_current_user_id():
    """Get current user ID from JWT token"""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            jwt_secret = current_app.config.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            
            # 👇 ADD THESE DEBUG LINES
            print("🔐 JWT Token Payload:", payload)
            print("🔍 Looking for user_id:", payload.get('user_id'))
            print("🔍 Looking for id:", payload.get('id'))
            
            return payload.get('user_id') or payload.get('id')
        except Exception as e:
            print("❌ JWT Decode Error:", str(e))
            pass
    return None

def get_user_role():
    """Get user role from JWT token"""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            jwt_secret = current_app.config.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            return payload.get('role')
        except:
            pass
    return None

def get_user_class():
    """Get user class from JWT token (for students)"""
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            jwt_secret = current_app.config.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
            
            # 👇 ADD DEBUG: Print token info (first 20 chars)
            print(f"🔐 Token first 20 chars: {token[:20]}...")
            print(f"🔐 JWT Secret configured: {jwt_secret[:10]}..." if jwt_secret else "❌ No JWT secret!")
            
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
            
            print(f"🔍 JWT Payload decoded: {payload}")
            
            class_value = payload.get('class')
            
            if class_value is None:
                print("⚠️ 'class' field not found in JWT payload")
                return None
            
            if isinstance(class_value, str) and class_value.strip() == '':
                print("⚠️ 'class' field is empty string")
                return None
            
            print(f"✅ Found class in token: {class_value}")
            return class_value
            
        except jwt.ExpiredSignatureError:
            print("❌ JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            print(f"❌ Invalid JWT token: {str(e)}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error decoding JWT: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    else:
        print("⚠️ No Authorization header found")
    return None
# ==================== QUESTION BANK ROUTES ====================

@quiz_bp.route('/question-bank', methods=['GET'])
def get_question_bank():
    """Get all questions from question bank with school_id filtering"""
    try:
        # Get school_id
        school_id = get_school_id_from_request()
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        # Get query parameters
        subject = request.args.get('subject', '')
        topic = request.args.get('topic', '')
        difficulty = request.args.get('difficulty', '')
        question_type = request.args.get('question_type', '')
        search = request.args.get('search', '')
        question_class = request.args.get('class', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        
        # Build query - filter by school_id
        query = {'school_id': school_id}
        
        # Apply filters
        if subject:
            query['subject'] = subject
        
        if topic:
            query['topic'] = topic
        
        if difficulty:
            query['difficulty'] = difficulty
        
        if question_type:
            query['question_type'] = question_type
        
        if question_class:
            query['class'] = question_class
        
        if search:
            query['$or'] = [
                {'question_text': {'$regex': search, '$options': 'i'}},
                {'topic': {'$regex': search, '$options': 'i'}},
                {'tags': {'$regex': search, '$options': 'i'}}
            ]
        
        print(f"📋 Question bank query for school {school_id}: {query}")
        
        # Get questions from MongoDB
        db = current_app.db
        total = db.question_bank.count_documents(query)
        skip = (page - 1) * limit
        
        questions_cursor = db.question_bank.find(query)\
            .sort('updated_at', -1)\
            .skip(skip)\
            .limit(limit)
        
        questions = list(questions_cursor)
        
        # Convert ObjectId to string
        question_list = []
        for q in questions:
            q['id'] = str(q['_id'])
            del q['_id']
            question_list.append(q)
        
        # Get unique values for filtering from same school
        subjects = db.question_bank.distinct('subject', {'school_id': school_id})
        topics = db.question_bank.distinct('topic', {'school_id': school_id})
        difficulties = db.question_bank.distinct('difficulty', {'school_id': school_id})
        classes = db.question_bank.distinct('class', {'school_id': school_id})
        question_types = db.question_bank.distinct('question_type', {'school_id': school_id})
        
        # Get all tags from same school
        all_tags = set()
        for q in questions:
            if 'tags' in q and q['tags']:
                all_tags.update(q['tags'])
        
        return jsonify({
            'questions': question_list,
            'subjects': subjects,
            'topics': topics,
            'difficulties': list(difficulties),
            'classes': [c for c in classes if c],
            'question_types': question_types,
            'tags': list(all_tags),
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if limit > 0 else 1
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching question bank: {str(e)}")
        return jsonify({'error': f'Failed to fetch question bank: {str(e)}'}), 500

@quiz_bp.route('/question-bank/filters', methods=['GET'])
def get_question_bank_filters():
    """Get available filters for question bank"""
    try:
        # Get school_id
        school_id = get_school_id_from_request()
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        db = current_app.db
        
        # Get unique values from MongoDB for this school
        subjects = db.question_bank.distinct('subject', {'school_id': school_id})
        topics = db.question_bank.distinct('topic', {'school_id': school_id})
        classes = db.question_bank.distinct('class', {'school_id': school_id})
        
        # Get all tags from this school
        questions = list(db.question_bank.find({'school_id': school_id}))
        all_tags = set()
        for q in questions:
            if 'tags' in q and q['tags']:
                all_tags.update(q['tags'])
        
        question_types = ['multiple_choice', 'short_answer', 'numerical', 'true_false']
        difficulties = ['easy', 'medium', 'hard']
        
        return jsonify({
            'subjects': subjects,
            'topics': topics,
            'question_types': question_types,
            'difficulties': difficulties,
            'classes': [c for c in classes if c],
            'tags': list(all_tags)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching question bank filters: {str(e)}")
        return jsonify({'error': 'Failed to fetch filters'}), 500

@quiz_bp.route('/question-bank', methods=['POST'])
def add_to_question_bank():
    """Add a new question to the question bank"""
    try:
        # Get school_id and user_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        # Check if request has JSON
        if not request.is_json:
            return jsonify({'error': 'Missing JSON in request'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['question_text', 'question_type', 'subject', 'topic', 'correct_answer', 'points', 'class']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        # Check for duplicate question within same school
        db = current_app.db
        existing_question = db.question_bank.find_one({
            'question_text': data['question_text'].strip(),
            'subject': data['subject'],
            'school_id': school_id
        })
        
        if existing_question:
            return jsonify({'error': 'This question already exists in your school\'s question bank'}), 409
        
        # Create new question document
        question_doc = {
            'question_text': data['question_text'].strip(),
            'question_type': data['question_type'],
            'subject': data['subject'],
            'topic': data['topic'].strip(),
            'correct_answer': data['correct_answer'],
            'explanation': data.get('explanation', '').strip(),
            'points': int(data['points']),
            'difficulty': data.get('difficulty', 'medium'),
            'time_estimate': data.get('time_estimate', 2),
            'tags': data.get('tags', []),
            'class': data['class'],
            'created_by': user_id or 'unknown',
            'school_id': school_id,
            'is_reusable': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Handle options for multiple choice questions
        if data['question_type'] == 'multiple_choice':
            if 'options' not in data or not isinstance(data['options'], list) or len(data['options']) < 2:
                return jsonify({'error': 'Multiple choice questions require at least 2 options'}), 400
            question_doc['options'] = data['options']
        
        # Insert into MongoDB
        result = db.question_bank.insert_one(question_doc)
        question_doc['id'] = str(result.inserted_id)
        del question_doc['_id']
        
        return jsonify({
            'message': 'Question added to question bank successfully',
            'question': question_doc
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error adding to question bank: {str(e)}")
        return jsonify({'error': f'Failed to add question to bank: {str(e)}'}), 500

# ==================== QUIZ ROUTES ====================

@quiz_bp.route('/quizzes', methods=['GET'])
def get_quizzes():
    """Get all quizzes for the current teacher with school_id filtering"""
    try:
        # Get school_id and user info
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        user_role = get_user_role()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        # Get query parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        subject = request.args.get('subject', '')
        quiz_class = request.args.get('class', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # Build query - filter by school_id
        query = {'school_id': school_id}
        
        # Teachers can only see their own quizzes
        if user_role == 'teacher' and user_id:
            query['teacher_id'] = user_id
        
        if status:
            query['status'] = status
        
        if subject:
            query['subject'] = subject
        
        if quiz_class:
            query['class'] = quiz_class
        
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}},
                {'subject': {'$regex': search, '$options': 'i'}}
            ]
        
        print(f"📋 Quizzes query for school {school_id}: {query}")
        
        # Get quizzes from MongoDB
        db = current_app.db
        total = db.quizzes.count_documents(query)
        skip = (page - 1) * limit
        
        quizzes_cursor = db.quizzes.find(query)\
            .sort('updated_at', -1)\
            .skip(skip)\
            .limit(limit)
        
        quizzes = list(quizzes_cursor)
        
        # Convert ObjectId to string
        quiz_list = []
        for quiz in quizzes:
            quiz['id'] = str(quiz['_id'])
            del quiz['_id']
            
            # Convert question IDs
            if 'questions' in quiz:
                for q in quiz['questions']:
                    if '_id' in q:
                        q['id'] = str(q['_id'])
                        del q['_id']
            
            quiz_list.append(quiz)
        
        # Get unique subjects for filter from same school
        subjects = db.quizzes.distinct('subject', {'school_id': school_id})
        classes = db.quizzes.distinct('class', {'school_id': school_id})
        
        return jsonify({
            'quizzes': quiz_list,
            'subjects': subjects,
            'classes': [c for c in classes if c],
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if limit > 0 else 1
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching quizzes: {str(e)}")
        return jsonify({'error': f'Failed to fetch quizzes: {str(e)}'}), 500

@quiz_bp.route('/quizzes', methods=['POST'])
def create_quiz():
    """Create a new quiz from selected questions"""
    try:
        print("🔧 CREATE QUIZ - Request received")
        print(f"🔧 Headers: {dict(request.headers)}")
        
        # Debug: Check Authorization header
        auth_header = request.headers.get('Authorization')
        print(f"🔧 Authorization Header: {auth_header}")
        
        # Get school_id and user_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        print(f"🔧 School ID: {school_id}")
        print(f"🔧 User ID: {user_id}")
        
        # TEMPORARY FIX: If no user_id from token, try to get from body
        if not user_id:
            print("⚠️ No user_id from token, checking request body...")
            try:
                data = request.get_json(silent=True) or {}
                user_id = data.get('teacher_id') or data.get('user_id')
                print(f"⚠️ User ID from body: {user_id}")
            except:
                pass
        
        # Validation
        if not school_id:
            print("❌ School ID missing")
            response = jsonify({'error': 'School ID is required'})
            return add_cors_headers(response), 400
        
        if not user_id:
            print("❌ User ID missing - authentication failed")
            response = jsonify({'error': 'User authentication required'})
            return add_cors_headers(response), 401
        
        # Parse request data
        if not request.is_json:
            print("❌ Request is not JSON")
            response = jsonify({'error': 'Missing JSON in request'})
            return add_cors_headers(response), 400
            
        data = request.get_json()
        if not data:
            print("❌ No data provided")
            response = jsonify({'error': 'No data provided'})
            return add_cors_headers(response), 400
        
        print(f"🔧 Request data keys: {list(data.keys())}")
        print(f"🔧 Questions count: {len(data.get('questions', []))}")
        
        # Validate required fields
        required_fields = ['title', 'subject', 'class', 'questions']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            print(f"❌ Missing fields: {missing_fields}")
            response = jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'})
            return add_cors_headers(response), 400
        
        print(f"🔧 Quiz Title: {data['title']}")
        print(f"🔧 Subject: {data['subject']}")
        print(f"🔧 Class: {data['class']}")
        
        # Check for duplicate quiz title
        db = current_app.db
        existing_quiz = db.quizzes.find_one({
            'title': data['title'].strip(),
            'teacher_id': user_id,
            'school_id': school_id
        })
        
        if existing_quiz:
            print(f"❌ Duplicate quiz: {data['title']}")
            response = jsonify({'error': 'A quiz with this title already exists in your school'})
            return add_cors_headers(response), 409
        
        # Verify all questions exist
        question_bank_ids = []
        for q in data['questions']:
            if 'question_bank_id' in q and ObjectId.is_valid(q['question_bank_id']):
                question_bank_ids.append(ObjectId(q['question_bank_id']))
        
        if question_bank_ids:
            print(f"🔧 Question IDs: {[str(id) for id in question_bank_ids]}")
            
            question_count = db.question_bank.count_documents({
                '_id': {'$in': question_bank_ids},
                'school_id': school_id
            })
            
            print(f"🔧 Questions Found: {question_count}/{len(question_bank_ids)}")
            
            if question_count != len(question_bank_ids):
                print("❌ Some questions not found or unauthorized")
                response = jsonify({'error': 'One or more questions not found or unauthorized'})
                return add_cors_headers(response), 400
        
        # Create quiz questions
        questions = []
        total_points = 0
        
        for index, question_data in enumerate(data['questions'], 1):
            if 'question_bank_id' in question_data and ObjectId.is_valid(question_data['question_bank_id']):
                question_bank = db.question_bank.find_one({
                    '_id': ObjectId(question_data['question_bank_id']),
                    'school_id': school_id
                })
                
                if not question_bank:
                    print(f"⚠️ Question {question_data['question_bank_id']} not found")
                    continue
                
                question = {
                    'question_bank_id': str(question_bank['_id']),
                    'question_text': question_bank['question_text'],
                    'question_type': question_bank['question_type'],
                    'options': question_bank.get('options'),
                    'correct_answer': question_bank['correct_answer'],
                    'explanation': question_bank.get('explanation', ''),
                    'points': question_bank['points'],
                    'difficulty': question_bank.get('difficulty', 'medium'),
                    'subject': question_bank['subject'],
                    'topic': question_bank['topic'],
                    'class': question_bank.get('class', ''),
                    'time_estimate': question_bank.get('time_estimate', 2),
                    'tags': question_bank.get('tags', []),
                    'order_index': index
                }
                print(f"🔧 Q{index} from bank: {question_bank['question_text'][:50]}...")
            else:
                question = {
                    'question_text': question_data.get('question_text', '').strip(),
                    'question_type': question_data.get('question_type', 'multiple_choice'),
                    'correct_answer': question_data.get('correct_answer', ''),
                    'explanation': question_data.get('explanation', '').strip(),
                    'points': int(question_data.get('points', 1)),
                    'difficulty': question_data.get('difficulty', 'medium'),
                    'subject': data['subject'],
                    'topic': question_data.get('topic', 'General').strip(),
                    'class': data.get('class', ''),
                    'time_estimate': question_data.get('time_estimate', 2),
                    'tags': question_data.get('tags', []),
                    'order_index': index
                }
                
                if question['question_type'] == 'multiple_choice':
                    if 'options' in question_data and isinstance(question_data['options'], list):
                        question['options'] = question_data['options']
                
                print(f"🔧 Q{index} new: {question['question_text'][:50]}...")
            
            total_points += question.get('points', 0)
            questions.append(question)
        
        print(f"🔧 Total Points: {total_points}")
        print(f"🔧 Questions Count: {len(questions)}")
        
        # Create quiz document
        quiz_doc = {
            'title': data['title'].strip(),
            'subject': data['subject'],
            'description': data.get('description', '').strip(),
            'class': data['class'],
            'teacher_id': user_id,
            'teacher_name': data.get('teacher_name', 'Teacher'),
            'school_id': school_id,
            'time_limit': int(data.get('time_limit', 60)),
            'status': data.get('status', 'draft'),
            'total_points': total_points,
            'questions': questions,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        print(f"🔧 Quiz Document: Title={quiz_doc['title']}, Teacher={quiz_doc['teacher_id']}, Questions={len(quiz_doc['questions'])}")
        
        # Insert into MongoDB
        result = db.quizzes.insert_one(quiz_doc)
        quiz_doc['id'] = str(result.inserted_id)
        del quiz_doc['_id']
        
        print(f"✅ SUCCESS: Quiz created with ID: {quiz_doc['id']}")
        
        response = jsonify({
            'message': 'Quiz created successfully',
            'quiz': quiz_doc
        })
        
        return add_cors_headers(response), 201
        
    except Exception as e:
        print(f"❌ EXCEPTION: Error creating quiz: {str(e)}")
        import traceback
        print(f"❌ TRACEBACK: {traceback.format_exc()}")
        current_app.logger.error(f"Error creating quiz: {str(e)}")
        response = jsonify({'error': f'Failed to create quiz: {str(e)}'})
        return add_cors_headers(response), 500
@quiz_bp.route('/quizzes/<quiz_id>', methods=['DELETE'])
def delete_quiz(quiz_id):
    """Delete a quiz"""
    try:
        # Get school_id and user_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        if not user_id:
            return jsonify({'error': 'User authentication required'}), 401
        
        db = current_app.db
        
        # Delete quiz only if it belongs to the teacher and school
        result = db.quizzes.delete_one({
            '_id': ObjectId(quiz_id),
            'teacher_id': user_id,
            'school_id': school_id
        })
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Quiz not found or unauthorized'}), 404
        
        return jsonify({'message': 'Quiz deleted successfully'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error deleting quiz: {str(e)}")
        return jsonify({'error': 'Failed to delete quiz'}), 500

@quiz_bp.route('/quiz/publish/<quiz_id>', methods=['PUT'])
def publish_quiz(quiz_id):
    """Publish a quiz to make it available to students"""
    try:
        # Get school_id and user_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        if not user_id:
            return jsonify({'error': 'User authentication required'}), 401
        
        db = current_app.db
        result = db.quizzes.update_one(
            {
                '_id': ObjectId(quiz_id),
                'teacher_id': user_id,
                'school_id': school_id
            },
            {
                '$set': {
                    'status': 'published',
                    'published_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Quiz not found or unauthorized'}), 404
        
        return jsonify({'message': 'Quiz published successfully'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error publishing quiz: {str(e)}")
        return jsonify({'error': 'Failed to publish quiz'}), 500

@quiz_bp.route('/quiz/unpublish/<quiz_id>', methods=['PUT'])
def unpublish_quiz(quiz_id):
    """Unpublish a quiz to make it unavailable to students"""
    try:
        # Get school_id and user_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        if not user_id:
            return jsonify({'error': 'User authentication required'}), 401
        
        db = current_app.db
        result = db.quizzes.update_one(
            {
                '_id': ObjectId(quiz_id),
                'teacher_id': user_id,
                'school_id': school_id
            },
            {
                '$set': {
                    'status': 'draft',
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Quiz not found or unauthorized'}), 404
        
        return jsonify({'message': 'Quiz unpublished successfully'}), 200
        
    except Exception as e:
        current_app.logger.error(f"Error unpublishing quiz: {str(e)}")
        return jsonify({'error': 'Failed to unpublish quiz'}), 500



# ==================== TEACHER RESULTS ROUTES ====================

@quiz_bp.route('/teacher/results', methods=['GET'])
def get_teacher_results():
    """Get all quiz results for teacher view (for all students in their school)"""
    try:
        # Get school_id
        school_id = get_school_id_from_request()
        user_id = get_current_user_id()
        
        if not school_id:
            return jsonify({'error': 'School ID is required'}), 400
        
        # Get query parameters for filtering
        student_email = request.args.get('student_email', '')
        subject = request.args.get('subject', '')
        quiz_id = request.args.get('quiz_id', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # Build query
        query = {'school_id': school_id}
        
        if student_email:
            query['student_email'] = student_email
        
        if subject:
            query['quiz_subject'] = subject
        
        if quiz_id:
            query['quiz_id'] = quiz_id
        
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query['submitted_at'] = query.get('submitted_at', {})
                query['submitted_at']['$gte'] = start
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                end = end.replace(hour=23, minute=59, second=59)
                query['submitted_at'] = query.get('submitted_at', {})
                query['submitted_at']['$lte'] = end
            except ValueError:
                pass
        
        print(f"📋 Teacher results query: {query}")
        
        # Get results from MongoDB
        db = current_app.db
        total = db.quiz_results.count_documents(query)
        skip = (page - 1) * limit
        
        results_cursor = db.quiz_results.find(query)\
            .sort('submitted_at', -1)\
            .skip(skip)\
            .limit(limit)
        
        results = list(results_cursor)
        
        # Convert ObjectId to string
        result_list = []
        for result in results:
            result['id'] = str(result['_id'])
            result['_id'] = str(result['_id'])
            
            # Add student details if not present
            if 'student_name' not in result and 'student_email' in result:
                # Try to get student name from students collection
                student = db.students.find_one({
                    'email': result['student_email'],
                    'school_id': school_id
                })
                if student:
                    result['student_name'] = student.get('name', 'Unknown')
            
            result_list.append(result)
        
        # Get aggregation data for analytics
        aggregation = [
            {'$match': {'school_id': school_id}},
            {
                '$group': {
                    '_id': '$quiz_subject',
                    'average_score': {'$avg': '$percentage'},
                    'total_attempts': {'$sum': 1},
                    'total_students': {'$addToSet': '$student_email'},
                    'high_score': {'$max': '$percentage'},
                    'low_score': {'$min': '$percentage'}
                }
            }
        ]
        
        if subject:
            aggregation.insert(0, {'$match': {'quiz_subject': subject}})
        
        analytics = list(db.quiz_results.aggregate(aggregation))
        
        # Process analytics
        for analytic in analytics:
            analytic['subject'] = analytic.pop('_id')
            analytic['total_students'] = len(analytic['total_students'])
        
        return jsonify({
            'results': result_list,
            'analytics': analytics,
            'total': total,
            'page': page,
            'limit': limit,
            'pages': math.ceil(total / limit) if limit > 0 else 1
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching teacher results: {str(e)}")
        return jsonify({'error': f'Failed to fetch teacher results: {str(e)}'}), 500

# ==================== TEST ROUTE ====================
@quiz_bp.route('/test', methods=['GET'])
def test_route():
    """Test route to verify the API is working"""
    return jsonify({
        'message': 'Quiz API is working!',
        'status': 'success',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

# ==================== HEALTH CHECK ====================
@quiz_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        db = current_app.db
        # Try to ping the database
        db.command('ping')
        
        # Check if collections exist
        collections = db.list_collection_names()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'collections': [col for col in ['question_bank', 'quizzes', 'quiz_results'] if col in collections],
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# app/routes/studentquiz.py
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from datetime import datetime, timedelta
from bson import ObjectId
import jwt as pyjwt

# Create blueprint
studentquiz_bp = Blueprint('studentquiz', __name__)

def serialize_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if not doc:
        return None
    
    if '_id' in doc:
        doc['id'] = str(doc['_id'])
        del doc['_id']
    
    # Convert other ObjectIds
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, dict):
            doc[key] = serialize_doc(value)
        elif isinstance(value, list):
            doc[key] = [serialize_doc(item) if isinstance(item, dict) else item for item in value]
    
    return doc

# Debug middleware
@studentquiz_bp.before_request
def log_request_info():
    if request.endpoint and 'health' not in request.endpoint:
        print(f"\n📥 Request: {request.method} {request.path}")
        print(f"   Args: {dict(request.args)}")
        
        auth_header = request.headers.get('Authorization')
        if auth_header:
            print(f"   Auth Header: {auth_header[:50]}...")

# ==================== DEBUG ENDPOINTS ====================

@studentquiz_bp.route('/student/debug/token-check', methods=['GET'])
def debug_token_check():
    """Debug endpoint to check token"""
    auth_header = request.headers.get('Authorization')
    
    response = {
        'success': True,
        'debug': True,
        'auth_header_present': bool(auth_header),
        'config': {
            'jwt_secret_set': bool(current_app.config.get('JWT_SECRET_KEY')),
            'jwt_secret_length': len(current_app.config.get('JWT_SECRET_KEY', '')),
            'secret_key_set': bool(current_app.config.get('SECRET_KEY')),
            'secret_key_length': len(current_app.config.get('SECRET_KEY', ''))
        }
    }
    
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        response['token_info'] = {
            'length': len(token),
            'first_50_chars': token[:50] + '...' if len(token) > 50 else token
        }
        
        try:
            # Try to decode without verification first
            decoded = pyjwt.decode(token, options={"verify_signature": False})
            response['token_info']['decoded'] = decoded
            response['token_info']['keys'] = list(decoded.keys())
        except Exception as e:
            response['token_info']['decode_error'] = str(e)
    
    return jsonify(response)

# ==================== MAIN QUIZ ENDPOINTS ====================
@studentquiz_bp.route('/student/quizzes', methods=['GET'])
def get_student_quizzes():
    """Get all quizzes available for student"""
    try:
        print(f"📊 Getting quizzes...")
        
        # Get query parameters
        school_id = request.args.get('school_id', '')
        student_class = request.args.get('class', '')
        filter_by_class = request.args.get('filter_by_class', 'true').lower() == 'true'
        debug_mode = request.args.get('debug', 'false').lower() == 'true'
        
        print(f"🔍 Query params - School: {school_id}, Class: {student_class}, Filter by class: {filter_by_class}")
        
        # Check database connection properly
        if not hasattr(current_app, 'db') or current_app.db is None:
            print("❌ Database connection not available")
            return jsonify({
                'success': False,
                'error': 'Database connection not available',
                'debug': 'current_app.db is None or not set'
            }), 500
        
        db = current_app.db
        print(f"✅ Database connection: {db is not None}")
        
        # If school_id not provided in query, try to get from token
        if not school_id:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]
                try:
                    decoded = pyjwt.decode(token, options={"verify_signature": False})
                    school_id = decoded.get('school_id', '')
                    if not student_class:
                        student_class = decoded.get('class', '')
                    print(f"🔍 Extracted from token - School: {school_id}, Class: {student_class}")
                except:
                    pass
        
        # If still no school_id, use default
        if not school_id:
            school_id = 'Nar1234'
            print(f"⚠️ Using default school_id: {school_id}")
        
        # Build query
        query = {
            'status': 'published',
            'school_id': school_id
        }
        
        # Add class filter if requested
        if filter_by_class and student_class:
            query['$or'] = [
                {'class': student_class},
                {'class': {'$exists': False}},
                {'class': ''},
                {'class': None}
            ]
        
        if debug_mode:
            print(f"🔍 MongoDB query: {query}")
        
        # Fetch quizzes
        try:
            quizzes_cursor = db.quizzes.find(query).sort('created_at', -1)
            quizzes = list(quizzes_cursor)
            print(f"✅ Found {len(quizzes)} quizzes in database")
        except Exception as db_error:
            print(f"❌ Database query error: {str(db_error)}")
            return jsonify({
                'success': False,
                'error': 'Database query failed',
                'debug_error': str(db_error)
            }), 500
        
        processed_quizzes = []
        
        for quiz in quizzes:
            quiz_data = {
                'id': str(quiz['_id']),
                'title': quiz.get('title', 'Untitled Quiz'),
                'subject': quiz.get('subject', 'General'),
                'description': quiz.get('description', ''),
                'teacher_id': quiz.get('teacher_id', ''),
                'teacher_name': quiz.get('teacher_name', ''),
                'time_limit': quiz.get('time_limit', 60),
                'status': quiz.get('status', 'draft'),
                'total_points': quiz.get('total_points', 0),
                'question_count': len(quiz.get('questions', [])),
                'created_at': quiz.get('created_at', datetime.utcnow()).isoformat() if isinstance(quiz.get('created_at'), datetime) else str(quiz.get('created_at', '')),
                'updated_at': quiz.get('updated_at', datetime.utcnow()).isoformat() if isinstance(quiz.get('updated_at'), datetime) else str(quiz.get('updated_at', '')),
                'class': quiz.get('class', ''),
                'school_id': quiz.get('school_id', ''),
                'questions': []
            }
            
            if quiz.get('published_at'):
                if isinstance(quiz['published_at'], datetime):
                    quiz_data['published_at'] = quiz['published_at'].isoformat()
                else:
                    quiz_data['published_at'] = str(quiz['published_at'])
            
            # Add questions without correct answers - USE ACTUAL IDs
            for q in quiz.get('questions', []):
                # Use the actual _id from the database, don't generate new ones
                question_id = str(q.get('_id', ObjectId()))
                
                question = {
                    'id': question_id,  # Use the actual ID from database
                    'question_text': q.get('question_text', ''),
                    'question_type': q.get('question_type', 'multiple_choice'),
                    'points': q.get('points', 1),
                    'difficulty': q.get('difficulty', 'medium'),
                    'time_estimate': q.get('time_estimate', 1),
                    'order_index': q.get('order_index', 0)
                }
                
                if q.get('question_type') in ['multiple_choice', 'true_false']:
                    question['options'] = q.get('options', [])
                
                quiz_data['questions'].append(question)
            
            # Sort questions by order_index
            quiz_data['questions'].sort(key=lambda x: x.get('order_index', 0))
            processed_quizzes.append(quiz_data)
        
        # Get unique subjects
        try:
            subjects = list(db.quizzes.distinct('subject', query))
        except:
            subjects = list(set([q.get('subject', 'General') for q in quizzes]))
        
        response_data = {
            'success': True,
            'quizzes': processed_quizzes,
            'subjects': subjects,
            'count': len(processed_quizzes),
            'query_info': {
                'school_id': school_id,
                'class': student_class,
                'filter_by_class': filter_by_class,
                'total_found': len(processed_quizzes)
            }
        }
        
        if debug_mode:
            response_data['debug'] = {
                'query_used': query,
                'total_quizzes_in_db': len(quizzes),
                'subjects_found': subjects,
                'database_name': db.name if hasattr(db, 'name') else 'unknown'
            }
        
        print(f"✅ Successfully returned {len(processed_quizzes)} quizzes for school {school_id}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in get_student_quizzes: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': 'Failed to load quizzes',
            'debug_error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# ==================== SIMPLIFIED QUIZ ATTEMPT ENDPOINT ====================

# Add this endpoint to studentquiz.py (around line 300)
@studentquiz_bp.route('/student/quiz/attempt/<quiz_id>', methods=['GET'])
def get_quiz_for_attempt(quiz_id):
    """Get quiz details for student attempt"""
    try:
        print(f"🎯 Getting quiz for attempt: {quiz_id}")
        
        # Check database connection
        if not hasattr(current_app, 'db') or current_app.db is None:
            return jsonify({'error': 'Database connection failed'}), 500
        
        db = current_app.db
        
        # Find quiz
        try:
            quiz = db.quizzes.find_one({'_id': ObjectId(quiz_id)})
        except:
            return jsonify({'error': 'Invalid quiz ID format'}), 400
        
        if not quiz:
            return jsonify({'error': 'Quiz not found'}), 404
        
        # Check if quiz is published
        if quiz.get('status') != 'published':
            return jsonify({'error': 'Quiz is not available'}), 403
        
        # Prepare quiz data for attempt
        quiz_data = {
            'id': str(quiz['_id']),
            'title': quiz.get('title', 'Untitled Quiz'),
            'subject': quiz.get('subject', 'General'),
            'description': quiz.get('description', ''),
            'time_limit': quiz.get('time_limit', 60),
            'total_points': quiz.get('total_points', 0),
            'questions': []
        }
        
        # Add questions (without correct answers)
        for i, q in enumerate(quiz.get('questions', [])):
    # Generate the same question ID as in get_quiz_for_attempt
            question_id = str(q.get('_id', ''))
    
    # If no _id exists, generate a stable ID
            if not question_id or question_id == '' or question_id == 'None':
                import hashlib
                question_text = q.get('question_text', '')
                question_hash = hashlib.md5(f"{question_text}_{i}_{str(quiz['_id'])}".encode()).hexdigest()[:12]
                question_id = f"q_{question_hash}"
    
            question = {
                'id': question_id,
                'question_text': q.get('question_text', ''),
                'question_type': q.get('question_type', 'multiple_choice'),
                'points': q.get('points', 1),
                'difficulty': q.get('difficulty', 'medium'),
                'time_estimate': q.get('time_estimate', 1),
                'order_index': q.get('order_index', i)
            }
            
            if q.get('question_type') in ['multiple_choice', 'true_false']:
                question['options'] = q.get('options', [])
            
            quiz_data['questions'].append(question)
        
        # Sort questions by order_index
        quiz_data['questions'].sort(key=lambda x: x.get('order_index', 0))
        
        # Debug: Print question IDs
        print(f"📋 Quiz '{quiz_data['title']}' has {len(quiz_data['questions'])} questions")
        for i, q in enumerate(quiz_data['questions']):
            print(f"   Q{i+1}: ID={q['id']}, Text='{q['question_text'][:50]}...'")
        
        return jsonify({
            'success': True,
            'quiz': quiz_data,
            'quiz_info': {
                'class': quiz.get('class', ''),
                'total_questions': len(quiz_data['questions']),
                'title': quiz.get('title', '')
            }
        })
        
    except Exception as e:
        print(f"❌ Error getting quiz for attempt: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Failed to load quiz',
            'debug': str(e)
        }), 500
# Add this to studentquiz.py, replace the existing submit_quiz_attempt function
@studentquiz_bp.route('/student/quiz/submit', methods=['POST'])
def submit_quiz_attempt():
    """Submit quiz attempt for grading"""
    try:
        print(f"📥 Received quiz submission request")
        data = request.get_json()
        
        if not data:
            print("❌ No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
        
        print(f"📊 Submission data keys: {list(data.keys())}")
        print(f"📊 Answers received:")
        for i, answer in enumerate(data.get('answers', [])):
            print(f"  Answer {i+1}: question_id={answer.get('question_id')}, answer={answer.get('answer')}")
        
        # Validate required fields
        required_fields = ['quiz_id', 'student_email', 'answers']
        for field in required_fields:
            if field not in data:
                print(f"❌ Missing required field: {field}")
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Get database
        if not hasattr(current_app, 'db') or current_app.db is None:
            print("❌ Database connection failed")
            return jsonify({'error': 'Database connection failed'}), 500
        
        db = current_app.db
        
        # Get quiz
        try:
            print(f"🔍 Looking for quiz: {data['quiz_id']}")
            quiz = db.quizzes.find_one({'_id': ObjectId(data['quiz_id'])})
        except Exception as e:
            print(f"❌ Error converting quiz ID: {str(e)}")
            return jsonify({'error': 'Invalid quiz ID'}), 400
        
        if not quiz:
            print("❌ Quiz not found")
            return jsonify({'error': 'Quiz not found'}), 404
        
        print(f"✅ Found quiz: {quiz.get('title')} with {len(quiz.get('questions', []))} questions")
        
        # Calculate score
        total_score = 0
        max_score = quiz.get('total_points', 0)
        correct_answers = 0
        question_results = []
        
        # Create a dictionary of student answers for easier lookup
        student_answers_dict = {}
        print("📝 Processing student answers:")
        for answer in data['answers']:
            q_id = answer.get('question_id', '')
            ans = answer.get('answer', '')
            student_answers_dict[q_id] = ans
            print(f"  Question ID: '{q_id}', Answer: '{ans}'")
        
        for i, q in enumerate(quiz.get('questions', [])):
            # Generate the same question ID that was used in get_quiz_for_attempt
            question_id = str(q.get('_id', ''))
            
            # If no _id exists, generate the same ID that was sent to the frontend
            if not question_id or question_id == '' or question_id == 'None':
                import hashlib
                question_text = q.get('question_text', '')
                question_hash = hashlib.md5(f"{question_text}_{i}_{data['quiz_id']}".encode()).hexdigest()[:12]
                question_id = f"q_{question_hash}"
            
            # Find student's answer for this question
            student_answer = student_answers_dict.get(question_id, '')
            
            # Debug logging
            print(f"\n🔍 Checking question {i+1}: '{q.get('question_text', '')[:50]}...'")
            print(f"   Generated Question ID: {question_id}")
            print(f"   Student answer: '{student_answer}'")
            
            correct_answer = q.get('correct_answer', '')
            print(f"   Correct answer: '{correct_answer}'")
            
            # For multiple choice, compare strings directly
            is_correct = str(student_answer).strip() == str(correct_answer).strip()
            
            points = q.get('points', 1)
            score = points if is_correct else 0
            
            if is_correct:
                correct_answers += 1
                total_score += score
                print(f"   ✅ Correct! Score: {score}/{points}")
            else:
                print(f"   ❌ Incorrect. Expected: '{correct_answer}', Got: '{student_answer}'")
            
            question_results.append({
                'question_id': question_id,  # Use the generated ID
                'question_text': q.get('question_text', ''),
                'question_type': q.get('question_type', ''),
                'student_answer': student_answer,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'points': points,
                'score': score,
                'explanation': q.get('explanation', '')
            })
        
        print(f"\n📊 Final score: {correct_answers}/{len(quiz.get('questions', []))} correct, {total_score}/{max_score} points")
        
        # Calculate percentage
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        
        # Determine grade
        if percentage >= 90:
            grade = 'A'
        elif percentage >= 80:
            grade = 'B'
        elif percentage >= 70:
            grade = 'C'
        elif percentage >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        # Create result document
        result_data = {
            'quiz_id': data['quiz_id'],
            'quiz_title': quiz.get('title', 'Untitled Quiz'),
            'quiz_subject': quiz.get('subject', 'General'),
            'student_id': data.get('student_id', ''),
            'student_email': data['student_email'],
            'student_name': data.get('student_name', ''),
            'total_questions': len(quiz.get('questions', [])),
            'correct_answers': correct_answers,
            'total_score': total_score,
            'max_score': max_score,
            'percentage': round(percentage, 2),
            'grade': grade,
            'question_results': question_results,
            'answers': data['answers'],
            'submitted_at': datetime.utcnow(),
            'time_taken': data.get('time_taken', 0),
            'school_id': data.get('school_id', ''),
            'student_class': data.get('student_class', '')
        }
        
        print(f"📝 Inserting result into database...")
        
        # Insert result
        result = db.quiz_results.insert_one(result_data)
        result_id = str(result.inserted_id)
        
        print(f"✅ Result inserted with ID: {result_id}")
        
        # Prepare response data - make sure it's JSON serializable
        response_data = {
            'id': result_id,
            'quiz_id': data['quiz_id'],
            'quiz_title': result_data['quiz_title'],
            'quiz_subject': result_data['quiz_subject'],
            'student_id': result_data['student_id'],
            'student_email': result_data['student_email'],
            'student_name': result_data['student_name'],
            'total_questions': result_data['total_questions'],
            'correct_answers': result_data['correct_answers'],
            'total_score': result_data['total_score'],
            'max_score': result_data['max_score'],
            'percentage': result_data['percentage'],
            'grade': result_data['grade'],
            'submitted_at': result_data['submitted_at'].isoformat(),  # Convert datetime to string
            'time_taken': result_data['time_taken'],
            'school_id': result_data['school_id'],
            'student_class': result_data.get('student_class', '')
        }
        
        # Add question results (already serializable)
        response_data['question_results'] = question_results
        
        return jsonify({
            'success': True,
            'message': 'Quiz submitted successfully',
            'result': response_data
        })
        
    except Exception as e:
        print(f"❌ Error submitting quiz: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': 'Failed to submit quiz',
            'debug': str(e)
        }), 500
# ==================== TEST ENDPOINTS ====================

@studentquiz_bp.route('/student/test/database', methods=['GET'])
def test_database():
    """Test database connection"""
    try:
        if not hasattr(current_app, 'db') or current_app.db is None:
            return jsonify({
                'success': False,
                'error': 'Database not connected',
                'db_attribute_exists': hasattr(current_app, 'db'),
                'db_is_none': current_app.db is None if hasattr(current_app, 'db') else 'no db attribute'
            }), 500
        
        db = current_app.db
        
        # Test connection by listing collections
        collections = db.list_collection_names()
        
        # Count quizzes
        quiz_count = db.quizzes.count_documents({})
        
        # Get sample quiz
        sample_quiz = db.quizzes.find_one({})
        
        return jsonify({
            'success': True,
            'database': db.name if hasattr(db, 'name') else 'unknown',
            'collections': collections,
            'quiz_count': quiz_count,
            'sample_quiz_id': str(sample_quiz['_id']) if sample_quiz else None,
            'sample_quiz_title': sample_quiz.get('title') if sample_quiz else None,
            'sample_quiz_class': sample_quiz.get('class') if sample_quiz else None,
            'sample_quiz_school_id': sample_quiz.get('school_id') if sample_quiz else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': str(e.__traceback__)
        }), 500

@studentquiz_bp.route('/student/test/quizzes-by-class', methods=['GET'])
def test_quizzes_by_class():
    """Test getting quizzes by class directly"""
    try:
        school_id = request.args.get('school_id', 'Nar1234')
        student_class = request.args.get('class', '')
        
        if not hasattr(current_app, 'db') or current_app.db is None:
            return jsonify({'error': 'Database not connected'}), 500
        
        db = current_app.db
        
        # Build query
        query = {
            'status': 'published',
            'school_id': school_id
        }
        
        if student_class:
            query['$or'] = [
                {'class': student_class},
                {'class': {'$exists': False}},
                {'class': ''},
                {'class': None}
            ]
        
        quizzes = list(db.quizzes.find(query).limit(5))
        
        result = []
        for quiz in quizzes:
            result.append({
                'id': str(quiz['_id']),
                'title': quiz.get('title', 'Untitled'),
                'subject': quiz.get('subject', 'General'),
                'class': quiz.get('class', 'Not specified'),
                'school_id': quiz.get('school_id', ''),
                'question_count': len(quiz.get('questions', [])),
                'status': quiz.get('status', 'unknown')
            })
        
        return jsonify({
            'success': True,
            'query': query,
            'quizzes': result,
            'count': len(result)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ==================== HEALTH CHECK ====================

@studentquiz_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'student-quiz-api',
        'timestamp': datetime.utcnow().isoformat(),
        'endpoints': {
            'debug': '/student/debug/*',
            'quizzes': '/student/quizzes',
            'attempt': '/student/quiz/attempt',
            'test': '/student/test/*'
        }
    })

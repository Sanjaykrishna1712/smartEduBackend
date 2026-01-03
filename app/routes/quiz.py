from flask import Blueprint, request, jsonify, current_app
import json
from datetime import datetime,timedelta 
from bson import ObjectId
import uuid

quiz_bp = Blueprint('quiz', __name__)

# Helper function to validate JSON fields
def validate_required_fields(data, required_fields):
    missing_fields = []
    for field in required_fields:
        if field not in data or (isinstance(data[field], str) and not data[field].strip()):
            missing_fields.append(field)
    return missing_fields

# REMOVED: get_current_user_id function since we're not using JWT
# For now, we'll use a dummy user ID or get it from request
def get_current_user_id():
    # For development/testing, use a dummy user ID
    # In production, you should implement proper authentication
    return "dummy_user_id"  # TODO: Replace with actual user ID from session or auth

# Question Bank Routes - REMOVED @jwt_required()
@quiz_bp.route('/question-bank', methods=['GET'])
def get_question_bank():  # REMOVED: @jwt_required()
    """Get all questions from question bank with filters"""
    try:
        # Get query parameters
        subject = request.args.get('subject', '')
        topic = request.args.get('topic', '')
        difficulty = request.args.get('difficulty', '')
        search = request.args.get('search', '')
        
        # Build query - using dummy user for now
        query = {'created_by': get_current_user_id(), 'is_reusable': True}
        
        if subject:
            query['subject'] = subject
        
        if topic:
            query['topic'] = topic
        
        if difficulty:
            query['difficulty'] = difficulty
        
        # Get questions from MongoDB
        db = current_app.db
        questions_cursor = db.question_bank.find(query).sort('updated_at', -1)
        questions = list(questions_cursor)
        
        # Convert ObjectId to string
        question_list = []
        for q in questions:
            q['id'] = str(q['_id'])
            del q['_id']
            question_list.append(q)
        
        # Get unique subjects, topics and difficulties for filtering
        subjects = db.question_bank.distinct('subject', {'created_by': get_current_user_id()})
        topics = db.question_bank.distinct('topic', {'created_by': get_current_user_id()})
        difficulties = db.question_bank.distinct('difficulty', {'created_by': get_current_user_id()})
        
        # Get all tags
        all_tags = set()
        for q in questions:
            if 'tags' in q and q['tags']:
                all_tags.update(q['tags'])
        
        return jsonify({
            'questions': question_list,
            'subjects': subjects,
            'topics': topics,
            'difficulties': list(difficulties),
            'tags': list(all_tags),
            'total': len(question_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching question bank: {str(e)}")
        return jsonify({'error': 'Failed to fetch question bank'}), 500

@quiz_bp.route('/question-bank/filters', methods=['GET'])
def get_question_bank_filters():  # REMOVED: @jwt_required()
    """Get available filters for question bank"""
    try:
        db = current_app.db
        user_id = get_current_user_id()
        
        # Get unique values from MongoDB
        subjects = db.question_bank.distinct('subject', {'created_by': user_id})
        topics = db.question_bank.distinct('topic', {'created_by': user_id})
        
        # Get all tags
        questions = list(db.question_bank.find({'created_by': user_id}))
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
            'tags': list(all_tags)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching question bank filters: {str(e)}")
        return jsonify({'error': 'Failed to fetch filters'}), 500

@quiz_bp.route('/question-bank', methods=['POST'])
def add_to_question_bank():  # REMOVED: @jwt_required()
    """Add a new question to the question bank"""
    try:
        # Check if request has JSON
        if not request.is_json:
            return jsonify({'error': 'Missing JSON in request'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['question_text', 'question_type', 'subject', 'topic', 'correct_answer', 'points']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        user_id = get_current_user_id()
        
        # Check for duplicate question
        db = current_app.db
        existing_question = db.question_bank.find_one({
            'question_text': data['question_text'].strip(),
            'subject': data['subject'],
            'created_by': user_id
        })
        
        if existing_question:
            return jsonify({'error': 'This question already exists in your question bank'}), 409
        
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
            'created_by': user_id,
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

# Quiz Routes - REMOVED @jwt_required()
@quiz_bp.route('/quizzes', methods=['GET'])
def get_quizzes():  # REMOVED: @jwt_required()
    """Get all quizzes for the current teacher with search and filter"""
    try:
        # Get query parameters
        search = request.args.get('search', '')
        status = request.args.get('status', '')
        subject = request.args.get('subject', '')
        
        # Build query
        query = {'teacher_id': get_current_user_id()}
        
        if status:
            query['status'] = status
        
        if subject:
            query['subject'] = subject
        
        # Get quizzes from MongoDB
        db = current_app.db
        quizzes_cursor = db.quizzes.find(query).sort('updated_at', -1)
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
        
        # Get unique subjects for filter
        subjects = db.quizzes.distinct('subject', {'teacher_id': get_current_user_id()})
        
        return jsonify({
            'quizzes': quiz_list,
            'subjects': subjects,
            'total': len(quiz_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching quizzes: {str(e)}")
        return jsonify({'error': 'Failed to fetch quizzes'}), 500

@quiz_bp.route('/quizzes', methods=['POST'])
def create_quiz():  # REMOVED: @jwt_required()
    """Create a new quiz from selected questions"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Missing JSON in request'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['title', 'subject', 'questions']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        user_id = get_current_user_id()
        
        # Check for duplicate quiz title
        db = current_app.db
        existing_quiz = db.quizzes.find_one({
            'title': data['title'].strip(),
            'teacher_id': user_id
        })
        
        if existing_quiz:
            return jsonify({'error': 'A quiz with this title already exists'}), 409
        
        # Verify all questions exist and belong to teacher
        question_bank_ids = [ObjectId(q['question_bank_id']) for q in data['questions'] if 'question_bank_id' in q]
        if question_bank_ids:
            question_count = db.question_bank.count_documents({
                '_id': {'$in': question_bank_ids},
                'created_by': user_id
            })
            
            if question_count != len(question_bank_ids):
                return jsonify({'error': 'One or more questions not found or unauthorized'}), 400
        
        # Create quiz questions from question bank
        questions = []
        total_points = 0
        
        for index, question_data in enumerate(data['questions'], 1):
            if 'question_bank_id' in question_data:
                # Get question from question bank
                question_bank = db.question_bank.find_one({
                    '_id': ObjectId(question_data['question_bank_id']),
                    'created_by': user_id
                })
                
                if not question_bank:
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
                    'time_estimate': question_bank.get('time_estimate', 2),
                    'tags': question_bank.get('tags', []),
                    'order_index': index
                }
            else:
                # Add new question directly
                question = {
                    'question_text': question_data['question_text'].strip(),
                    'question_type': question_data['question_type'],
                    'correct_answer': question_data['correct_answer'],
                    'explanation': question_data.get('explanation', '').strip(),
                    'points': int(question_data['points']),
                    'difficulty': question_data.get('difficulty', 'medium'),
                    'subject': data['subject'],
                    'topic': question_data.get('topic', 'General').strip(),
                    'time_estimate': question_data.get('time_estimate', 2),
                    'tags': question_data.get('tags', []),
                    'order_index': index
                }
                
                if question_data['question_type'] == 'multiple_choice':
                    if 'options' in question_data and isinstance(question_data['options'], list):
                        question['options'] = question_data['options']
            
            total_points += question['points']
            questions.append(question)
        
        # Create quiz document
        quiz_doc = {
            'title': data['title'].strip(),
            'subject': data['subject'],
            'description': data.get('description', '').strip(),
            'teacher_id': user_id,
            'time_limit': int(data.get('time_limit', 60)),
            'status': data.get('status', 'draft'),
            'total_points': total_points,
            'questions': questions,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert into MongoDB
        result = db.quizzes.insert_one(quiz_doc)
        quiz_doc['id'] = str(result.inserted_id)
        del quiz_doc['_id']
        
        return jsonify({
            'message': 'Quiz created successfully',
            'quiz': quiz_doc
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error creating quiz: {str(e)}")
        return jsonify({'error': f'Failed to create quiz: {str(e)}'}), 500

# Add more routes as needed...

@quiz_bp.route('/test', methods=['GET', 'POST'])
def test_route():
    """Test route to verify the API is working"""
    if request.method == 'POST':
        data = request.get_json() or {}
        return jsonify({
            'message': 'POST test successful',
            'received_data': data,
            'status': 'success',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    
    return jsonify({
        'message': 'Quiz API is working!',
        'status': 'success',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

#quiz
# Add these routes to your existing quiz_bp

@quiz_bp.route('/student/quizzes', methods=['GET'])
def get_student_quizzes():
    """Get all quizzes available for students"""
    try:
        # Get query parameters
        search = request.args.get('search', '')
        subject = request.args.get('subject', '')
        status = request.args.get('status', 'active')  # Default to active quizzes
        
        # Build query - only get published quizzes
        query = {'status': 'published'}
        
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}},
                {'subject': {'$regex': search, '$options': 'i'}}
            ]
        
        if subject:
            query['subject'] = subject
        
        # Get quizzes from MongoDB
        db = current_app.db
        quizzes_cursor = db.quizzes.find(query).sort('created_at', -1)
        quizzes = list(quizzes_cursor)
        
        # Convert ObjectId to string and remove correct answers
        quiz_list = []
        for quiz in quizzes:
            quiz['id'] = str(quiz['_id'])
            del quiz['_id']
            
            # Remove correct answers from questions for student view
            if 'questions' in quiz:
                for q in quiz['questions']:
                    if '_id' in q:
                        q['id'] = str(q['_id'])
                        del q['_id']
                    # Remove correct_answer for student view
                    q.pop('correct_answer', None)
                    q.pop('explanation', None)
            
            quiz_list.append(quiz)
        
        # Get unique subjects for filter
        subjects = db.quizzes.distinct('subject', {'status': 'published'})
        
        return jsonify({
            'quizzes': quiz_list,
            'subjects': subjects,
            'total': len(quiz_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching student quizzes: {str(e)}")
        return jsonify({'error': 'Failed to fetch quizzes'}), 500

@quiz_bp.route('/student/quiz/<quiz_id>', methods=['GET'])
def get_student_quiz(quiz_id):
    """Get a specific quiz for student attempt"""
    try:
        # Verify quiz exists and is published
        db = current_app.db
        quiz = db.quizzes.find_one({
            '_id': ObjectId(quiz_id),
            'status': 'published'
        })
        
        if not quiz:
            return jsonify({'error': 'Quiz not found or not available'}), 404
        
        # Convert ObjectId to string
        quiz['id'] = str(quiz['_id'])
        del quiz['_id']
        
        # Remove correct answers from questions
        if 'questions' in quiz:
            for q in quiz['questions']:
                if '_id' in q:
                    q['id'] = str(q['_id'])
                    del q['_id']
                # Remove correct_answer for student attempt
                q.pop('correct_answer', None)
                q.pop('explanation', None)
        
        return jsonify(quiz), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching student quiz: {str(e)}")
        return jsonify({'error': 'Failed to fetch quiz'}), 500

@quiz_bp.route('/student/quiz/submit', methods=['POST'])
def submit_quiz():
    """Submit a quiz attempt and calculate results"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Missing JSON in request'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['quiz_id', 'student_id', 'student_email', 'answers']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        # Get quiz with correct answers
        db = current_app.db
        quiz = db.quizzes.find_one({
            '_id': ObjectId(data['quiz_id']),
            'status': 'published'
        })
        
        if not quiz:
            return jsonify({'error': 'Quiz not found or not available'}), 404
        
        # Calculate results
        total_questions = len(quiz['questions'])
        correct_answers = 0
        total_score = 0
        max_score = quiz.get('total_points', 0)
        
        # Evaluate each answer
        question_results = []
        for i, question in enumerate(quiz['questions']):
            question_id = str(question.get('_id', '')) or str(i)
            student_answer = next((ans for ans in data['answers'] 
                                  if ans.get('question_id') == question_id), None)
            
            # Get correct answer
            correct_answer = question.get('correct_answer', '')
            points = question.get('points', 1)
            
            # Check if answer is correct
            is_correct = False
            if student_answer:
                student_response = student_answer.get('answer', '').strip()
                
                if question.get('question_type') == 'multiple_choice':
                    is_correct = student_response == correct_answer
                elif question.get('question_type') == 'true_false':
                    is_correct = str(student_response).lower() == str(correct_answer).lower()
                else:
                    # For short_answer and numerical
                    is_correct = str(student_response).strip().lower() == str(correct_answer).strip().lower()
            
            # Calculate score for this question
            question_score = points if is_correct else 0
            total_score += question_score
            
            if is_correct:
                correct_answers += 1
            
            # Store question result
            question_result = {
                'question_id': question_id,
                'question_text': question.get('question_text', ''),
                'question_type': question.get('question_type', ''),
                'student_answer': student_answer.get('answer', '') if student_answer else '',
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'points': points,
                'score': question_score,
                'explanation': question.get('explanation', '')
            }
            question_results.append(question_result)
        
        # Calculate percentage
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        
        # Determine grade based on percentage
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
        result_doc = {
            'quiz_id': data['quiz_id'],
            'quiz_title': quiz.get('title', ''),
            'quiz_subject': quiz.get('subject', ''),
            'student_id': data['student_id'],
            'student_email': data['student_email'],
            'student_name': data.get('student_name', ''),
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'total_score': total_score,
            'max_score': max_score,
            'percentage': round(percentage, 2),
            'grade': grade,
            'question_results': question_results,
            'submitted_at': datetime.utcnow(),
            'time_taken': data.get('time_taken', 0),  # in seconds
            'attempt_number': data.get('attempt_number', 1)
        }
        
        # Check if this is a retake
        if data.get('attempt_number', 1) > 1:
            # Keep previous attempts
            result_doc['is_retake'] = True
        
        # Insert result into MongoDB
        result = db.quiz_results.insert_one(result_doc)
        result_doc['id'] = str(result.inserted_id)
        del result_doc['_id']
        
        return jsonify({
            'message': 'Quiz submitted successfully',
            'result': result_doc
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error submitting quiz: {str(e)}")
        return jsonify({'error': f'Failed to submit quiz: {str(e)}'}), 500

@quiz_bp.route('/student/results', methods=['GET'])
def get_student_results():
    """Get quiz results for a specific student"""
    try:
        student_email = request.args.get('student_email', '')
        student_id = request.args.get('student_id', '')
        
        if not student_email and not student_id:
            return jsonify({'error': 'Student email or ID is required'}), 400
        
        # Build query - FIXED: Use OR logic to find by either email or ID
        query = {}
        if student_email:
            query['student_email'] = student_email
        if student_id:
            query['student_id'] = student_id
        
        print(f"Querying results with: {query}")  # Debug log
        
        # Get results from MongoDB
        db = current_app.db
        results_cursor = db.quiz_results.find(query).sort('submitted_at', -1)
        results = list(results_cursor)
        
        print(f"Found {len(results)} results")  # Debug log
        
        # Convert ObjectId to string
        result_list = []
        for result in results:
            result['id'] = str(result['_id'])
            result['_id'] = str(result['_id'])  # Keep _id for compatibility
            result_list.append(result)
        
        return jsonify({
            'results': result_list,
            'total': len(result_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching student results: {str(e)}")
        return jsonify({'error': f'Failed to fetch results: {str(e)}'}), 500

@quiz_bp.route('/quiz/publish/<quiz_id>', methods=['PUT'])
def publish_quiz(quiz_id):
    """Publish a quiz to make it available to students"""
    try:
        user_id = get_current_user_id()
        
        db = current_app.db
        result = db.quizzes.update_one(
            {
                '_id': ObjectId(quiz_id),
                'teacher_id': user_id
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
        user_id = get_current_user_id()
        
        db = current_app.db
        result = db.quizzes.update_one(
            {
                '_id': ObjectId(quiz_id),
                'teacher_id': user_id
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
@quiz_bp.route('/student/quiz/attempt/<quiz_id>', methods=['GET'])
def get_quiz_for_attempt(quiz_id):
    """Get quiz details for attempt (without answers)"""
    try:
        db = current_app.db
        quiz = db.quizzes.find_one({
            '_id': ObjectId(quiz_id),
            'status': 'published'
        })
        
        if not quiz:
            return jsonify({'error': 'Quiz not found or not available'}), 404
        
        # Convert ObjectId to string
        quiz['id'] = str(quiz['_id'])
        del quiz['_id']
        
        # Prepare quiz for attempt
        attempt_data = {
            'id': quiz['id'],
            'title': quiz.get('title', ''),
            'subject': quiz.get('subject', ''),
            'description': quiz.get('description', ''),
            'teacher_id': quiz.get('teacher_id', ''),
            'time_limit': quiz.get('time_limit', 60),
            'total_points': quiz.get('total_points', 0),
            'questions': []
        }
        
        # Process questions (remove correct answers)
        if 'questions' in quiz:
            for i, q in enumerate(quiz['questions']):
                question_data = {
                    'id': str(i) if '_id' not in q else str(q['_id']),
                    'question_text': q.get('question_text', ''),
                    'question_type': q.get('question_type', 'multiple_choice'),
                    'points': q.get('points', 1),
                    'difficulty': q.get('difficulty', 'medium'),
                    'time_estimate': q.get('time_estimate', 2),
                    'order_index': q.get('order_index', i + 1)
                }
                
                # Add options for multiple choice questions
                if q.get('question_type') == 'multiple_choice':
                    question_data['options'] = q.get('options', [])
                
                attempt_data['questions'].append(question_data)
        
        return jsonify(attempt_data), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching quiz for attempt: {str(e)}")
        return jsonify({'error': 'Failed to fetch quiz for attempt'}), 500

@quiz_bp.route('/student/quiz/attempt', methods=['POST'])
def save_quiz_attempt():
    """Save a quiz attempt (for auto-saving during quiz)"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Missing JSON in request'}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['quiz_id', 'student_id', 'student_email', 'answers']
        missing_fields = validate_required_fields(data, required_fields)
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        db = current_app.db
        
        # Create attempt document
        attempt_doc = {
            'quiz_id': data['quiz_id'],
            'student_id': data['student_id'],
            'student_email': data['student_email'],
            'student_name': data.get('student_name', ''),
            'answers': data['answers'],
            'current_question': data.get('current_question', 0),
            'time_spent': data.get('time_spent', 0),
            'is_submitted': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(hours=24)  # Attempt expires in 24 hours
        }
        
        # Check for existing unsubmitted attempt
        existing_attempt = db.quiz_attempts.find_one({
            'quiz_id': data['quiz_id'],
            'student_id': data['student_id'],
            'is_submitted': False,
            'expires_at': {'$gt': datetime.utcnow()}
        })
        
        if existing_attempt:
            # Update existing attempt
            result = db.quiz_attempts.update_one(
                {'_id': existing_attempt['_id']},
                {
                    '$set': {
                        'answers': data['answers'],
                        'current_question': data.get('current_question', 0),
                        'time_spent': data.get('time_spent', 0),
                        'updated_at': datetime.utcnow()
                    }
                }
            )
            return jsonify({
                'message': 'Quiz attempt updated successfully',
                'attempt_id': str(existing_attempt['_id'])
            }), 200
        else:
            # Insert new attempt
            result = db.quiz_attempts.insert_one(attempt_doc)
            return jsonify({
                'message': 'Quiz attempt saved successfully',
                'attempt_id': str(result.inserted_id)
            }), 201
            
    except Exception as e:
        current_app.logger.error(f"Error saving quiz attempt: {str(e)}")
        return jsonify({'error': f'Failed to save quiz attempt: {str(e)}'}), 500

@quiz_bp.route('/student/quiz/resume/<quiz_id>', methods=['GET'])
def get_quiz_attempt(quiz_id):
    """Get existing quiz attempt to resume"""
    try:
        student_email = request.args.get('student_email', '')
        student_id = request.args.get('student_id', '')
        
        if not student_email and not student_id:
            return jsonify({'error': 'Student email or ID is required'}), 400
        
        db = current_app.db
        
        # Find unsubmitted attempt
        query = {
            'quiz_id': quiz_id,
            'is_submitted': False,
            'expires_at': {'$gt': datetime.utcnow()}
        }
        
        if student_email:
            query['student_email'] = student_email
        if student_id:
            query['student_id'] = student_id
        
        attempt = db.quiz_attempts.find_one(query)
        
        if not attempt:
            return jsonify({'message': 'No active attempt found', 'attempt': None}), 200
        
        # Convert ObjectId to string
        attempt['id'] = str(attempt['_id'])
        del attempt['_id']
        
        return jsonify({
            'message': 'Active attempt found',
            'attempt': attempt
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching quiz attempt: {str(e)}")
        return jsonify({'error': 'Failed to fetch quiz attempt'}), 500

@quiz_bp.route('/student/quiz/result/<attempt_id>', methods=['GET'])
def get_quiz_result(attempt_id):
    """Get quiz result after submission"""
    try:
        db = current_app.db
        
        # Get the result
        result = db.quiz_results.find_one({'_id': ObjectId(attempt_id)})
        
        if not result:
            return jsonify({'error': 'Result not found'}), 404
        
        # Convert ObjectId to string
        result['id'] = str(result['_id'])
        del result['_id']
        
        return jsonify({
            'result': result
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching quiz result: {str(e)}")
        return jsonify({'error': 'Failed to fetch quiz result'}), 500
@quiz_bp.route('/teacher/results', methods=['GET'])
def get_teacher_results():
    """Get all quiz results for teacher view (for all students)"""
    try:
        # In a real implementation, you would verify teacher authentication here
        # For now, we'll just return all results
        
        # Get query parameters for filtering
        student_email = request.args.get('student_email', '')
        subject = request.args.get('subject', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # Build query
        query = {}
        
        if student_email:
            query['student_email'] = student_email
        
        if subject:
            query['quiz_subject'] = subject
        
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
        
        print(f"Teacher querying results with: {query}")  # Debug log
        
        # Get results from MongoDB
        db = current_app.db
        results_cursor = db.quiz_results.find(query).sort('submitted_at', -1)
        results = list(results_cursor)
        
        print(f"Found {len(results)} results for teacher")  # Debug log
        
        # Convert ObjectId to string
        result_list = []
        for result in results:
            result['id'] = str(result['_id'])
            result['_id'] = str(result['_id'])  # Keep _id for compatibility
            
            # Add student details if not present
            if 'student_name' not in result and 'student_email' in result:
                # Try to get student name from users collection
                student = db.users.find_one({'email': result['student_email']})
                if student:
                    result['student_name'] = student.get('name', 'Unknown')
            
            result_list.append(result)
        
        # Get aggregation data for analytics
        aggregation = [
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
            'total': len(result_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching teacher results: {str(e)}")
        return jsonify({'error': f'Failed to fetch teacher results: {str(e)}'}), 500
@quiz_bp.route('/teacher/student/results', methods=['GET'])
def get_student_results_for_teacher():
    """Get quiz results for a specific student (teacher view)"""
    try:
        student_email = request.args.get('student_email', '')
        student_id = request.args.get('student_id', '')
        
        if not student_email and not student_id:
            return jsonify({'error': 'Student email or ID is required'}), 400
        
        # Build query
        query = {}
        if student_email:
            query['student_email'] = student_email
        if student_id:
            query['student_id'] = student_id
        
        print(f"Teacher querying student results with: {query}")  # Debug log
        
        # Get results from MongoDB
        db = current_app.db
        results_cursor = db.quiz_results.find(query).sort('submitted_at', -1)
        results = list(results_cursor)
        
        print(f"Found {len(results)} results for student")  # Debug log
        
        # Convert ObjectId to string
        result_list = []
        for result in results:
            result['id'] = str(result['_id'])
            result['_id'] = str(result['_id'])  # Keep _id for compatibility
            result_list.append(result)
        
        # Calculate student statistics
        if results:
            percentages = [r['percentage'] for r in results]
            subjects = list(set([r.get('quiz_subject', 'Unknown') for r in results]))
            
            stats = {
                'average_score': sum(percentages) / len(percentages),
                'high_score': max(percentages),
                'low_score': min(percentages),
                'total_quizzes': len(results),
                'subjects_attempted': subjects,
                'improvement_trend': calculate_improvement_trend(results)
            }
        else:
            stats = {
                'average_score': 0,
                'high_score': 0,
                'low_score': 0,
                'total_quizzes': 0,
                'subjects_attempted': [],
                'improvement_trend': 0
            }
        
        return jsonify({
            'results': result_list,
            'stats': stats,
            'total': len(result_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Error fetching student results for teacher: {str(e)}")
        return jsonify({'error': f'Failed to fetch student results: {str(e)}'}), 500

def calculate_improvement_trend(results):
    """Calculate improvement trend based on recent performance"""
    if len(results) < 2:
        return 0
    
    # Sort by date
    sorted_results = sorted(results, key=lambda x: x['submitted_at'])
    
    # Split into halves
    mid_point = len(sorted_results) // 2
    first_half = sorted_results[:mid_point]
    second_half = sorted_results[mid_point:]
    
    if not first_half or not second_half:
        return 0
    
    avg_first = sum(r['percentage'] for r in first_half) / len(first_half)
    avg_second = sum(r['percentage'] for r in second_half) / len(second_half)
    
    return avg_second - avg_first

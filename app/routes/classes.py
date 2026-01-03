# app/routes/classes.py
from flask import Blueprint, request, jsonify, current_app
from bson import ObjectId
from datetime import datetime

classes_bp = Blueprint('classes', __name__, url_prefix='/api')

def validate_object_id(id_str):
    """Validate if string is a valid ObjectId"""
    try:
        return ObjectId(id_str)
    except:
        return None

def serialize_document(doc):
    """Convert MongoDB document to JSON serializable format"""
    if not doc:
        return None
    
    doc['id'] = str(doc['_id'])
    
    # Remove MongoDB _id field
    if '_id' in doc:
        del doc['_id']
    
    # Ensure arrays exist
    if 'courses' not in doc:
        doc['courses'] = []
    if 'subjects' not in doc:
        doc['subjects'] = []
    
    return doc

# Get all classes
@classes_bp.route('/classes', methods=['GET'])
def get_classes():
    try:
        db = current_app.db
        
        # Get filter parameters
        grade = request.args.get('grade', 'all')
        search = request.args.get('search', '')
        subject = request.args.get('subject', 'all')
        
        # Build query
        query = {}
        
        # Apply filters
        if grade != 'all':
            query['grade'] = grade
        
        # Apply search
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'grade': {'$regex': search, '$options': 'i'}},
                {'code': {'$regex': search, '$options': 'i'}}
            ]
        
        # Apply subject filter
        if subject != 'all':
            query['subjects.id'] = subject
        
        # Get classes
        classes = list(db.classes.find(query).sort('grade', 1))
        
        # Serialize documents
        serialized_classes = []
        for cls in classes:
            serialized_cls = serialize_document(cls)
            
            # Get student count
            try:
                student_count = db.students.count_documents({'class_id': serialized_cls['id']})
                serialized_cls['students'] = student_count
            except:
                serialized_cls['students'] = 0
            
            serialized_classes.append(serialized_cls)
        
        return jsonify({
            'success': True,
            'classes': serialized_classes,
            'total': len(serialized_classes)
        }), 200
        
    except Exception as e:
        print(f"Error in get_classes: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get single class
@classes_bp.route('/classes/<string:class_id>', methods=['GET'])
def get_class(class_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(class_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid class ID'}), 400
        
        class_obj = db.classes.find_one({'_id': obj_id})
        if not class_obj:
            return jsonify({'success': False, 'message': 'Class not found'}), 404
        
        # Serialize class
        serialized_class = serialize_document(class_obj)
        
        # Get students in this class
        try:
            students = list(db.students.find({'class_id': str(obj_id)}))
            student_count = len(students)
        except:
            student_count = 0
        
        # Get subjects with full details
        if 'subjects' in serialized_class:
            subjects_with_details = []
            for subject in serialized_class['subjects']:
                subject_id = subject.get('id')
                if subject_id:
                    subject_obj = db.subjects.find_one({'_id': ObjectId(subject_id)})
                    if subject_obj:
                        subjects_with_details.append(serialize_document(subject_obj))
            serialized_class['subjects'] = subjects_with_details
        
        return jsonify({
            'success': True,
            'class': serialized_class,
            'student_count': student_count
        }), 200
        
    except Exception as e:
        print(f"Error in get_class: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Create new class
@classes_bp.route('/classes', methods=['POST'])
def create_class():
    try:
        db = current_app.db
        data = request.get_json()
        
        # Validate required fields
        if 'grade' not in data or not data['grade']:
            return jsonify({'success': False, 'message': 'Grade is required'}), 400
        
        # Generate class name and code
        grade = data['grade']
        class_count = db.classes.count_documents({'grade': grade}) + 1
        class_name = f"Class {grade}"
        class_code = f'CL{grade.zfill(2)}{class_count:03d}'
        
        # Process subjects
        subjects = data.get('subjects', [])
        processed_subjects = []
        
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists
                subject_obj = db.subjects.find_one({'_id': ObjectId(subject_id)})
                if subject_obj:
                    processed_subjects.append({
                        'id': subject_id,
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', '')
                    })
        
        # Prepare class document
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
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert class
        result = db.classes.insert_one(class_doc)
        class_doc['_id'] = result.inserted_id
        
        # Get created class
        created_class = serialize_document(class_doc)
        
        return jsonify({
            'success': True,
            'message': 'Class created successfully',
            'class': created_class
        }), 201
        
    except Exception as e:
        print(f"Error in create_class: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Update class
@classes_bp.route('/classes/<string:class_id>', methods=['PUT'])
def update_class(class_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(class_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid class ID'}), 400
        
        class_obj = db.classes.find_one({'_id': obj_id})
        if not class_obj:
            return jsonify({'success': False, 'message': 'Class not found'}), 404
        
        data = request.get_json()
        update_data = {}
        
        # Update class fields
        if 'grade' in data:
            update_data['grade'] = data['grade']
            # Update name based on grade
            update_data['name'] = f"Class {data['grade']}"
        
        if 'capacity' in data:
            update_data['capacity'] = data['capacity']
        
        if 'academic_year' in data:
            update_data['academic_year'] = data['academic_year']
        
        if 'description' in data:
            update_data['description'] = data['description']
        
        if 'courses' in data:
            update_data['courses'] = data['courses']
        
        # Process subjects
        if 'subjects' in data:
            subjects = data['subjects']
            processed_subjects = []
            
            for subject in subjects:
                subject_id = subject.get('id')
                if subject_id and validate_object_id(subject_id):
                    # Verify subject exists
                    subject_obj = db.subjects.find_one({'_id': ObjectId(subject_id)})
                    if subject_obj:
                        processed_subjects.append({
                            'id': subject_id,
                            'name': subject_obj.get('name', ''),
                            'code': subject_obj.get('code', '')
                        })
            
            update_data['subjects'] = processed_subjects
        
        update_data['updated_at'] = datetime.utcnow()
        
        # Update class
        db.classes.update_one(
            {'_id': obj_id},
            {'$set': update_data}
        )
        
        # Get updated class
        updated_class = db.classes.find_one({'_id': obj_id})
        serialized_class = serialize_document(updated_class)
        
        return jsonify({
            'success': True,
            'message': 'Class updated successfully',
            'class': serialized_class
        }), 200
        
    except Exception as e:
        print(f"Error in update_class: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Delete class
@classes_bp.route('/classes/<string:class_id>', methods=['DELETE'])
def delete_class(class_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(class_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid class ID'}), 400
        
        class_obj = db.classes.find_one({'_id': obj_id})
        if not class_obj:
            return jsonify({'success': False, 'message': 'Class not found'}), 404
        
        # Delete class
        db.classes.delete_one({'_id': obj_id})
        
        return jsonify({
            'success': True,
            'message': 'Class deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error in delete_class: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get courses by grade level
@classes_bp.route('/courses/grade/<string:grade>', methods=['GET'])
def get_courses_by_grade(grade):
    try:
        db = current_app.db
        
        # Get subjects first
        subjects = list(db.subjects.find({}).sort('name', 1))
        
        # Define courses for different grade levels with subjects
        grade_courses = {
            '1': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Environmental Studies', 'subjects': ['Environmental Science', 'Social Studies']},
                {'name': 'Art & Craft', 'subjects': ['Art', 'Craft']}
            ],
            '2': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Environmental Studies', 'subjects': ['Environmental Science', 'Social Studies']},
                {'name': 'Art & Craft', 'subjects': ['Art', 'Craft']}
            ],
            '3': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Environmental Studies', 'subjects': ['Environmental Science', 'Social Studies']},
                {'name': 'General Knowledge', 'subjects': ['General Knowledge']}
            ],
            '4': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Environmental Studies', 'subjects': ['Environmental Science', 'Social Studies']},
                {'name': 'General Knowledge', 'subjects': ['General Knowledge']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '5': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Science', 'subjects': ['Physics', 'Chemistry', 'Biology']},
                {'name': 'Social Studies', 'subjects': ['History', 'Geography', 'Civics']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '6': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Science', 'subjects': ['Physics', 'Chemistry', 'Biology']},
                {'name': 'Social Studies', 'subjects': ['History', 'Geography', 'Civics']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '7': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Science', 'subjects': ['Physics', 'Chemistry', 'Biology']},
                {'name': 'Social Studies', 'subjects': ['History', 'Geography', 'Civics']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '8': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Hindi', 'subjects': ['Hindi Language', 'Hindi Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Science', 'subjects': ['Physics', 'Chemistry', 'Biology']},
                {'name': 'Social Studies', 'subjects': ['History', 'Geography', 'Civics']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '9': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Physics', 'subjects': ['Physics']},
                {'name': 'Chemistry', 'subjects': ['Chemistry']},
                {'name': 'Biology', 'subjects': ['Biology']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '10': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Physics', 'subjects': ['Physics']},
                {'name': 'Chemistry', 'subjects': ['Chemistry']},
                {'name': 'Biology', 'subjects': ['Biology']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '11': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Physics', 'subjects': ['Physics']},
                {'name': 'Chemistry', 'subjects': ['Chemistry']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Biology', 'subjects': ['Biology']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ],
            '12': [
                {'name': 'English', 'subjects': ['English Language', 'English Literature']},
                {'name': 'Physics', 'subjects': ['Physics']},
                {'name': 'Chemistry', 'subjects': ['Chemistry']},
                {'name': 'Mathematics', 'subjects': ['Mathematics']},
                {'name': 'Biology', 'subjects': ['Biology']},
                {'name': 'Computer Science', 'subjects': ['Computer Science']}
            ]
        }
        
        # Get courses for the requested grade
        courses_data = grade_courses.get(grade, [
            {'name': 'English', 'subjects': ['English Language', 'English Literature']},
            {'name': 'Mathematics', 'subjects': ['Mathematics']},
            {'name': 'Science', 'subjects': ['Physics', 'Chemistry', 'Biology']}
        ])
        
        # Convert to our course format with subject references
        courses = []
        for i, course_data in enumerate(courses_data):
            course_name = course_data['name']
            course_code = f"{course_name[:3].upper()}{grade.zfill(2)}{i+1:02d}"
            
            # Find subject IDs for this course
            course_subjects = []
            for subject_name in course_data['subjects']:
                subject_obj = next((s for s in subjects if s.get('name') == subject_name), None)
                if subject_obj:
                    course_subjects.append({
                        'id': str(subject_obj['_id']),
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', '')
                    })
            
            courses.append({
                'id': f'CRS{grade.zfill(2)}{i+1:03d}',
                'name': course_name,
                'code': course_code,
                'grade': grade,
                'subjects': course_subjects
            })
        
        return jsonify({
            'success': True,
            'courses': courses,
            'grade': grade
        }), 200
        
    except Exception as e:
        print(f"Error in get_courses_by_grade: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get all courses
@classes_bp.route('/courses', methods=['GET'])
def get_all_courses():
    try:
        # Get all grades
        grades = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
        all_courses = []
        
        # Get courses for each grade
        for grade in grades:
            response = get_courses_by_grade(grade)
            if response[0].json['success']:
                all_courses.extend(response[0].json['courses'])
        
        return jsonify({
            'success': True,
            'courses': all_courses
        }), 200
        
    except Exception as e:
        print(f"Error in get_all_courses: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get all subjects
@classes_bp.route('/subjects', methods=['GET'])
def get_subjects():
    try:
        db = current_app.db
        
        # Get subjects
        subjects = list(db.subjects.find({}).sort('name', 1))
        
        # Serialize documents
        serialized_subjects = []
        for subject in subjects:
            serialized_subject = serialize_document(subject)
            serialized_subjects.append(serialized_subject)
        
        return jsonify({
            'success': True,
            'subjects': serialized_subjects,
            'total': len(serialized_subjects)
        }), 200
        
    except Exception as e:
        print(f"Error in get_subjects: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Create new subject
@classes_bp.route('/subjects', methods=['POST'])
def create_subject():
    try:
        db = current_app.db
        data = request.get_json()
        
        # Validate required fields
        if 'name' not in data or not data['name']:
            return jsonify({'success': False, 'message': 'Subject name is required'}), 400
        
        # Check if subject already exists
        existing_subject = db.subjects.find_one({'name': data['name']})
        if existing_subject:
            return jsonify({'success': False, 'message': 'Subject already exists'}), 400
        
        # Generate subject code
        subject_count = db.subjects.count_documents({}) + 1
        subject_code = f'SUB{subject_count:03d}'
        
        # Prepare subject document
        subject_doc = {
            'name': data['name'],
            'code': data.get('code', subject_code),
            'description': data.get('description', ''),
            'credits': data.get('credits', 0),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Insert subject
        result = db.subjects.insert_one(subject_doc)
        subject_doc['_id'] = result.inserted_id
        
        # Get created subject
        created_subject = serialize_document(subject_doc)
        
        return jsonify({
            'success': True,
            'message': 'Subject created successfully',
            'subject': created_subject
        }), 201
        
    except Exception as e:
        print(f"Error in create_subject: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Update subject
@classes_bp.route('/subjects/<string:subject_id>', methods=['PUT'])
def update_subject(subject_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(subject_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid subject ID'}), 400
        
        subject_obj = db.subjects.find_one({'_id': obj_id})
        if not subject_obj:
            return jsonify({'success': False, 'message': 'Subject not found'}), 404
        
        data = request.get_json()
        update_data = {}
        
        # Update subject fields
        if 'name' in data:
            update_data['name'] = data['name']
        
        if 'code' in data:
            update_data['code'] = data['code']
        
        if 'description' in data:
            update_data['description'] = data['description']
        
        if 'credits' in data:
            update_data['credits'] = data['credits']
        
        update_data['updated_at'] = datetime.utcnow()
        
        # Update subject
        db.subjects.update_one(
            {'_id': obj_id},
            {'$set': update_data}
        )
        
        # Get updated subject
        updated_subject = db.subjects.find_one({'_id': obj_id})
        serialized_subject = serialize_document(updated_subject)
        
        return jsonify({
            'success': True,
            'message': 'Subject updated successfully',
            'subject': serialized_subject
        }), 200
        
    except Exception as e:
        print(f"Error in update_subject: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Delete subject
@classes_bp.route('/subjects/<string:subject_id>', methods=['DELETE'])
def delete_subject(subject_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(subject_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid subject ID'}), 400
        
        subject_obj = db.subjects.find_one({'_id': obj_id})
        if not subject_obj:
            return jsonify({'success': False, 'message': 'Subject not found'}), 404
        
        # Check if subject is used in any class
        used_in_classes = db.classes.find_one({'subjects.id': str(obj_id)})
        if used_in_classes:
            return jsonify({
                'success': False, 
                'message': 'Cannot delete subject. It is assigned to one or more classes.'
            }), 400
        
        # Delete subject
        db.subjects.delete_one({'_id': obj_id})
        
        return jsonify({
            'success': True,
            'message': 'Subject deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error in delete_subject: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get single subject
@classes_bp.route('/subjects/<string:subject_id>', methods=['GET'])
def get_subject(subject_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(subject_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid subject ID'}), 400
        
        subject_obj = db.subjects.find_one({'_id': obj_id})
        if not subject_obj:
            return jsonify({'success': False, 'message': 'Subject not found'}), 404
        
        # Serialize subject
        serialized_subject = serialize_document(subject_obj)
        
        return jsonify({
            'success': True,
            'subject': serialized_subject
        }), 200
        
    except Exception as e:
        print(f"Error in get_subject: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Update class subjects
@classes_bp.route('/classes/<string:class_id>/subjects', methods=['PUT'])
def update_class_subjects(class_id):
    try:
        db = current_app.db
        obj_id = validate_object_id(class_id)
        if not obj_id:
            return jsonify({'success': False, 'message': 'Invalid class ID'}), 400
        
        class_obj = db.classes.find_one({'_id': obj_id})
        if not class_obj:
            return jsonify({'success': False, 'message': 'Class not found'}), 404
        
        data = request.get_json()
        subjects = data.get('subjects', [])
        
        # Process subjects
        processed_subjects = []
        for subject in subjects:
            subject_id = subject.get('id')
            if subject_id and validate_object_id(subject_id):
                # Verify subject exists
                subject_obj = db.subjects.find_one({'_id': ObjectId(subject_id)})
                if subject_obj:
                    processed_subjects.append({
                        'id': subject_id,
                        'name': subject_obj.get('name', ''),
                        'code': subject_obj.get('code', '')
                    })
        
        # Update class subjects
        db.classes.update_one(
            {'_id': obj_id},
            {'$set': {
                'subjects': processed_subjects,
                'updated_at': datetime.utcnow()
            }}
        )
        
        # Get updated class
        updated_class = db.classes.find_one({'_id': obj_id})
        serialized_class = serialize_document(updated_class)
        
        return jsonify({
            'success': True,
            'message': 'Class subjects updated successfully',
            'class': serialized_class
        }), 200
        
    except Exception as e:
        print(f"Error in update_class_subjects: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Initialize database with basic subjects (optional)
@classes_bp.route('/initialize-db', methods=['POST'])
def initialize_database():
    try:
        db = current_app.db
        
        # Only initialize if database is empty
        subjects_count = db.subjects.count_documents({})
        if subjects_count > 0:
            return jsonify({
                'success': False,
                'message': 'Database already initialized'
            }), 400
        
        # Basic subjects for school
        basic_subjects = [
            {'name': 'English Language', 'code': 'ENG101', 'description': 'English Language Studies', 'credits': 3},
            {'name': 'English Literature', 'code': 'ENG102', 'description': 'English Literature Studies', 'credits': 3},
            {'name': 'Hindi Language', 'code': 'HIN101', 'description': 'Hindi Language Studies', 'credits': 3},
            {'name': 'Hindi Literature', 'code': 'HIN102', 'description': 'Hindi Literature Studies', 'credits': 3},
            {'name': 'Mathematics', 'code': 'MAT101', 'description': 'Mathematics', 'credits': 4},
            {'name': 'Physics', 'code': 'PHY101', 'description': 'Physics', 'credits': 4},
            {'name': 'Chemistry', 'code': 'CHE101', 'description': 'Chemistry', 'credits': 4},
            {'name': 'Biology', 'code': 'BIO101', 'description': 'Biology', 'credits': 4},
            {'name': 'Computer Science', 'code': 'COM101', 'description': 'Computer Science', 'credits': 3},
            {'name': 'Environmental Science', 'code': 'ENV101', 'description': 'Environmental Science', 'credits': 3},
            {'name': 'Social Studies', 'code': 'SOC101', 'description': 'Social Studies', 'credits': 3},
            {'name': 'History', 'code': 'HIS101', 'description': 'History', 'credits': 3},
            {'name': 'Geography', 'code': 'GEO101', 'description': 'Geography', 'credits': 3},
            {'name': 'Civics', 'code': 'CIV101', 'description': 'Civics', 'credits': 2},
            {'name': 'General Knowledge', 'code': 'GEN101', 'description': 'General Knowledge', 'credits': 2},
            {'name': 'Art', 'code': 'ART101', 'description': 'Art Studies', 'credits': 2},
            {'name': 'Craft', 'code': 'CRA101', 'description': 'Craft Studies', 'credits': 2},
            {'name': 'Physical Education', 'code': 'PE101', 'description': 'Physical Education', 'credits': 2},
            {'name': 'Music', 'code': 'MUS101', 'description': 'Music Studies', 'credits': 2},
            {'name': 'Dance', 'code': 'DAN101', 'description': 'Dance Studies', 'credits': 2}
        ]
        
        # Insert subjects
        result = db.subjects.insert_many(basic_subjects)
        
        return jsonify({
            'success': True,
            'message': 'Database initialized with basic subjects',
            'subjects_added': len(result.inserted_ids)
        }), 201
        
    except Exception as e:
        print(f"Error in initialize_database: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Search subjects
@classes_bp.route('/subjects/search', methods=['GET'])
def search_subjects():
    try:
        db = current_app.db
        
        search = request.args.get('search', '')
        limit = int(request.args.get('limit', 10))
        
        query = {}
        if search:
            query['$or'] = [
                {'name': {'$regex': search, '$options': 'i'}},
                {'code': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}}
            ]
        
        # Get subjects
        subjects = list(db.subjects.find(query).limit(limit).sort('name', 1))
        
        # Serialize documents
        serialized_subjects = []
        for subject in subjects:
            serialized_subject = serialize_document(subject)
            serialized_subjects.append(serialized_subject)
        
        return jsonify({
            'success': True,
            'subjects': serialized_subjects
        }), 200
        
    except Exception as e:
        print(f"Error in search_subjects: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
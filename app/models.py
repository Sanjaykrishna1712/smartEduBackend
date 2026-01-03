from datetime import datetime
from bson import ObjectId
import json

class QuestionBank:
    """MongoDB document structure for reusable questions"""
    
    @staticmethod
    def get_collection(db):
        return db.question_bank
    
    @staticmethod
    def to_dict(doc):
        if '_id' in doc:
            doc['id'] = str(doc['_id'])
            del doc['_id']
        return doc
    
    @staticmethod
    def create_document(data):
        return {
            'question_text': data['question_text'],
            'question_type': data['question_type'],
            'subject': data['subject'],
            'topic': data['topic'],
            'options': data.get('options'),
            'correct_answer': data['correct_answer'],
            'explanation': data.get('explanation', ''),
            'points': data['points'],
            'difficulty': data.get('difficulty', 'medium'),
            'time_estimate': data.get('time_estimate', 2),
            'tags': data.get('tags', []),
            'is_reusable': data.get('is_reusable', True),
            'created_by': data['created_by'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

class Quiz:
    """MongoDB document structure for quizzes"""
    
    @staticmethod
    def get_collection(db):
        return db.quizzes
    
    @staticmethod
    def to_dict(doc):
        if '_id' in doc:
            doc['id'] = str(doc['_id'])
            del doc['_id']
        
        # Convert ObjectId to string for questions
        if 'questions' in doc:
            for q in doc['questions']:
                if '_id' in q:
                    q['id'] = str(q['_id'])
                    del q['_id']
                if 'question_bank_id' in q and isinstance(q['question_bank_id'], ObjectId):
                    q['question_bank_id'] = str(q['question_bank_id'])
        
        return doc
    
    @staticmethod
    def create_document(data):
        return {
            'title': data['title'],
            'subject': data['subject'],
            'description': data.get('description', ''),
            'teacher_id': data['teacher_id'],
            'time_limit': data.get('time_limit', 60),
            'total_points': 0,  # Will be calculated
            'status': data.get('status', 'draft'),
            'questions': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
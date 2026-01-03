from flask import current_app
from bson import ObjectId
from datetime import datetime
import json

def get_db():
    """Get database instance from current app"""
    return current_app.db

def serialize_document(doc):
    """
    Convert MongoDB document to JSON-serializable format
    Handles ObjectId, datetime, and other MongoDB types
    """
    if not doc:
        return None
    
    serialized = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif isinstance(value, datetime):
            serialized[key] = value.isoformat()
        elif isinstance(value, list):
            # Recursively serialize list items
            serialized[key] = [serialize_document(item) if isinstance(item, dict) else 
                              str(item) if isinstance(item, ObjectId) else
                              item.isoformat() if isinstance(item, datetime) else
                              item for item in value]
        elif isinstance(value, dict):
            serialized[key] = serialize_document(value)
        else:
            serialized[key] = value
    
    # Handle _id specially
    if '_id' in doc:
        serialized['id'] = str(doc['_id'])
    
    return serialized

def validate_object_id(id_str):
    """Validate if string is a valid ObjectId"""
    try:
        return ObjectId(id_str)
    except:
        return None

def datetime_to_string(dt):
    """Convert datetime to ISO format string"""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt

def string_to_datetime(date_str):
    """Convert ISO format string to datetime"""
    try:
        if isinstance(date_str, str):
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return None
    return date_str
# app/routes/calendar.py
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import uuid
from bson import ObjectId
from app.utils.mongo import get_db
from flask_cors import cross_origin

# Create Blueprint without URL prefix - we'll register it with prefixes in __init__.py
calendar_bp = Blueprint('calendar', __name__)

# Get event color based on type
def get_event_color(event_type):
    color_map = {
        'class': '#3B82F6',
        'exam': '#EF4444',
        'meeting': '#10B981',
        'event': '#F59E0B',
        'holiday': '#8B5CF6',
        'sports': '#45B7D1',
        'cultural': '#FFEAA7',
        'other': '#778899'
    }
    return color_map.get(event_type, '#778899')

# Helper to serialize MongoDB document
def serialize_document(doc):
    if not doc:
        return {}
    
    result = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, dict):
            result[key] = serialize_document(value)
        elif isinstance(value, list):
            result[key] = [serialize_document(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    
    return result

# Parse date string
def parse_date_string(date_str):
    """Parse date string from various formats"""
    if not date_str:
        return None
    
    # Handle ISO format with timezone
    if date_str.endswith('Z'):
        date_str = date_str[:-1] + '+00:00'
    
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f%z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try ISO format
    try:
        return datetime.fromisoformat(date_str)
    except:
        raise ValueError(f"Unable to parse date string: {date_str}")

# Build audience query
def build_audience_query(user_role=None, current_user=None):
    """Build query based on user role"""
    if user_role in ['principal', 'admin']:
        return {'is_active': True}
    
    if user_role == 'guest' or not user_role:
        return {'is_active': True, 'audience': 'all'}
    
    query = {
        'is_active': True,
        '$or': [
            {'audience': 'all'},
            {'audience': user_role + 's'}
        ]
    }
    
    # Add role-specific audiences
    if user_role == 'teacher':
        query['$or'].append({'audience': 'staff'})
    elif user_role == 'student':
        query['$or'].append({'audience': 'students'})
    
    # Add class restrictions
    if current_user and 'class' in current_user:
        user_class = current_user.get('class', '')
        if user_class:
            query['$or'].append({
                'audience': 'specific_class',
                'class_restriction': {'$in': [user_class]}
            })
    
    return query

# Helper to get user info from request (simplified without JWT)
def get_current_user():
    """Get current user info from request headers or session"""
    # For now, return a default user or extract from simple auth
    # You can implement your own authentication logic here
    
    # Example: Check for a simple token in headers
    auth_token = request.headers.get('X-Auth-Token') or request.headers.get('Authorization')
    
    if auth_token:
        # Simple validation - in real app, validate token properly
        return {
            'role': 'admin',  # Default role for testing
            'user_id': 'admin_001',
            'name': 'Administrator'
        }
    
    # For public access
    return {
        'role': 'guest',
        'user_id': None,
        'name': 'Guest'
    }

# GET: Get all calendar events with filters
@calendar_bp.route('/events', methods=['GET', 'OPTIONS'])
def get_calendar_events():
    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Get query parameters
        month = request.args.get('month')
        event_type = request.args.get('type')
        
        # Get database connection
        db = get_db()
        
        # Build query
        query = build_audience_query(user_role, current_user)
        
        # Filter by month
        if month:
            try:
                year, month_num = map(int, month.split('-'))
                start_date = datetime(year, month_num, 1)
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1)
                else:
                    end_date = datetime(year, month_num + 1, 1)
                
                query['start'] = {
                    '$gte': start_date,
                    '$lt': end_date
                }
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid month format. Use YYYY-MM'
                }), 400
        
        # Filter by event type
        if event_type and event_type != 'all':
            query['type'] = event_type
        
        # Fetch events
        if 'calendar_events' not in db.list_collection_names():
            events = []
        else:
            events_cursor = db.calendar_events.find(query).sort('start', 1)
            events = list(events_cursor)
        
        # Serialize events
        serialized_events = []
        for event in events:
            serialized_event = serialize_document(event)
            serialized_event['color'] = get_event_color(event.get('type', 'other'))
            serialized_event['id'] = str(event.get('_id', ''))
            
            # Add formatted dates
            if isinstance(event.get('start'), datetime):
                serialized_event['formatted_start'] = event['start'].strftime('%Y-%m-%dT%H:%M')
                serialized_event['display_start'] = event['start'].strftime('%b %d, %Y %I:%M %p')
            
            if isinstance(event.get('end'), datetime):
                serialized_event['formatted_end'] = event['end'].strftime('%Y-%m-%dT%H:%M')
                serialized_event['display_end'] = event['end'].strftime('%b %d, %Y %I:%M %p')
            
            serialized_events.append(serialized_event)
        
        # Get event statistics
        event_stats = {
            'total': len(events),
            'classes': len([e for e in events if e.get('type') == 'class']),
            'exams': len([e for e in events if e.get('type') == 'exam']),
            'meetings': len([e for e in events if e.get('type') == 'meeting']),
            'events': len([e for e in events if e.get('type') == 'event']),
            'holidays': len([e for e in events if e.get('type') == 'holiday'])
        }
        
        return jsonify({
            'success': True,
            'events': serialized_events,
            'stats': event_stats,
            'count': len(serialized_events)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching calendar events: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to fetch events: {str(e)}'
        }), 500

# POST: Create a new calendar event
@calendar_bp.route('/events', methods=['POST', 'OPTIONS'])
def create_calendar_event():
    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Check if user has permission (Principal/Admin only)
        if user_role not in ['principal', 'admin']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized: Only principals and admins can create events'
            }), 403
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        print(f"📥 Creating calendar event with data: {data}")
        
        # Validate required fields
        required_fields = ['title', 'start', 'end', 'type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'{field.replace("_", " ").title()} is required'
                }), 400
        
        # Validate dates
        try:
            start_date = data['start']
            end_date = data['end']
            
            # Parse dates
            start_datetime = parse_date_string(start_date)
            end_datetime = parse_date_string(end_date)
            
            if not start_datetime or not end_datetime:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format'
                }), 400
            
            if start_datetime >= end_datetime:
                return jsonify({
                    'success': False,
                    'error': 'End time must be after start time'
                }), 400
                
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid date format: {str(e)}'
            }), 400
        
        # Get database connection
        db = get_db()
        
        # Generate unique event ID
        event_id = f"EVENT{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
        
        # Prepare event data
        event_data = {
            'event_id': event_id,
            'title': data['title'].strip(),
            'description': data.get('description', '').strip(),
            'type': data['type'],
            'start': start_datetime,
            'end': end_datetime,
            'teacher': data.get('teacher', '').strip(),
            'class': data.get('class', '').strip(),
            'location': data.get('location', '').strip(),
            'audience': data.get('audience', 'all'),
            'class_restriction': data.get('class_restriction', []),
            'priority': data.get('priority', 'medium'),
            'color': get_event_color(data['type']),
            'created_by': {
                'user_id': current_user.get('user_id', ''),
                'name': current_user.get('name', 'Administrator'),
                'role': user_role
            },
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'is_active': True,
            'participants': data.get('participants', [])
        }
        
        # Insert event into database
        result = db.calendar_events.insert_one(event_data)
        
        # Get the created event
        created_event = db.calendar_events.find_one({'_id': result.inserted_id})
        
        # Serialize the event
        serialized_event = serialize_document(created_event)
        serialized_event['color'] = get_event_color(created_event.get('type', 'other'))
        
        print(f"✅ Event created successfully: {event_id}")
        return jsonify({
            'success': True,
            'message': 'Event created successfully',
            'event': serialized_event,
            'event_id': event_id
        }), 201
        
    except Exception as e:
        print(f"❌ Error creating calendar event: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to create event: {str(e)}'
        }), 500

# PUT: Update an event
@calendar_bp.route('/events/<event_id>', methods=['PUT', 'OPTIONS'])
@cross_origin(origins="https://smartedufrontend.onrender.com")
def update_event(event_id):

    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Check if user has permission
        if user_role not in ['principal', 'admin']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized: Only principals and admins can update events'
            }), 403
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        # Get database connection
        db = get_db()
        
        # Find the event
        event = db.calendar_events.find_one({
            '$or': [
                {'event_id': event_id},
                {'_id': ObjectId(event_id) if ObjectId.is_valid(event_id) else None}
            ],
            'is_active': True
        })
        
        if not event:
            return jsonify({
                'success': False,
                'error': 'Event not found'
            }), 404
        
        # Prepare update data
        update_data = {'updated_at': datetime.utcnow()}
        
        # Update fields if provided
        if 'title' in data:
            update_data['title'] = data['title'].strip()
        
        if 'description' in data:
            update_data['description'] = data['description'].strip()
        
        if 'type' in data:
            update_data['type'] = data['type']
            update_data['color'] = get_event_color(data['type'])
        
        if 'start' in data and 'end' in data:
            try:
                start_date = data['start']
                end_date = data['end']
                
                # Parse dates
                start_datetime = parse_date_string(start_date)
                end_datetime = parse_date_string(end_date)
                
                if not start_datetime or not end_datetime:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid date format'
                    }), 400
                
                if start_datetime >= end_datetime:
                    return jsonify({
                        'success': False,
                        'error': 'End time must be after start time'
                    }), 400
                
                update_data['start'] = start_datetime
                update_data['end'] = end_datetime
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': f'Invalid date format: {str(e)}'
                }), 400
        
        # Update other fields
        field_mappings = {
            'teacher': 'teacher',
            'class': 'class',
            'location': 'location',
            'audience': 'audience',
            'class_restriction': 'class_restriction',
            'priority': 'priority',
            'participants': 'participants'
        }
        
        for json_key, db_key in field_mappings.items():
            if json_key in data:
                if isinstance(data[json_key], str):
                    update_data[db_key] = data[json_key].strip()
                else:
                    update_data[db_key] = data[json_key]
        
        # Add updated by info
        update_data['updated_by'] = {
            'user_id': current_user.get('user_id'),
            'name': current_user.get('name', 'Administrator'),
            'role': user_role
        }
        
        # Update the event
        db.calendar_events.update_one(
            {'_id': event['_id']},
            {'$set': update_data}
        )
        
        # Get updated event
        updated_event = db.calendar_events.find_one({'_id': event['_id']})
        
        # Serialize the updated event
        serialized_event = serialize_document(updated_event)
        serialized_event['color'] = get_event_color(updated_event.get('type', 'other'))
        
        return jsonify({
            'success': True,
            'message': 'Event updated successfully',
            'event': serialized_event
        }), 200
        
    except Exception as e:
        print(f"❌ Error updating event: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Failed to update event: {str(e)}'
        }), 500

# DELETE: Soft delete an event
@calendar_bp.route('/events/<event_id>', methods=['DELETE', 'OPTIONS'])
def delete_event(event_id):
    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Check if user has permission
        if user_role not in ['principal', 'admin']:
            return jsonify({
                'success': False,
                'error': 'Unauthorized: Only principals and admins can delete events'
            }), 403
        
        # Get database connection
        db = get_db()
        
        # Find the event
        event = db.calendar_events.find_one({
            '$or': [
                {'event_id': event_id},
                {'_id': ObjectId(event_id) if ObjectId.is_valid(event_id) else None}
            ],
            'is_active': True
        })
        
        if not event:
            return jsonify({
                'success': False,
                'error': 'Event not found'
            }), 404
        
        # Soft delete (mark as inactive)
        db.calendar_events.update_one(
            {'_id': event['_id']},
            {
                '$set': {
                    'is_active': False,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': {
                        'user_id': current_user.get('user_id'),
                        'name': current_user.get('name', 'Administrator'),
                        'role': user_role
                    }
                }
            }
        )
        
        return jsonify({
            'success': True,
            'message': 'Event deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"❌ Error deleting event: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to delete event: {str(e)}'
        }), 500

# GET: Get upcoming events (next 7 days)
@calendar_bp.route('/events/upcoming', methods=['GET', 'OPTIONS'])
def get_upcoming_events():
    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Get database connection
        db = get_db()
        
        # Calculate date range
        now = datetime.utcnow()
        seven_days_later = now + timedelta(days=7)
        
        # Build query for upcoming events
        query = build_audience_query(user_role, current_user)
        query['start'] = {
            '$gte': now,
            '$lte': seven_days_later
        }
        
        # Fetch upcoming events
        if 'calendar_events' not in db.list_collection_names():
            events = []
        else:
            events_cursor = db.calendar_events.find(query).sort('start', 1).limit(10)
            events = list(events_cursor)
        
        # Serialize events
        serialized_events = []
        for event in events:
            serialized_event = serialize_document(event)
            serialized_event['color'] = get_event_color(event.get('type', 'other'))
            serialized_events.append(serialized_event)
        
        return jsonify({
            'success': True,
            'events': serialized_events,
            'count': len(serialized_events)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching upcoming events: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch upcoming events: {str(e)}'
        }), 500

# GET: Get event statistics
@calendar_bp.route('/stats', methods=['GET', 'OPTIONS'])
def get_calendar_stats():
    try:
        # Get current user info
        current_user = get_current_user()
        user_role = current_user.get('role', 'guest')
        
        # Get database connection
        db = get_db()
        
        # Build query based on user role
        query = build_audience_query(user_role, current_user)
        
        # Get current month events
        now = datetime.utcnow()
        current_month_start = datetime(now.year, now.month, 1)
        if now.month == 12:
            next_month_start = datetime(now.year + 1, 1, 1)
        else:
            next_month_start = datetime(now.year, now.month + 1, 1)
        
        month_query = {
            **query,
            'start': {
                '$gte': current_month_start,
                '$lt': next_month_start
            }
        }
        
        # Check if collection exists
        if 'calendar_events' not in db.list_collection_names():
            stats = {
                'total': 0,
                'classes': 0,
                'exams': 0,
                'meetings': 0,
                'events': 0,
                'holidays': 0,
                'other': 0
            }
            upcoming_count = 0
            today_count = 0
        else:
            # Get event counts by type
            pipeline = [
                {'$match': month_query},
                {'$group': {
                    '_id': '$type',
                    'count': {'$sum': 1}
                }}
            ]
            
            type_counts = list(db.calendar_events.aggregate(pipeline))
            
            # Initialize stats
            stats = {
                'total': 0,
                'classes': 0,
                'exams': 0,
                'meetings': 0,
                'events': 0,
                'holidays': 0,
                'other': 0
            }
            
            # Fill stats
            for count in type_counts:
                event_type = count['_id']
                if event_type in stats:
                    stats[event_type] = count['count']
                    stats['total'] += count['count']
                else:
                    stats['other'] += count['count']
                    stats['total'] += count['count']
            
            # Get upcoming events count (next 7 days)
            seven_days_later = now + timedelta(days=7)
            upcoming_query = {
                **query,
                'start': {
                    '$gte': now,
                    '$lte': seven_days_later
                }
            }
            upcoming_count = db.calendar_events.count_documents(upcoming_query)
            
            # Get today's events count
            today_start = datetime(now.year, now.month, now.day)
            today_end = datetime(now.year, now.month, now.day, 23, 59, 59)
            today_query = {
                **query,
                'start': {
                    '$gte': today_start,
                    '$lte': today_end
                }
            }
            today_count = db.calendar_events.count_documents(today_query)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'upcoming_count': upcoming_count,
            'today_count': today_count,
            'month': now.strftime('%B %Y')
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching calendar stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to fetch stats: {str(e)}'
        }), 500

from flask import Blueprint, request, jsonify, send_file, Response, current_app, send_from_directory
from werkzeug.utils import secure_filename
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson.objectid import ObjectId
import os
import uuid
from datetime import datetime
import json
import math
import mimetypes
from flask_cors import cross_origin
import traceback

content_bp = Blueprint('content', __name__, url_prefix='/api/content')

# File type mappings
FILE_TYPES = {
    'pdf': ['application/pdf'],
    'video': ['video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'],
    'audio': ['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp3', 'audio/x-m4a'],
    'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'],
    'document': [
        'application/msword', 
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
        'application/rtf'
    ],
    'presentation': [
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ],
    'spreadsheet': [
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]
}

# IMPORTANT: Correct base upload directory
# Since your file is at D:\Intelligent_Education\backend\uploads\image\
# The base directory should be: D:\Intelligent_Education\backend\uploads
# Let's use relative path to ensure it works on any system
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Goes up to backend folder
BASE_UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

print(f"📂 Base upload directory set to: {BASE_UPLOAD_DIR}")
print(f"📂 Directory exists: {os.path.exists(BASE_UPLOAD_DIR)}")

# Subdirectories for different file types
UPLOAD_SUBDIRS = {
    'pdf': 'pdf',
    'video': 'video',
    'audio': 'audio',
    'image': 'image',
    'document': 'documents',
    'presentation': 'presentations',
    'spreadsheet': 'spreadsheets'
}

def ensure_upload_dirs():
    """Create all upload directories if they don't exist"""
    print(f"\n🔧 Ensuring upload directories exist...")
    print(f"   Base directory: {BASE_UPLOAD_DIR}")
    
    # Create base directory
    os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)
    print(f"   ✅ Base upload directory ready")
    
    # Create all subdirectories
    for subdir in UPLOAD_SUBDIRS.values():
        dir_path = os.path.join(BASE_UPLOAD_DIR, subdir)
        os.makedirs(dir_path, exist_ok=True)
        print(f"   📁 Created/verified: {subdir}")
    
    print(f"   📊 Checking existing files...")
    for root, dirs, files in os.walk(BASE_UPLOAD_DIR):
        level = root.replace(BASE_UPLOAD_DIR, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files[:5]:  # Show first 5 files
            print(f'{subindent}{file}')
        if len(files) > 5:
            print(f'{subindent}... and {len(files) - 5} more files')

# Create directories on startup
ensure_upload_dirs()

def get_content_collections():
    """Get MongoDB collections from Flask app"""
    try:
        # Access the Flask app's MongoDB connection
        db = current_app.db
        # Check if collections exist, create them if they don't
        if 'resources' not in db.list_collection_names():
            db.create_collection('resources')
        if 'folders' not in db.list_collection_names():
            db.create_collection('folders')
        if 'subjects' not in db.list_collection_names():
            db.create_collection('subjects')
        if 'classes' not in db.list_collection_names():
            db.create_collection('classes')
        if 'stats' not in db.list_collection_names():
            db.create_collection('stats')
            
        return {
            'resources': db.resources,
            'folders': db.folders,
            'subjects': db.subjects,
            'classes': db.classes,
            'stats': db.stats
        }
    except Exception as e:
        print(f"Error getting collections: {e}")
        # Fallback to direct connection if needed
        client = MongoClient('mongodb://localhost:27017/')
        db = client['resources']
        return {
            'resources': db.resources,
            'folders': db.folders,
            'subjects': db.subjects,
            'classes': db.classes,
            'stats': db.stats
        }

def get_file_type(mime_type):
    """Determine file type from MIME type"""
    for file_type, mime_types in FILE_TYPES.items():
        if mime_type in mime_types:
            return file_type
    return 'document'

def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False
    
    ALLOWED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.txt', '.rtf',
        '.ppt', '.pptx', 
        '.xls', '.xlsx',
        '.mp4', '.avi', '.mov', '.mkv', '.webm',
        '.mp3', '.wav', '.ogg', '.m4a', '.flac',
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg'
    }
    
    ext = '.' + filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def format_file_size(bytes):
    """Format file size to human readable format"""
    if bytes == 0:
        return "0 Bytes"
    k = 1024
    sizes = ["Bytes", "KB", "MB", "GB"]
    i = int(math.floor(math.log(bytes) / math.log(k)))
    return f"{bytes / math.pow(k, i):.2f} {sizes[i]}"

def ensure_list(data):
    """Ensure data is a list, parsing JSON string if needed"""
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return []
    return data or []

def prepare_content_for_response(content):
    """Convert MongoDB document to JSON-friendly format"""
    if not content:
        return None
    
    content_dict = dict(content)
    
    # Convert ObjectId to string
    content_dict['id'] = str(content_dict['_id'])
    
    # Format file size if not already formatted
    if 'file_size' in content_dict and 'file_size_formatted' not in content_dict:
        content_dict['file_size_formatted'] = format_file_size(content_dict['file_size'])
    
    # Convert any ObjectId fields in lists
    if 'assigned_to' in content_dict and content_dict['assigned_to']:
        # Convert ObjectId to string in assigned_to list
        content_dict['assigned_to'] = [str(obj_id) if isinstance(obj_id, ObjectId) else obj_id 
                                      for obj_id in content_dict['assigned_to']]
    
    # Remove the original _id field
    if '_id' in content_dict:
        del content_dict['_id']
    
    # Convert datetime objects to strings
    for key in ['uploaded_at', 'updated_at', 'last_updated']:
        if key in content_dict and isinstance(content_dict[key], datetime):
            content_dict[key] = content_dict[key].isoformat()
    
    return content_dict

def get_content_type_from_mime(mime_type):
    """Map MIME type to content type"""
    if mime_type.startswith('video/'):
        return 'video', 'video'
    elif mime_type.startswith('audio/'):
        return 'audio', 'audio'
    elif mime_type.startswith('image/'):
        return 'image', 'image'
    elif mime_type == 'application/pdf':
        return 'document', 'pdf'
    elif 'presentation' in mime_type:
        return 'presentation', 'presentations'
    elif 'spreadsheet' in mime_type:
        return 'spreadsheet', 'spreadsheets'
    elif 'document' in mime_type or 'text' in mime_type:
        return 'document', 'documents'
    else:
        return 'document', 'documents'

# ============= ROUTES =============

@content_bp.route('/upload', methods=['POST', 'OPTIONS'])
@cross_origin()
def upload_content():
    """Upload single or multiple files"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print(f"\n📤 Upload endpoint called!")
    print(f"   Upload directory: {BASE_UPLOAD_DIR}")
    
    if 'files' not in request.files:
        print("❌ No files in request")
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    print(f"📄 Number of files: {len(files)}")
    
    if len(files) == 0:
        return jsonify({'error': 'No files selected'}), 400
    
    collections = get_content_collections()
    resources = collections['resources']
    uploaded_content = []
    
    for file in files:
        if file.filename == '':
            print("⚠️ Empty filename skipped")
            continue
            
        print(f"📁 Processing file: {file.filename}")
        
        if file and allowed_file(file.filename):
            # Generate unique filename
            original_filename = secure_filename(file.filename)
            file_extension = os.path.splitext(original_filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Determine file type and upload path
            mime_type = file.content_type or mimetypes.guess_type(original_filename)[0] or 'application/octet-stream'
            content_type, subdir = get_content_type_from_mime(mime_type)
            
            # Create full upload path
            upload_dir = os.path.join(BASE_UPLOAD_DIR, subdir)
            os.makedirs(upload_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(upload_dir, unique_filename)
            print(f"💾 Saving to: {file_path}")
            file.save(file_path)
            
            # Verify file was saved
            if os.path.exists(file_path):
                print(f"✅ File saved successfully: {file_path}")
            else:
                print(f"❌ File NOT saved: {file_path}")
                return jsonify({'error': f'Failed to save file: {original_filename}'}), 500
            
            # Parse form data with defaults
            form_data = request.form.to_dict()
            print(f"📋 Form data: {form_data}")
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Create content record in MongoDB
            content_data = {
                'type': content_type,
                'title': form_data.get('title', os.path.splitext(original_filename)[0]),
                'description': form_data.get('description', ''),
                'subject': form_data.get('subject', 'General'),
                'topic': form_data.get('topic', ''),
                'folder': form_data.get('folder', 'Uploads'),
                'status': form_data.get('status', 'draft'),
                'access': form_data.get('access', 'private'),
                'author': form_data.get('author', 'Teacher'),
                'original_filename': original_filename,
                'stored_filename': unique_filename,
                'file_path': file_path,  # Store absolute path
                'file_size': file_size,
                'file_size_formatted': format_file_size(file_size),
                'mime_type': mime_type,
                'tags': ensure_list(form_data.get('tags', '[]')),
                'assigned_to': ensure_list(form_data.get('assigned_to', '[]')),
                'views': 0,
                'downloads': 0,
                'likes': 0,
                'shares': 0,
                'completion_rate': 0,
                'uploaded_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            # Insert into MongoDB
            result = resources.insert_one(content_data)
            content_data['_id'] = result.inserted_id
            content_data['id'] = str(result.inserted_id)

            uploaded_content.append(prepare_content_for_response(content_data))
            print(f"✅ Added content to MongoDB: {content_data['title']}")
        else:
            print(f"❌ File not allowed: {file.filename}")
            return jsonify({'error': f'File type not allowed: {file.filename}'}), 400
    
    print(f"🎉 Uploaded {len(uploaded_content)} files")
    return jsonify({'success': True, 'uploaded': uploaded_content}), 201

@content_bp.route('/', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_all_content():
    """Get all content with filters"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("📚 GET all content endpoint called")
    
    # Parse query parameters
    content_type = request.args.get('type', 'all')
    folder = request.args.get('folder', 'all')
    subject = request.args.get('subject', 'all')
    status = request.args.get('status', 'all')
    class_id = request.args.get('class_id', 'all')
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'uploaded_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    collections = get_content_collections()
    resources = collections['resources']
    
    # Build MongoDB query
    query = {}
    
    if content_type != 'all':
        query['type'] = content_type
    
    if folder != 'all':
        query['folder'] = folder
    
    if subject != 'all':
        query['subject'] = subject
    
    if status != 'all':
        query['status'] = status
    
    if class_id != 'all':
        query['assigned_to'] = class_id
    
    if search:
        query['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'description': {'$regex': search, '$options': 'i'}},
            {'tags': {'$regex': search, '$options': 'i'}}
        ]
    
    # Determine sort order
    sort_direction = DESCENDING if sort_order == 'desc' else ASCENDING
    sort_field = 'uploaded_at'
    
    if sort_by == 'title':
        sort_field = 'title'
    elif sort_by == 'views':
        sort_field = 'views'
    elif sort_by == 'uploaded_at':
        sort_field = 'uploaded_at'
    elif sort_by == 'completion_rate':
        sort_field = 'completion_rate'
    
    # Execute query
    filtered = list(resources.find(query).sort(sort_field, sort_direction))
    
    # Convert to JSON-friendly format
    result = []
    for item in filtered:
        content_dict = prepare_content_for_response(item)
        if content_dict:
            result.append(content_dict)
    
    return jsonify(result)

@content_bp.route('/<content_id>', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_content(content_id):
    """Get specific content by ID"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print(f"🔍 GET content by ID: {content_id}")
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        
        content = resources.find_one({'_id': ObjectId(content_id)})
        if not content:
            return jsonify({'error': 'Content not found'}), 404
        
        # Increment view count
        resources.update_one(
            {'_id': ObjectId(content_id)},
            {'$inc': {'views': 1}}
        )
        
        # Return the content
        content_dict = prepare_content_for_response(content)
        return jsonify(content_dict)
    except Exception as e:
        print(f"❌ Error getting content: {e}")
        return jsonify({'error': 'Invalid content ID'}), 400

@content_bp.route('/<content_id>/download', methods=['GET', 'OPTIONS'])
@cross_origin()
def download_content(content_id):
    """Download content file"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print(f"\n⬇️ Download endpoint called for ID: {content_id}")
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        
        content = resources.find_one({'_id': ObjectId(content_id)})
        if not content:
            print(f"❌ Content not found: {content_id}")
            return jsonify({'error': 'Content not found'}), 404
        
        print(f"📄 Content found: {content.get('title', 'Unknown')}")
        print(f"   Stored filename: {content.get('stored_filename', 'N/A')}")
        print(f"   File path in DB: {content.get('file_path', 'N/A')}")
        
        # Get file path from database
        file_path = content.get('file_path', '')
        
        if not file_path:
            print(f"❌ No file path in database")
            return jsonify({'error': 'No file path found in database'}), 404
        
        # Check if file exists
        if os.path.exists(file_path):
            print(f"✅ File exists at: {file_path}")
            
            # Increment download count
            resources.update_one(
                {'_id': ObjectId(content_id)},
                {'$inc': {'downloads': 1}}
            )
            
            try:
                return send_file(
                    file_path,
                    as_attachment=True,
                    download_name=content['original_filename'],
                    mimetype=content.get('mime_type', 'application/octet-stream')
                )
            except Exception as e:
                print(f"❌ Error sending file: {e}")
                print(traceback.format_exc())
                return jsonify({'error': f'File could not be sent: {str(e)}'}), 500
        else:
            print(f"❌ File NOT found at path: {file_path}")
            print(f"   Trying to find file in uploads directory...")
            
            # Try to find the file in the uploads directory
            stored_filename = content.get('stored_filename', '')
            if stored_filename:
                # Search in all subdirectories
                for subdir in UPLOAD_SUBDIRS.values():
                    possible_path = os.path.join(BASE_UPLOAD_DIR, subdir, stored_filename)
                    print(f"   Checking: {possible_path}")
                    if os.path.exists(possible_path):
                        print(f"   ✅ Found file at: {possible_path}")
                        
                        # Update database with correct path
                        resources.update_one(
                            {'_id': ObjectId(content_id)},
                            {'$set': {'file_path': possible_path}}
                        )
                        
                        # Increment download count
                        resources.update_one(
                            {'_id': ObjectId(content_id)},
                            {'$inc': {'downloads': 1}}
                        )
                        
                        return send_file(
                            possible_path,
                            as_attachment=True,
                            download_name=content['original_filename'],
                            mimetype=content.get('mime_type', 'application/octet-stream')
                        )
            
            print(f"❌ Could not find file anywhere")
            return jsonify({'error': 'File not found on server'}), 404
            
    except Exception as e:
        print(f"❌ Error downloading content: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 400

@content_bp.route('/<content_id>/preview', methods=['GET', 'OPTIONS'])
@cross_origin()
def preview_content(content_id):
    """Preview content file in browser"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print(f"\n👁️ Preview endpoint called for ID: {content_id}")
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        
        content = resources.find_one({'_id': ObjectId(content_id)})
        if not content:
            print(f"❌ Content not found: {content_id}")
            return jsonify({'error': 'Content not found'}), 404
        
        print(f"📄 Content found: {content.get('title', 'Unknown')}")
        print(f"   MIME type: {content.get('mime_type', 'N/A')}")
        print(f"   File path: {content.get('file_path', 'N/A')}")
        
        # Get file path from database
        file_path = content.get('file_path', '')
        
        if not file_path:
            print(f"❌ No file path in database")
            return jsonify({'error': 'No file path found in database'}), 404
        
        # Check if file exists
        if os.path.exists(file_path):
            print(f"✅ File exists at: {file_path}")
        else:
            print(f"❌ File NOT found at path: {file_path}")
            print(f"   Trying to find file in uploads directory...")
            
            # Try to find the file in the uploads directory
            stored_filename = content.get('stored_filename', '')
            if stored_filename:
                # Search in all subdirectories
                for subdir in UPLOAD_SUBDIRS.values():
                    possible_path = os.path.join(BASE_UPLOAD_DIR, subdir, stored_filename)
                    print(f"   Checking: {possible_path}")
                    if os.path.exists(possible_path):
                        print(f"   ✅ Found file at: {possible_path}")
                        file_path = possible_path
                        
                        # Update database with correct path
                        resources.update_one(
                            {'_id': ObjectId(content_id)},
                            {'$set': {'file_path': possible_path}}
                        )
                        break
            
            if not os.path.exists(file_path):
                print(f"❌ Could not find file anywhere")
                return jsonify({'error': 'File not found on server'}), 404
        
        mime_type = content.get('mime_type', 'application/octet-stream')
        
        try:
            # For images, PDFs, videos, audio - serve inline
            if mime_type.startswith('image/'):
                print(f"👁️ Serving image: {file_path}")
                return send_file(file_path, mimetype=mime_type)
            elif mime_type == 'application/pdf':
                print(f"👁️ Serving PDF: {file_path}")
                return send_file(file_path, mimetype=mime_type)
            elif mime_type.startswith('video/'):
                print(f"👁️ Serving video: {file_path}")
                return send_file(file_path, mimetype=mime_type)
            elif mime_type.startswith('audio/'):
                print(f"👁️ Serving audio: {file_path}")
                return send_file(file_path, mimetype=mime_type)
            else:
                print(f"👁️ Serving other file type: {mime_type}")
                return send_file(
                    file_path,
                    as_attachment=False,
                    download_name=content['original_filename'],
                    mimetype=mime_type
                )
        except Exception as e:
            print(f"❌ Error previewing file: {e}")
            print(traceback.format_exc())
            return jsonify({'error': f'File could not be previewed: {str(e)}'}), 500
            
    except Exception as e:
        print(f"❌ Error previewing content: {e}")
        print(traceback.format_exc())
        return jsonify({'error': f'Server error: {str(e)}'}), 400


@content_bp.route('/<content_id>/like', methods=['POST', 'OPTIONS'])
@cross_origin()
def like_content(content_id):
    """Like/unlike content"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        
        content = resources.find_one({'_id': ObjectId(content_id)})
        if not content:
            return jsonify({'error': 'Content not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        action = data.get('action', 'like')  # 'like' or 'unlike'
        
        if action == 'like':
            update_op = {'$inc': {'likes': 1}}
        else:
            # Ensure likes don't go below 0
            current_likes = content.get('likes', 0)
            if current_likes > 0:
                update_op = {'$inc': {'likes': -1}}
            else:
                update_op = {'$set': {'likes': 0}}
        
        resources.update_one(
            {'_id': ObjectId(content_id)},
            update_op
        )
        
        # Get updated likes count
        updated_content = resources.find_one({'_id': ObjectId(content_id)})
        return jsonify({'likes': updated_content.get('likes', 0)})
    except Exception as e:
        print(f"❌ Error liking content: {e}")
        return jsonify({'error': 'Invalid content ID'}), 400

@content_bp.route('/folders', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_folders():
    """Get all folders"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("📁 GET folders endpoint called")
    
    collections = get_content_collections()
    resources = collections['resources']
    folders_col = collections['folders']
    
    # Get all unique folders from content
    pipeline = [
        {"$group": {
            "_id": "$folder",
            "item_count": {"$sum": 1},
            "total_size": {"$sum": "$file_size"},
            "last_updated": {"$max": "$uploaded_at"}
        }}
    ]
    
    folder_stats = list(resources.aggregate(pipeline))
    
    # Add folders from folders collection
    existing_folders = list(folders_col.find({}))
    
    # Combine results
    all_folders = []
    folder_names = set()
    
    # Add from content aggregation
    for folder in folder_stats:
        folder_dict = {
            'id': str(uuid.uuid4()),
            'name': folder['_id'],
            'item_count': folder.get('item_count', 0),
            'size': folder.get('total_size', 0),
            'size_formatted': format_file_size(folder.get('total_size', 0)),
            'description': '',
            'color': 'blue',
            'last_updated': folder.get('last_updated', datetime.utcnow()).isoformat() if folder.get('last_updated') else datetime.utcnow().isoformat()
        }
        all_folders.append(folder_dict)
        folder_names.add(folder_dict['name'])
    
    # Add from folders collection
    for folder in existing_folders:
        if folder['name'] not in folder_names:
            folder_dict = {
                'id': str(folder['_id']),
                'name': folder['name'],
                'description': folder.get('description', ''),
                'color': folder.get('color', 'blue'),
                'item_count': 0,
                'size': 0,
                'size_formatted': '0 Bytes',
                'last_updated': folder.get('created_at', datetime.utcnow()).isoformat() if folder.get('created_at') else datetime.utcnow().isoformat()
            }
            all_folders.append(folder_dict)
    
    return jsonify(all_folders)

@content_bp.route('/folders', methods=['POST', 'OPTIONS'])
@cross_origin()
def create_folder():
    """Create new folder"""
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    folder_name = data.get('name')
    
    if not folder_name:
        return jsonify({'error': 'Folder name is required'}), 400
    
    collections = get_content_collections()
    folders = collections['folders']
    
    # Check if folder already exists in folders collection
    if folders.find_one({'name': folder_name}):
        return jsonify({'error': 'Folder already exists'}), 400
    
    folder_data = {
        'name': folder_name,
        'description': data.get('description', ''),
        'color': data.get('color', 'blue'),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    result = folders.insert_one(folder_data)
    folder_data['_id'] = result.inserted_id
    folder_data['id'] = str(result.inserted_id)
    folder_data['item_count'] = 0
    folder_data['size'] = 0
    folder_data['size_formatted'] = '0 Bytes'
    
    return jsonify(folder_data), 201

@content_bp.route('/subjects', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_subjects():
    """Get all subjects"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("📖 GET subjects endpoint called")
    
    collections = get_content_collections()
    resources = collections['resources']
    
    # Get all unique subjects from content
    pipeline = [
        {"$group": {
            "_id": "$subject",
            "content_count": {"$sum": 1}
        }}
    ]
    
    subject_stats = list(resources.aggregate(pipeline))
    
    # Convert to proper format
    subjects_list = []
    for subject in subject_stats:
        subject_dict = {
            'id': str(uuid.uuid4()),
            'name': subject['_id'],
            'content_count': subject.get('content_count', 0),
            'color': 'blue'
        }
        subjects_list.append(subject_dict)
    
    # If no subjects found, add default
    if not subjects_list:
        subjects_list = [{
            'id': str(uuid.uuid4()),
            'name': 'General',
            'content_count': 0,
            'color': 'blue'
        }]
    
    return jsonify(subjects_list)

@content_bp.route('/classes', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_classes():
    """Get all classes (for filtering)"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("🎓 GET classes endpoint called")
    
    collections = get_content_collections()
    classes_col = collections['classes']
    
    # Get classes from database
    try:
        classes_list = list(classes_col.find({}))
        
        # Convert to proper format
        result = []
        for cls in classes_list:
            cls_dict = {
                'id': str(cls['_id']),
                'name': cls.get('name', ''),
                'subject': cls.get('subject', ''),
                'color': cls.get('color', 'blue')
            }
            result.append(cls_dict)
        
        return jsonify(result)
    except Exception as e:
        print(f"❌ Error fetching classes: {e}")
        # Return empty list if no classes found
        return jsonify([])

@content_bp.route('/stats', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_stats():
    """Get content statistics"""
    if request.method == 'OPTIONS':
        return '', 200
    
    print("📊 GET stats endpoint called")
    
    collections = get_content_collections()
    resources = collections['resources']
    
    # Calculate total counts
    total_content = resources.count_documents({})
    published_content = resources.count_documents({'status': 'published'})
    
    # Aggregate other stats
    pipeline = [
        {"$group": {
            "_id": None,
            "total_views": {"$sum": "$views"},
            "total_likes": {"$sum": "$likes"},
            "total_downloads": {"$sum": "$downloads"},
            "avg_completion": {"$avg": "$completion_rate"}
        }}
    ]
    
    stats_result = list(resources.aggregate(pipeline))
    
    if stats_result:
        agg_stats = stats_result[0]
        total_views = agg_stats.get('total_views', 0)
        total_likes = agg_stats.get('total_likes', 0)
        total_downloads = agg_stats.get('total_downloads', 0)
        avg_completion = agg_stats.get('avg_completion', 0) or 0
    else:
        total_views = total_likes = total_downloads = avg_completion = 0
    
    # Content type distribution
    type_pipeline = [
        {"$group": {
            "_id": "$type",
            "count": {"$sum": 1}
        }}
    ]
    
    type_distribution_result = list(resources.aggregate(type_pipeline))
    type_distribution = {}
    
    for item in type_distribution_result:
        type_distribution[item['_id']] = item['count']
    
    stats_data = {
        'total_content': total_content,
        'published_content': published_content,
        'total_views': total_views,
        'total_likes': total_likes,
        'total_downloads': total_downloads,
        'avg_completion': round(avg_completion, 1),
        'type_distribution': type_distribution
    }
    
    return jsonify(stats_data)

@content_bp.route('/create', methods=['POST', 'OPTIONS'])
@cross_origin()
def create_content():
    """Create content metadata without file"""
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    if not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400
    
    collections = get_content_collections()
    resources = collections['resources']
    
    content_data = {
        'type': data.get('type', 'lesson'),
        'title': data.get('title'),
        'description': data.get('description', ''),
        'subject': data.get('subject', 'General'),
        'topic': data.get('topic', ''),
        'uploaded_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
        'status': data.get('status', 'draft'),
        'views': 0,
        'completion_rate': 0,
        'likes': 0,
        'shares': 0,
        'downloads': 0,
        'file_size': data.get('file_size', 0),
        'mime_type': 'text/plain',
        'tags': data.get('tags', []),
        'author': data.get('author', 'Teacher'),
        'access': data.get('access', 'private'),
        'folder': data.get('folder', 'Drafts'),
        'assigned_to': data.get('assigned_to', []),
        'original_filename': f"{data.get('title')}.txt",
        'stored_filename': f"{uuid.uuid4()}.txt",
        'file_path': '',
        'relative_path': ''
    }
    
    # Insert into MongoDB
    result = resources.insert_one(content_data)
    content_data['_id'] = result.inserted_id
    content_data['id'] = str(result.inserted_id)
    content_data['file_size_formatted'] = format_file_size(content_data['file_size'])
    
    return jsonify(content_data), 201

@content_bp.route('/init', methods=['POST', 'OPTIONS'])
@cross_origin()
def initialize_data():
    """Initialize with sample data"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        folders = collections['folders']
        subjects = collections['subjects']
        classes = collections['classes']
        
        # Clear existing data
        resources.delete_many({})
        folders.delete_many({})
        subjects.delete_many({})
        classes.delete_many({})
        
        # Create sample folders
        sample_folders = [
            {'name': 'Lessons', 'description': 'Lesson materials', 'color': 'blue', 'created_at': datetime.utcnow()},
            {'name': 'Assignments', 'description': 'Student assignments', 'color': 'green', 'created_at': datetime.utcnow()},
            {'name': 'Videos', 'description': 'Educational videos', 'color': 'red', 'created_at': datetime.utcnow()},
            {'name': 'Quizzes', 'description': 'Assessment quizzes', 'color': 'purple', 'created_at': datetime.utcnow()},
            {'name': 'Drafts', 'description': 'Work in progress', 'color': 'yellow', 'created_at': datetime.utcnow()},
        ]
        
        folders.insert_many(sample_folders)
        
        # Create sample classes
        sample_classes = [
            {'name': 'Mathematics 101', 'subject': 'Mathematics', 'color': 'blue'},
            {'name': 'Physics 101', 'subject': 'Physics', 'color': 'green'},
            {'name': 'Chemistry 101', 'subject': 'Chemistry', 'color': 'red'},
            {'name': 'Biology 101', 'subject': 'Biology', 'color': 'purple'},
            {'name': 'Computer Science 101', 'subject': 'Computer Science', 'color': 'yellow'},
        ]
        
        classes.insert_many(sample_classes)
        
        return jsonify({'success': True, 'message': 'Data initialized successfully'})
    except Exception as e:
        print(f"❌ Error initializing data: {e}")
        return jsonify({'error': str(e)}), 500

@content_bp.route('/clear', methods=['POST', 'OPTIONS'])
@cross_origin()
def clear_data():
    """Clear all data (for development only)"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        collections = get_content_collections()
        resources = collections['resources']
        folders = collections['folders']
        subjects = collections['subjects']
        classes = collections['classes']
        
        resources.delete_many({})
        folders.delete_many({})
        subjects.delete_many({})
        classes.delete_many({})
        return jsonify({'success': True, 'message': 'All data cleared'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Add a route to serve uploaded files directly
@content_bp.route('/uploads/<path:filename>')
@cross_origin()
def serve_uploaded_file(filename):
    """Serve uploaded files directly"""
    return send_from_directory(BASE_UPLOAD_DIR, filename)
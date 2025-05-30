from flask import Flask, request, send_from_directory, jsonify, session, redirect, url_for, g
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import os
import json
import shutil
import time
import errno
import stat
import secrets
import hashlib
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import re
import logging
from logging.handlers import RotatingFileHandler
import ipaddress
from email.utils import parseaddr
import threading
import queue
from contextlib import contextmanager
import ssl
import sys

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

# Load environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
SECRET_KEY = os.environ.get('SECRET_KEY')
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

# Set up paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
DB_FILE = os.path.join(DATA_DIR, 'users.db')
LOG_FILE = os.path.join(DATA_DIR, 'access.log')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Force HTTPS
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['DEBUG'] = False  # Disable debug mode in production

# Set session configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # Changed from Lax to Strict
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.secret_key = SECRET_KEY or secrets.token_hex(32)  # Use environment variable or default

# Enable CORS with secure settings
CORS(app, 
     supports_credentials=True,
     resources={
         r"/*": {
             "origins": ALLOWED_ORIGINS,
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "expose_headers": ["Content-Type"],
             "supports_credentials": True
         }
     })

# Global variables
METADATA_FILE = 'metadata.json'
AUTH_FILE = 'auth.json'
LOG_FILE = LOG_FILE
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes in seconds
RATE_LIMIT_REQUESTS = 500  # Increased from 100 to 500
RATE_LIMIT_WINDOW = 60  # Reduced from 3600 to 60 seconds
BATCH_OPERATION_LIMIT = 50  # Number of operations allowed in a batch

# Set up logging
logging.basicConfig(level=logging.DEBUG)
handler = RotatingFileHandler(LOG_FILE, maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))
handler.setLevel(logging.DEBUG)
app.logger.setLevel(logging.DEBUG)
app.logger.addHandler(handler)

# Rate limiting data structure
rate_limits = {}
failed_attempts = {}
ip_blacklist = set()
batch_operations = {}

def is_safe_filename(filename):
    """Check if a filename is safe to use."""
    return bool(re.match(r'^[a-zA-Z0-9_\-\.]+$', filename))

def init_db():
    """Initialize the database with schema."""
    try:
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        
        with sqlite3.connect(DB_FILE) as conn:
            # Read schema from the file
            if os.path.exists(SCHEMA_FILE):
                with open(SCHEMA_FILE, 'r') as f:
                    conn.executescript(f.read())
                    app.logger.info("Database initialized successfully")
            else:
                app.logger.error("Schema file not found")
                raise FileNotFoundError("Schema file not found")
            
            cursor = conn.cursor()
            
            # Check if any admin user exists
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
            admin_exists = cursor.fetchone()[0] > 0
            
            if not admin_exists:
                app.logger.warning("No admin account detected, creating default admin...")
                # Create default admin user
                cursor.execute('''
                    INSERT INTO users (
                        username,
                        password_hash,
                        email,
                        is_admin,
                        is_approved,
                        status,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    'OPERATOR_1337',
                    generate_password_hash('ITgwXqkIl2co6RsgAvBhvQ'),
                    'admin@example.com',
                    True,
                    True,
                    'active',
                    datetime.now(),
                    datetime.now()
                ))
                conn.commit()
                app.logger.info("Default admin user created")
            
    except Exception as e:
        app.logger.error(f"Database initialization error: {str(e)}")
        raise

def get_db():
    """Get database connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_FILE)
        db.row_factory = sqlite3.Row
    return db

def log_audit(user_id, action, details, ip_address):
    """Log audit trail."""
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO audit_log (user_id, action, details, ip_address) VALUES (?, ?, ?, ?)',
                (user_id, action, details, ip_address)
            )
            conn.commit()
    except Exception as e:
        app.logger.error(f"Audit log error: {str(e)}")

def check_rate_limit():
    """Check if the current request exceeds rate limits."""
    try:
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Initialize or reset rate limit data
        if client_ip not in rate_limits:
            rate_limits[client_ip] = {
                'count': 1,
                'start_time': current_time
            }
            return False
            
        # Reset if window expired
        if current_time - rate_limits[client_ip]['start_time'] >= RATE_LIMIT_WINDOW:
            rate_limits[client_ip] = {
                'count': 1,
                'start_time': current_time
            }
            return False
            
        # Increment and check
        rate_limits[client_ip]['count'] += 1
        if rate_limits[client_ip]['count'] > RATE_LIMIT_REQUESTS:
            app.logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return True
            
        return False
        
    except Exception as e:
        app.logger.error(f"Rate limit check error: {str(e)}")
        return False

def is_ip_blocked(ip):
    """Check if IP is blocked."""
    return ip in ip_blacklist

def record_failed_attempt(ip):
    """Record failed login attempt."""
    now = time.time()
    if ip in failed_attempts:
        attempts, first_attempt = failed_attempts[ip]
        if now - first_attempt >= LOCKOUT_DURATION:
            failed_attempts[ip] = (1, now)
        else:
            failed_attempts[ip] = (attempts + 1, first_attempt)
            if attempts + 1 >= MAX_FAILED_ATTEMPTS:
                ip_blacklist.add(ip)
                app.logger.warning(f"IP {ip} blocked due to too many failed attempts")
    else:
        failed_attempts[ip] = (1, now)

def requires_auth(f):
    """Decorator for routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        app.logger.debug(f"Checking auth for {f.__name__}, session: {session}")
        if 'user_id' not in session:
            app.logger.warning(f"Unauthorized access attempt to {f.__name__}")
            return jsonify({'error': 'Unauthorized'}), 401
        app.logger.debug(f"Auth successful for user_id: {session['user_id']}")
        return f(*args, **kwargs)
    return decorated

def requires_admin(f):
    """Decorator for routes that require admin privileges."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            app.logger.warning(f"Unauthorized access attempt to admin endpoint {f.__name__}")
            return jsonify({'error': 'Unauthorized'}), 401
            
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],))
            user = cursor.fetchone()
            
            if not user or not user[0]:
                app.logger.warning(f"Non-admin user {session['user_id']} attempted to access {f.__name__}")
                return jsonify({'error': 'Forbidden'}), 403
                
        return f(*args, **kwargs)
    return decorated

@app.before_request
def enforce_rate_limit():
    """Enforce rate limiting on all requests."""
    # Skip for static files and OPTIONS
    if request.path.startswith('/static/') or request.method == 'OPTIONS':
        return
        
    if check_rate_limit():
        return jsonify({'error': 'Rate limit exceeded'}), 429

@app.before_request
def make_session_permanent():
    session.permanent = True
    session.modified = True

@app.route('/register', methods=['POST'])
def register():
    """Handle user registration requests."""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        
        # Validate inputs
        if not username or len(username) < 3:
            return jsonify({'error': 'Invalid username'}), 400
        
        if not password or len(password) < 12:
            return jsonify({'error': 'Invalid password'}), 400
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            return jsonify({'error': 'Username contains invalid characters'}), 400
        
        if not all(re.search(pattern, password) for pattern in [r'[A-Z]', r'[a-z]', r'[0-9]', r'[!@#$%^&*(),.?":{}|<>]']):
            return jsonify({'error': 'Password does not meet requirements'}), 400
        
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return jsonify({'error': 'Invalid email'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Check if username exists
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                return jsonify({'error': 'Username already exists'}), 400
            
            # Check if registration request exists
            cursor.execute('SELECT id FROM registration_requests WHERE username = ?', (username,))
            if cursor.fetchone():
                return jsonify({'error': 'Registration request already pending'}), 400
            
            # Create registration request (always as non-admin)
            password_hash = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO registration_requests (username, password_hash, email) VALUES (?, ?, ?)',
                (username, password_hash, email)
            )
            
            log_audit(None, 'REGISTRATION_REQUEST', f'New registration request for username: {username}', request.remote_addr)
            
            return jsonify({'message': 'Registration request submitted'}), 200
            
    except Exception as e:
        app.logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/login', methods=['POST'])
def login():
    """Handle user login."""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        client_ip = request.remote_addr
        
        if not username or not password:
            record_failed_attempt(client_ip)
            return jsonify({'error': 'Invalid credentials'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, password_hash, is_approved, status FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            
            if not user or not check_password_hash(user[1], password):
                record_failed_attempt(client_ip)
                return jsonify({'error': 'Invalid credentials'}), 401
            
            if not user[2]:  # not approved
                return jsonify({'error': 'PENDING_APPROVAL'}), 401
            
            if user[3] != 'active':
                return jsonify({'error': 'ACCOUNT_DISABLED'}), 401
            
            # Clear failed attempts on successful login
            if client_ip in failed_attempts:
                del failed_attempts[client_ip]
            
            session['user_id'] = user[0]
            session.permanent = True
            
            # Update last login
            cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user[0],))
            conn.commit()
            
            log_audit(user[0], 'LOGIN', 'Successful login', client_ip)
            
            return jsonify({'success': True}), 200
    
    except Exception as e:
        app.logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/pending-requests', methods=['GET'])
@requires_admin
def get_pending_requests():
    """Get list of pending registration requests."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, email, request_date 
                FROM registration_requests 
                WHERE status = 'pending'
                ORDER BY request_date DESC
            ''')
            requests = cursor.fetchall()
            
            return jsonify({
                'requests': [{
                    'id': r[0],
                    'username': r[1],
                    'email': r[2],
                    'request_date': r[3]
                } for r in requests]
            }), 200
            
    except Exception as e:
        app.logger.error(f"Error getting pending requests: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/approve-request/<int:request_id>', methods=['POST'])
@requires_admin
def approve_request(request_id):
    """Approve a registration request."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Get request details
            cursor.execute('SELECT username, password_hash, email FROM registration_requests WHERE id = ?', (request_id,))
            request_data = cursor.fetchone()
            
            if not request_data:
                return jsonify({'error': 'Request not found'}), 404
            
            # Create user account
            cursor.execute('''
                INSERT INTO users (username, password_hash, is_approved, status)
                VALUES (?, ?, ?, ?)
            ''', (request_data[0], request_data[1], True, 'active'))
            
            user_id = cursor.lastrowid
            
            # Create user's upload folder
            user_folder = os.path.join(UPLOAD_FOLDER, f'user_{user_id}')
            os.makedirs(user_folder, exist_ok=True)
            
            # Update request status
            cursor.execute('''
                UPDATE registration_requests 
                SET status = 'approved', 
                    admin_response_date = CURRENT_TIMESTAMP,
                    admin_notes = ?
                WHERE id = ?
            ''', (f'Approved by admin (user_id: {session["user_id"]})', request_id))
            
            log_audit(session['user_id'], 'APPROVE_REQUEST', f'Approved registration request for {request_data[0]}', request.remote_addr)
            
            return jsonify({'success': True}), 200
            
    except Exception as e:
        app.logger.error(f"Error approving request: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/reject-request/<int:request_id>', methods=['POST'])
@requires_admin
def reject_request(request_id):
    """Reject a registration request."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get request details
            cursor.execute('SELECT username FROM registration_requests WHERE id = ?', (request_id,))
            request_data = cursor.fetchone()
            
            if not request_data:
                return jsonify({'error': 'Request not found'}), 404
            
            # Update request status
            cursor.execute('''
                UPDATE registration_requests 
                SET status = 'rejected',
                    admin_response_date = CURRENT_TIMESTAMP,
                    admin_notes = ?
                WHERE id = ?
            ''', (f'Rejected by admin (user_id: {session["user_id"]})', request_id))
            
            log_audit(session['user_id'], 'REJECT_REQUEST', f'Rejected registration request for {request_data[0]}', request.remote_addr)
            
            return jsonify({'success': True})
            
    except Exception as e:
        app.logger.error(f"Error rejecting request: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/upload', methods=['POST'])
@requires_auth
def upload_file():
    """Handle file upload with user-specific folders."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    folder = request.form.get('folder', '')
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    try:
        # Validate file size (max 10MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        file_data = file.read()
        if len(file_data) > MAX_FILE_SIZE:
            return jsonify({'error': 'File too large (max 10MB)'}), 400
        
        # Get user's base folder
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        
        # Use specified subfolder or create date-based folder
        if folder and folder.strip():
            folder_name = folder.strip()
            if not is_safe_filename(folder_name):
                return jsonify({'error': 'Invalid folder name'}), 400
            folder_path = os.path.join(user_base_folder, folder_name)
        else:
            today = datetime.now().strftime('%Y-%m-%d')
            folder_path = os.path.join(user_base_folder, today)
            folder = today
            
        ensure_folder_exists(folder_path)
        
        # Generate secure filename
        timestamp = datetime.now().strftime('%H-%M-%S')
        filename = f'screenshot_{timestamp}.png'
        file_path = os.path.join(folder_path, filename)
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        log_audit(session['user_id'], 'UPLOAD', f'Uploaded file: {filename} to folder: {folder}', request.remote_addr)
        
        return jsonify({
            'success': True,
            'path': f'/image/user_{session["user_id"]}/{folder}/{filename}',
            'folder': folder,
            'filename': filename
        })
        
    except Exception as e:
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/image/<path:filename>')
@requires_auth
def serve_image(filename):
    """Serve image files with user access control."""
    try:
        # Extract user_id from path
        path_parts = filename.split('/')
        if not path_parts[0].startswith('user_'):
            return jsonify({'error': 'Invalid path'}), 400
        
        requested_user_id = int(path_parts[0].replace('user_', ''))
        
        # Check if user has access to this folder
        if requested_user_id != session['user_id']:
            # Allow admin to view all images
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],))
                user = cursor.fetchone()
                
                if not user or not user[0]:
                    log_audit(session['user_id'], 'ACCESS_DENIED', f'Attempted to access file: {filename}', request.remote_addr)
                    return jsonify({'error': 'Access denied'}), 403
        
        # Construct the full file path
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        # Verify the file exists and is within the uploads directory
        if not os.path.exists(file_path) or not os.path.commonprefix([os.path.abspath(file_path), os.path.abspath(UPLOAD_FOLDER)]) == os.path.abspath(UPLOAD_FOLDER):
            app.logger.error(f"File not found or access denied: {file_path}")
            return jsonify({'error': 'File not found'}), 404
        
        # Get the directory containing the file
        directory = os.path.dirname(file_path)
        # Get just the filename
        basename = os.path.basename(file_path)
        
        return send_from_directory(directory, basename)
        
    except Exception as e:
        app.logger.error(f"Error serving image: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/folder', methods=['POST'])
@requires_auth
def create_folder():
    """Create a new folder."""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Folder name is required'}), 400
        
        name = data['name'].strip()
        display_name = data.get('display_name', '').strip() or name
        
        if not name or not is_safe_filename(name):
            return jsonify({'error': 'Invalid folder name'}), 400
        
        # Get user's base folder
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        folder_path = os.path.join(user_base_folder, name)
        
        # Check if folder already exists
        if os.path.exists(folder_path):
            return jsonify({'error': 'Folder already exists'}), 400
        
        # Create the folder
        os.makedirs(folder_path)
        
        log_audit(session['user_id'], 'CREATE_FOLDER', f'Created folder: {name}', request.remote_addr)
        
        return jsonify({
            'success': True,
            'folder': {
                'name': name,
                'display_name': display_name,
                'path': f'user_{session["user_id"]}/{name}',
                'created': datetime.now().isoformat(),
                'modified': datetime.now().isoformat(),
                'is_permanent': False,
                'is_starred': False,
                'screenshots': []
            }
        })
        
    except Exception as e:
        app.logger.error(f"Error creating folder: {str(e)}")
        return jsonify({'error': 'Failed to create folder'}), 500

def get_folder_screenshots(folder_path):
    """Get list of screenshots in a folder."""
    screenshots = []
    if os.path.exists(folder_path):
        for item in os.listdir(folder_path):
            if item.endswith('.png'):
                file_path = os.path.join(folder_path, item)
                stats = os.stat(file_path)
                screenshot_info = {
                    'name': item,
                    'path': f'/image/{os.path.relpath(file_path, UPLOAD_FOLDER)}',
                    'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    'size': stats.st_size
                }
                screenshots.append(screenshot_info)
    return sorted(screenshots, key=lambda x: x['created'], reverse=True)

def ensure_folder_exists(folder_path):
    """Create folder if it doesn't exist."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

def get_folder_metadata_path(user_id):
    """Get the path to the user's folder metadata file."""
    return os.path.join(UPLOAD_FOLDER, f'user_{user_id}', '.folder_metadata.json')

def load_folder_metadata(user_id):
    """Load folder metadata for a user."""
    metadata_path = get_folder_metadata_path(user_id)
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            app.logger.error(f"Error loading folder metadata: {str(e)}")
    return {'starred_folders': []}

def save_folder_metadata(user_id, metadata):
    """Save folder metadata for a user."""
    metadata_path = get_folder_metadata_path(user_id)
    try:
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        return True
    except Exception as e:
        app.logger.error(f"Error saving folder metadata: {str(e)}")
        return False

@app.route('/folder/<folder_name>/star', methods=['POST'])
@requires_auth
def star_folder(folder_name):
    """Star a folder."""
    try:
        if not is_safe_filename(folder_name):
            return jsonify({'error': 'Invalid folder name'}), 400
            
        # Load current metadata
        metadata = load_folder_metadata(session['user_id'])
        starred_folders = metadata.get('starred_folders', [])
        
        # Add to starred folders if not already starred
        if folder_name not in starred_folders:
            starred_folders.append(folder_name)
            metadata['starred_folders'] = starred_folders
            
            # Save metadata
            if save_folder_metadata(session['user_id'], metadata):
                log_audit(session['user_id'], 'star_folder', f'Starred folder {folder_name}', request.remote_addr)
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Failed to save folder metadata'}), 500
        else:
            return jsonify({'error': 'Folder already starred'}), 400
            
    except Exception as e:
        app.logger.error(f"Error starring folder: {str(e)}")
        return jsonify({'error': 'Failed to star folder'}), 500

@app.route('/folder/<folder_name>/unstar', methods=['POST'])
@requires_auth
def unstar_folder(folder_name):
    """Unstar a folder."""
    try:
        if not is_safe_filename(folder_name):
            return jsonify({'error': 'Invalid folder name'}), 400
            
        # Load metadata
        metadata = load_folder_metadata(session['user_id'])
        starred_folders = metadata.get('starred_folders', [])
        
        # Remove from starred folders if starred
        if folder_name in starred_folders:
            starred_folders.remove(folder_name)
            metadata['starred_folders'] = starred_folders
            
            # Save metadata
            if save_folder_metadata(session['user_id'], metadata):
                log_audit(session['user_id'], 'unstar_folder', f'Unstarred folder {folder_name}', request.remote_addr)
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'Failed to save folder metadata'}), 500
        else:
            return jsonify({'error': 'Folder not starred'}), 400
            
    except Exception as e:
        app.logger.error(f"Error unstarring folder: {str(e)}")
        return jsonify({'error': 'Failed to unstar folder'}), 500

@app.route('/move_screenshot', methods=['POST'])
@requires_auth
def move_screenshot():
    """Move or copy a screenshot between folders."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        source_folder = data.get('source_folder')
        target_folder = data.get('target_folder')
        filename = data.get('filename')
        operation = data.get('operation', 'move')  # Default to move if not specified
        
        if not all([source_folder, target_folder, filename]):
            return jsonify({'error': 'Missing required fields'}), 400
            
        if not all(is_safe_filename(name) for name in [source_folder, target_folder, filename]):
            return jsonify({'error': 'Invalid folder name or filename'}), 400
            
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        
        # If source_folder is 'all', we need to find which folder contains the file
        if source_folder == 'all':
            actual_folder = None
            # Search through all folders for the file
            for root, dirs, files in os.walk(user_base_folder):
                if filename in files:
                    actual_folder = os.path.basename(root)
                    source_folder = actual_folder
                    break
            
            if actual_folder is None:
                return jsonify({'error': 'Source file not found'}), 404
        
        source_path = os.path.join(user_base_folder, source_folder, filename)
        target_path = os.path.join(user_base_folder, target_folder, filename)
        
        # Security check: ensure paths are within user's directory
        if not all(os.path.abspath(p).startswith(os.path.abspath(user_base_folder)) 
                  for p in [source_path, target_path]):
            return jsonify({'error': 'Access denied'}), 403
            
        # Ensure source file exists
        if not os.path.exists(source_path):
            return jsonify({'error': 'Source file not found'}), 404
            
        # Ensure target folder exists
        target_folder_path = os.path.join(user_base_folder, target_folder)
        if not os.path.exists(target_folder_path):
            os.makedirs(target_folder_path)
            
        # Check if target file already exists
        if os.path.exists(target_path):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(target_path):
                new_filename = f"{base}_{counter}{ext}"
                target_path = os.path.join(user_base_folder, target_folder, new_filename)
                counter += 1
                
        # Perform the operation
        if operation == 'move':
            shutil.move(source_path, target_path)
            action = 'move_screenshot'
            details = f'Moved {filename} from {source_folder} to {target_folder}'
        else:  # copy
            shutil.copy2(source_path, target_path)
            action = 'copy_screenshot'
            details = f'Copied {filename} from {source_folder} to {target_folder}'
            
        log_audit(session['user_id'], action, details, request.remote_addr)
        return jsonify({'success': True})
        
    except Exception as e:
        app.logger.error(f"Error in move_screenshot: {str(e)}")
        return jsonify({'error': 'Failed to process screenshot'}), 500

@app.route('/folders')
@requires_auth
def list_folders():
    """List all folders for the current user."""
    app.logger.debug(f"Folders request received from user_id: {session.get('user_id')}")
    try:
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        app.logger.debug(f"Looking for folders in: {user_base_folder}")
        
        # Create user folder if it doesn't exist
        if not os.path.exists(user_base_folder):
            app.logger.debug(f"Creating user folder: {user_base_folder}")
            os.makedirs(user_base_folder)
        
        # Load folder metadata
        metadata = load_folder_metadata(session['user_id'])
        starred_folders = metadata.get('starred_folders', [])
        app.logger.debug(f"Loaded metadata with starred folders: {starred_folders}")
        
        # Initialize folders list
        folders = []
        
        # Get all screenshots across all folders for the "All Screenshots" view
        all_screenshots = []
        for root, dirs, files in os.walk(user_base_folder):
            for file in files:
                if file.endswith('.png'):
                    file_path = os.path.join(root, file)
                    stats = os.stat(file_path)
                    screenshot_info = {
                        'name': file,
                        'path': f'/image/{os.path.relpath(file_path, UPLOAD_FOLDER)}',
                        'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                        'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        'size': stats.st_size,
                        'folder': os.path.basename(os.path.dirname(file_path))
                    }
                    all_screenshots.append(screenshot_info)
                    app.logger.debug(f"Found screenshot: {screenshot_info}")
        
        # Add "All Screenshots" folder first (it's permanent)
        all_screenshots_folder = {
            'name': 'all',
            'display_name': 'All Screenshots',
            'path': f'user_{session["user_id"]}',
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'is_permanent': True,
            'is_starred': False,
            'screenshots': sorted(all_screenshots, key=lambda x: x['created'], reverse=True)
        }
        folders.append(all_screenshots_folder)
        app.logger.debug(f"Added All Screenshots folder with {len(all_screenshots)} screenshots")
        
        # Get other folders
        for item in os.listdir(user_base_folder):
            if item.startswith('.'):  # Skip hidden files/folders
                continue
                
            item_path = os.path.join(user_base_folder, item)
            if os.path.isdir(item_path):
                # Get folder stats
                stats = os.stat(item_path)
                folder_info = {
                    'name': item,
                    'display_name': item,
                    'path': f'user_{session["user_id"]}/{item}',
                    'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                    'is_permanent': False,
                    'is_starred': item in starred_folders,
                    'screenshots': get_folder_screenshots(item_path)
                }
                folders.append(folder_info)
                app.logger.debug(f"Found folder: {folder_info}")
        
        response_data = {
            'folders': folders,
            'default_folder': 'all'
        }
        app.logger.debug(f"Returning folders response: {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f"Error listing folders: {str(e)}")
        return jsonify({'error': 'Failed to list folders'}), 500

@app.route('/folder/<folder_name>')
@requires_auth
def get_folder(folder_name):
    """Get contents of a specific folder."""
    try:
        if not is_safe_filename(folder_name):
            return jsonify({'error': 'Invalid folder name'}), 400
            
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        folder_path = os.path.join(user_base_folder, folder_name)
        
        if not os.path.exists(folder_path):
            return jsonify({'error': 'Folder not found'}), 404
            
        stats = os.stat(folder_path)
        folder_info = {
            'name': folder_name,
            'display_name': folder_name,
            'path': f'user_{session["user_id"]}/{folder_name}',
            'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
            'is_permanent': False,
            'is_starred': False,
            'screenshots': get_folder_screenshots(folder_path)
        }
        
        return jsonify(folder_info)
        
    except Exception as e:
        app.logger.error(f"Error getting folder: {str(e)}")
        return jsonify({'error': 'Failed to get folder'}), 500

@app.route('/folder/<folder_name>', methods=['DELETE'])
@requires_auth
def delete_folder(folder_name):
    """Delete a folder and its contents."""
    try:
        if not is_safe_filename(folder_name):
            return jsonify({'error': 'Invalid folder name'}), 400
            
        # Don't allow deletion of permanent folders
        if folder_name == 'all':
            return jsonify({'error': 'Cannot delete permanent folders'}), 403
            
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        folder_path = os.path.join(user_base_folder, folder_name)
        
        # Security check: ensure folder is within user's directory
        if not os.path.abspath(folder_path).startswith(os.path.abspath(user_base_folder)):
            return jsonify({'error': 'Access denied'}), 403
            
        if not os.path.exists(folder_path):
            return jsonify({'error': 'Folder not found'}), 404
            
        # Remove folder from starred folders if it was starred
        metadata = load_folder_metadata(session['user_id'])
        if folder_name in metadata.get('starred_folders', []):
            metadata['starred_folders'].remove(folder_name)
            save_folder_metadata(session['user_id'], metadata)
            
        # Handle Windows file permissions
        def handle_remove_readonly(func, path, exc):
            excvalue = exc[1]
            if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno == errno.EACCES:
                # Change file permissions to allow deletion
                os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                func(path)  # Try again
            else:
                raise excvalue
            
        # Delete the folder and all its contents with error handler
        shutil.rmtree(folder_path, onerror=handle_remove_readonly)
        
        log_audit(session['user_id'], 'delete_folder', f'Deleted folder: {folder_name}', request.remote_addr)
        return jsonify({'success': True})
        
    except Exception as e:
        app.logger.error(f"Error deleting folder: {str(e)}")
        return jsonify({'error': 'Failed to delete folder'}), 500

@app.route('/admin/users', methods=['GET'])
@requires_auth
@requires_admin
def get_users():
    """Get list of all users."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get table info
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Build query based on available columns
            select_columns = ['id', 'username']
            if 'is_admin' in columns:
                select_columns.append('is_admin')
            if 'is_approved' in columns:
                select_columns.append('is_approved')
            if 'status' in columns:
                select_columns.append('status')
            if 'last_login' in columns:
                select_columns.append('last_login')
            if 'email' in columns:
                select_columns.append('email')
            if 'created_at' in columns:
                select_columns.append('created_at')
            if 'updated_at' in columns:
                select_columns.append('updated_at')
            
            query = f'SELECT {", ".join(select_columns)} FROM users ORDER BY id DESC'
            cursor.execute(query)
            users = cursor.fetchall()
            
            # Convert to list of dicts with default values for missing columns
            result = []
            for user in users:
                user_dict = {
                    'id': user[0],
                    'username': user[1],
                    'is_admin': user[2] if len(user) > 2 and 'is_admin' in columns else False,
                    'is_approved': user[3] if len(user) > 3 and 'is_approved' in columns else False,
                    'status': user[4] if len(user) > 4 and 'status' in columns else 'active',
                    'last_login': user[5] if len(user) > 5 and 'last_login' in columns else None,
                    'email': user[6] if len(user) > 6 and 'email' in columns else None,
                    'created_at': user[7] if len(user) > 7 and 'created_at' in columns else None,
                    'updated_at': user[8] if len(user) > 8 and 'updated_at' in columns else None
                }
                result.append(user_dict)
            
            return jsonify({'users': result}), 200
            
    except Exception as e:
        app.logger.error(f"Error getting users: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/users/<int:user_id>/toggle-access', methods=['POST'])
@requires_auth
@requires_admin
def toggle_user_access(user_id):
    """Toggle user's access (active/disabled)."""
    try:
        # Don't allow modifying own account
        if user_id == session['user_id']:
            return jsonify({'error': 'Cannot modify own account'}), 403
            
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Check if updated_at column exists
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            has_updated_at = 'updated_at' in columns
            
            # Get current user status
            cursor.execute('SELECT status, username FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
                
            new_status = 'disabled' if user[0] == 'active' else 'active'
            
            # Update user status
            if has_updated_at:
                cursor.execute('''
                    UPDATE users 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_status, user_id))
            else:
                cursor.execute('''
                    UPDATE users 
                    SET status = ?
                    WHERE id = ?
                ''', (new_status, user_id))
            
            log_audit(
                session['user_id'],
                'toggle_user_access',
                f"Changed user {user[1]} status to {new_status}",
                request.remote_addr
            )
            
            return jsonify({
                'success': True,
                'new_status': new_status
            })
            
    except Exception as e:
        app.logger.error(f"Error toggling user access: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def update_schema():
    """Update database schema with any missing columns."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get current columns
            cursor.execute("PRAGMA table_info(users)")
            existing_columns = {col[1] for col in cursor.fetchall()}
            
            # Add missing columns one by one without default values
            if 'email' not in existing_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN email TEXT')
                
            if 'status' not in existing_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN status TEXT')
                cursor.execute('UPDATE users SET status = "active" WHERE status IS NULL')
                
            if 'last_login' not in existing_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN last_login TIMESTAMP')
                
            if 'created_at' not in existing_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN created_at TIMESTAMP')
                cursor.execute('UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL')
                
            if 'updated_at' not in existing_columns:
                cursor.execute('ALTER TABLE users ADD COLUMN updated_at TIMESTAMP')
                cursor.execute('UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL')
            
            conn.commit()
            app.logger.info("Schema update completed successfully")
            
    except Exception as e:
        app.logger.error(f"Error updating schema: {str(e)}")

# Initialize database on startup
with app.app_context():
    init_db()
    update_schema()

# Basic routes for serving pages
@app.route('/')
def index():
    """Serve the login page."""
    return send_from_directory('static', 'login.html')

@app.route('/app')
@requires_auth
def serve_app():
    """Serve the main application page."""
    return send_from_directory('static', 'index.html')

@app.route('/admin')
@requires_admin
def serve_admin_panel():
    """Serve the admin panel."""
    return send_from_directory('static', 'admin.html')

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon."""
    return send_from_directory('static', 'favicon.ico')

@app.route('/lockdown-install.js')
def serve_lockdown_install():
    """Serve the lockdown installation script."""
    return send_from_directory('static', 'lockdown-install.js')

@app.route('/lockdown-config.js')
def serve_lockdown_config():
    """Serve the lockdown configuration script."""
    return send_from_directory('static', 'lockdown-config.js')

@app.route('/app.js')
def serve_app_js():
    """Serve the main application JavaScript."""
    return send_from_directory('static', 'app.js')

@app.route('/logout')
def logout():
    """Handle user logout."""
    session.clear()
    return jsonify({'success': True})

@app.route('/check-auth')
def check_auth():
    """Check if user is authenticated."""
    return jsonify({'authenticated': 'user_id' in session})

@app.route('/delete/<folder_name>/<filename>', methods=['DELETE'])
@requires_auth
def delete_screenshot(folder_name, filename):
    """Delete a screenshot from a folder."""
    try:
        if not is_safe_filename(filename) or not is_safe_filename(folder_name):
            return jsonify({'error': 'Invalid filename or folder name'}), 400
            
        user_base_folder = os.path.join(UPLOAD_FOLDER, f'user_{session["user_id"]}')
        
        # If folder_name is 'all', we need to find which folder contains the file
        if folder_name == 'all':
            actual_folder = None
            # Search through all folders for the file
            for root, dirs, files in os.walk(user_base_folder):
                if filename in files:
                    actual_folder = os.path.basename(root)
                    folder_name = actual_folder
                    break
            
            if actual_folder is None:
                return jsonify({'error': 'File not found'}), 404
        
        file_path = os.path.join(user_base_folder, folder_name, filename)
        
        # Security check: ensure file is within user's directory
        if not os.path.abspath(file_path).startswith(os.path.abspath(user_base_folder)):
            return jsonify({'error': 'Access denied'}), 403
            
        if os.path.exists(file_path):
            os.remove(file_path)
            log_audit(session['user_id'], 'delete_screenshot', f'Deleted {filename} from {folder_name}', request.remote_addr)
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting screenshot: {str(e)}")
        return jsonify({'error': 'Failed to delete screenshot'}), 500

@app.route('/api/admin/statistics')
@requires_admin
def get_admin_statistics():
    """Get system-wide statistics for admin panel."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get user statistics
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_users
                FROM users
            ''')
            user_stats = cursor.fetchone()
            
            # Calculate total storage used
            total_storage = 0
            total_screenshots = 0
            for root, _, files in os.walk(UPLOAD_FOLDER):
                for file in files:
                    if file.endswith('.png'):
                        total_screenshots += 1
                        total_storage += os.path.getsize(os.path.join(root, file))
            
            return jsonify({
                'totalUsers': user_stats[0] or 0,
                'activeUsers': user_stats[1] or 0,
                'totalScreenshots': total_screenshots,
                'storageUsed': total_storage
            })
            
    except Exception as e:
        app.logger.error(f"Error getting admin statistics: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/users')
@requires_admin
def get_admin_user_list():
    """Get list of all users for admin panel."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    id,
                    username,
                    email,
                    status,
                    last_login,
                    is_admin
                FROM users
                ORDER BY username
            ''')
            
            users = []
            for row in cursor.fetchall():
                # Calculate storage used by user
                user_folder = os.path.join(UPLOAD_FOLDER, f'user_{row[0]}')
                storage_used = 0
                if os.path.exists(user_folder):
                    for root, _, files in os.walk(user_folder):
                        storage_used += sum(os.path.getsize(os.path.join(root, name)) for name in files if name.endswith('.png'))
                
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'status': row[3],
                    'last_login': row[4],
                    'is_admin': bool(row[5]),
                    'storage_used': storage_used
                })
            
            return jsonify(users)
            
    except Exception as e:
        app.logger.error(f"Error getting user list: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@requires_admin
def update_user_status(user_id):
    """Update user status (active/disabled)."""
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'error': 'Status is required'}), 400
            
        status = data['status'].lower()
        if status not in ['active', 'disabled']:
            return jsonify({'error': 'Invalid status'}), 400
            
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Don't allow disabling the last admin
            if status == 'disabled':
                cursor.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                if user and user[0]:  # If user is admin
                    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1 AND status = "active"')
                    admin_count = cursor.fetchone()[0]
                    if admin_count <= 1:
                        return jsonify({'error': 'Cannot disable the last active admin'}), 400
            
            cursor.execute('UPDATE users SET status = ? WHERE id = ?', (status, user_id))
            
            if cursor.rowcount == 0:
                return jsonify({'error': 'User not found'}), 404
                
            log_audit(session['user_id'], 'UPDATE_USER_STATUS', f'Updated user {user_id} status to {status}', request.remote_addr)
            return jsonify({'success': True})
            
    except Exception as e:
        app.logger.error(f"Error updating user status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/registration-requests')
@requires_admin
def get_registration_requests():
    """Get list of pending registration requests."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, username, email, request_date
                FROM registration_requests
                WHERE status = 'pending'
                ORDER BY request_date DESC
            ''')
            
            requests = []
            for row in cursor.fetchall():
                requests.append({
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'requestDate': row[3]
                })
                
            return jsonify(requests)
            
    except Exception as e:
        app.logger.error(f"Error getting registration requests: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/registration-requests/<int:request_id>/approve', methods=['POST'])
@requires_admin
def approve_registration_request(request_id):
    """Approve a registration request."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get request details
            cursor.execute('''
                SELECT username, password_hash, email 
                FROM registration_requests 
                WHERE id = ? AND status = 'pending'
            ''', (request_id,))
            
            request_data = cursor.fetchone()
            if not request_data:
                return jsonify({'error': 'Request not found or already processed'}), 404
            
            # Create user account (always as non-admin)
            cursor.execute('''
                INSERT INTO users (username, password_hash, email, is_admin, is_approved, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (request_data[0], request_data[1], request_data[2], False, True, 'active'))
            
            user_id = cursor.lastrowid
            
            # Create user's upload folder
            user_folder = os.path.join(UPLOAD_FOLDER, f'user_{user_id}')
            os.makedirs(user_folder, exist_ok=True)
            
            # Update request status
            cursor.execute('''
                UPDATE registration_requests 
                SET status = 'approved',
                    admin_response_date = CURRENT_TIMESTAMP,
                    admin_notes = ?
                WHERE id = ?
            ''', (f'Approved by admin (user_id: {session["user_id"]})', request_id))
            
            conn.commit()
            
            log_audit(session['user_id'], 'APPROVE_REGISTRATION',
                     f'Approved registration request for {request_data[0]}',
                     request.remote_addr)
            
            return jsonify({'success': True})
            
    except Exception as e:
        app.logger.error(f"Error approving registration request: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/admin/registration-requests/<int:request_id>/reject', methods=['POST'])
@requires_admin
def reject_registration_request(request_id):
    """Reject a registration request."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get request details
            cursor.execute('SELECT username FROM registration_requests WHERE id = ? AND status = "pending"',
                         (request_id,))
            request_data = cursor.fetchone()
            
            if not request_data:
                return jsonify({'error': 'Request not found or already processed'}), 404
            
            # Update request status
            cursor.execute('''
                UPDATE registration_requests 
                SET status = 'rejected',
                    admin_response_date = CURRENT_TIMESTAMP,
                    admin_notes = ?
                WHERE id = ?
            ''', (f'Rejected by admin (user_id: {session["user_id"]})', request_id))
            
            conn.commit()
            
            log_audit(session['user_id'], 'REJECT_REGISTRATION',
                     f'Rejected registration request for {request_data[0]}',
                     request.remote_addr)
            
            return jsonify({'success': True})
            
    except Exception as e:
        app.logger.error(f"Error rejecting registration request: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Add security headers to all responses
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Remove strict security headers that might cause issues
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    # Update CSP to be more permissive
    response.headers['Content-Security-Policy'] = (
        "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "img-src * data: blob: 'unsafe-inline'; "
        "style-src * 'unsafe-inline'; "
        "script-src * 'unsafe-inline' 'unsafe-eval'; "
        "font-src * data:; "
        "connect-src *"
    )
    
    return response

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Get host from environment variable or default to '0.0.0.0'
    host = os.environ.get('HOST', '0.0.0.0')
    
    # In production, use proper SSL certificates
    if ENVIRONMENT == 'production':
        # Use proper SSL certificates in production
        if not SSL_CERT or not SSL_KEY:
            raise ValueError('SSL_CERT and SSL_KEY environment variables must be set in production')
        
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(SSL_CERT, SSL_KEY)
        app.run(host=host, port=port, ssl_context=context)
    else:
        # Development mode with self-signed certificates
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain('cert.pem', 'key.pem')
        app.run(host=host, port=port, ssl_context=context, debug=True) 

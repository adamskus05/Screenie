from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import check_password_hash
import logging
import os

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the static directory exists
os.makedirs('static', exist_ok=True)

@app.route('/')
def index():
    """Serve the main application."""
    return send_from_directory('static', 'index.html')

@app.route('/app')
def serve_app():
    """Serve the application interface."""
    return send_from_directory('static', 'app.html')

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Hardcoded test user
        if username.lower() == 'operator_1337' and password == 'ITgwXqkIl2co6RsgAvBhvQ':
            session['user_id'] = 1
            session.permanent = True
            
            response = jsonify({
                'success': True,
                'user_id': 1
            })
            
            if request.headers.get('Origin') == 'app://screenie':
                response.headers['Set-Cookie'] = f'session={session.sid}; SameSite=None; Secure; Path=/'
            
            return response
        
        return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon."""
    return send_from_directory('static', 'favicon.ico')

@app.route('/app.js')
def serve_app_js():
    """Serve the application JavaScript."""
    return send_from_directory('static', 'app.js')

@app.route('/lockdown-install.js')
def serve_lockdown_install():
    """Serve the lockdown installation script."""
    return send_from_directory('static', 'lockdown-install.js')

@app.route('/lockdown-config.js')
def serve_lockdown_config():
    """Serve the lockdown configuration."""
    return send_from_directory('static', 'lockdown-config.js')

if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Get host from environment variable or use default
    host = os.environ.get('HOST', '0.0.0.0')
    
    # Configure server name
    app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME', 'screenie.space')
    
    # Enable HTTPS redirect
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # Run the app
    app.run(
        host=host,
        port=port,
        debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    ) 
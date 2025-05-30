from flask import Flask, request, jsonify, session
from werkzeug.security import check_password_hash
import logging
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev')

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

if __name__ == '__main__':
    app.run(debug=True) 
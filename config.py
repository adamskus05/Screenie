import os
import secrets

# Security configuration
DEBUG = True
TESTING = False
SECRET_KEY = secrets.token_hex(32)
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
SESSION_COOKIE_SECURE = True  # Enforce HTTPS for cookies
PREFERRED_URL_SCHEME = 'https'  # Use HTTPS by default 
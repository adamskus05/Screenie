import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the database path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
DB_FILE = os.path.join(DATA_DIR, 'users.db')

def create_admin(username, password, email):
    """Create an admin user."""
    try:
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        logger.info(f"Database directory ensured: {os.path.dirname(DB_FILE)}")
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                logger.warning(f"Admin user '{username}' already exists!")
                return False
            
            # Create user
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
                username,
                generate_password_hash(password),
                email,
                True,  # is_admin
                True,  # is_approved
                'active',
                datetime.now(),
                datetime.now()
            ))
            
            logger.info(f"Admin user '{username}' created successfully!")
            return True
            
    except sqlite3.IntegrityError:
        logger.error(f"Error: Username '{username}' already exists!")
        return False
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        return False

if __name__ == '__main__':
    try:
        # Check if we're getting piped input
        if not sys.stdin.isatty():
            # Read input from pipe
            lines = sys.stdin.readlines()
            if len(lines) >= 4:
                username = lines[0].strip()
                password = lines[1].strip()
                confirm_password = lines[2].strip()
                email = lines[3].strip()
                
                logger.info(f"Attempting to create admin user: {username}")
                
                if password != confirm_password:
                    logger.error("Error: Passwords don't match!")
                    sys.exit(1)
                    
                if create_admin(username, password, email):
                    sys.exit(0)
                else:
                    sys.exit(1)
            else:
                logger.error("Error: Insufficient input provided")
                sys.exit(1)
        else:
            # Interactive mode
            print("Create Admin User")
            print("-" * 20)
            username = input("Username: ")
            password = getpass.getpass("Password: ")
            confirm_password = getpass.getpass("Confirm Password: ")
            
            if password != confirm_password:
                logger.error("Error: Passwords don't match!")
                sys.exit(1)
                
            email = input("Email: ")
            
            if create_admin(username, password, email):
                sys.exit(0)
            else:
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1) 
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
DB_FILE = os.path.join(DATA_DIR, 'users.db')

def create_admin(username, password, email):
    """Create an admin user."""
    try:
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
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
            
            print(f"Admin user '{username}' created successfully!")
            
    except sqlite3.IntegrityError:
        print(f"Error: Username '{username}' already exists!")
    except Exception as e:
        print(f"Error creating admin user: {str(e)}")

if __name__ == '__main__':
    import getpass
    
    print("Create Admin User")
    print("-" * 20)
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    confirm_password = getpass.getpass("Confirm Password: ")
    
    if password != confirm_password:
        print("Error: Passwords don't match!")
        exit(1)
        
    email = input("Email: ")
    
    create_admin(username, password, email) 
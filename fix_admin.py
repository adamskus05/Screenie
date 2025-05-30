import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
DB_FILE = 'users.db'

def fix_admin():
    """Fix the admin account."""
    try:
        # Connect to database
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Delete existing admin if exists
            cursor.execute('DELETE FROM users WHERE username = ?', ('OPERATOR_1337',))
            
            # Create new admin user
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
            
            print("Admin user recreated successfully!")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    fix_admin() 
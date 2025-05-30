import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
DB_FILE = 'users.db'

try:
    # Connect to database
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                is_admin BOOLEAN DEFAULT 0,
                is_approved BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
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
        
        print("Admin user created successfully!")
        
        # Verify the user was created
        cursor.execute('SELECT id, username, is_admin FROM users WHERE username = ?', ('OPERATOR_1337',))
        user = cursor.fetchone()
        if user:
            print(f"Verified admin user exists: ID={user[0]}, Username={user[1]}, Is Admin={user[2]}")
        else:
            print("ERROR: Failed to verify admin user creation")

except Exception as e:
    print(f"ERROR: {str(e)}")
    sys.exit(1) 
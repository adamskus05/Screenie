import sqlite3
import os
import sys
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = '/opt/render/project/src/data'
DB_FILE = os.path.join(DATA_DIR, 'users.db')
SCHEMA_FILE = os.path.join(BASE_DIR, 'schema.sql')

print(f"Current directory: {os.getcwd()}")
print(f"Base directory: {BASE_DIR}")
print(f"Data directory: {DATA_DIR}")
print(f"Database file: {DB_FILE}")
print(f"Schema file: {SCHEMA_FILE}")

try:
    # Ensure directories exist
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"Created/verified data directory: {DATA_DIR}")

    # Initialize database with schema first
    print("Initializing database...")
    with sqlite3.connect(DB_FILE) as conn:
        print(f"Connected to database: {DB_FILE}")
        
        # Read and execute schema
        if os.path.exists(SCHEMA_FILE):
            print(f"Found schema file: {SCHEMA_FILE}")
            with open(SCHEMA_FILE, 'r') as f:
                schema_content = f.read()
                print("Read schema content")
                conn.executescript(schema_content)
                print("Executed schema")
        else:
            print(f"ERROR: Schema file not found at {SCHEMA_FILE}")
            sys.exit(1)

        # Create admin user
        cursor = conn.cursor()
        
        # Check if admin already exists
        cursor.execute('SELECT id FROM users WHERE username = ?', ("OPERATOR_1337",))
        existing_user = cursor.fetchone()
        
        if existing_user is None:
            print("Creating admin user...")
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
                "OPERATOR_1337",
                generate_password_hash("ITgwXqkIl2co6RsgAvBhvQ"),
                "admin@example.com",
                True,  # is_admin
                True,  # is_approved
                'active',
                datetime.now(),
                datetime.now()
            ))
            conn.commit()
            print("Admin user created successfully!")
            
            # Verify the user was created
            cursor.execute('SELECT id, username, is_admin FROM users WHERE username = ?', ("OPERATOR_1337",))
            user = cursor.fetchone()
            if user:
                print(f"Verified admin user exists: ID={user[0]}, Username={user[1]}, Is Admin={user[2]}")
            else:
                print("ERROR: Failed to verify admin user creation")
        else:
            print(f"Admin user already exists with ID: {existing_user[0]}")

except Exception as e:
    print(f"ERROR: {str(e)}")
    sys.exit(1) 
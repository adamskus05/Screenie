import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
DATA_DIR = '/opt/render/project/src/data'
DB_FILE = os.path.join(DATA_DIR, 'users.db')
SCHEMA_FILE = 'schema.sql'

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize database with schema first
print("Initializing database...")
with sqlite3.connect(DB_FILE) as conn:
    with open(SCHEMA_FILE, 'r') as f:
        conn.executescript(f.read())
    print("Schema initialized")

    # Create admin user
    cursor = conn.cursor()
    
    # Check if admin already exists
    cursor.execute('SELECT id FROM users WHERE username = ?', ("OPERATOR_1337",))
    if cursor.fetchone() is None:
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
    else:
        print("Admin user already exists") 
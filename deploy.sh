#!/bin/bash

# Set up environment variables
export DATA_DIR=/opt/render/project/data
export UPLOAD_FOLDER=$DATA_DIR/uploads
export DB_FILE=$DATA_DIR/users.db

# Create necessary directories
mkdir -p $DATA_DIR
mkdir -p $UPLOAD_FOLDER

# Set proper permissions for directories
chmod 755 $DATA_DIR
chmod 755 $UPLOAD_FOLDER

# If database exists, ensure it's readable by the application
if [ -f "$DB_FILE" ]; then
    echo "Database exists, ensuring proper permissions..."
    chmod 600 "$DB_FILE"
fi

# Initialize database and handle user creation
python3 -c "
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

DB_FILE = os.environ['DB_FILE']
db_exists = os.path.exists(DB_FILE)

try:
    # Create new database connection
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Check if users table exists
        cursor.execute(\"\"\"
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='users'
        \"\"\")
        table_exists = cursor.fetchone() is not None
        
        # If table doesn't exist, create schema
        if not table_exists:
            print('Creating database schema...')
            with open('schema.sql', 'r') as f:
                conn.executescript(f.read())
            print('Schema created successfully')
        
        # Check if any users exist
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        
        # Only create admin if no users exist
        if user_count == 0:
            print('No users found. Creating default admin...')
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
            print('Default admin user created successfully')
        else:
            print(f'Database already has {user_count} users. Skipping admin creation.')
except Exception as e:
    print(f'Error during database initialization: {e}')
    raise
"

# Start the server
exec gunicorn server:app 
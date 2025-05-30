#!/bin/bash

# Set up environment variables
export DATA_DIR=/opt/render/project/data
export UPLOAD_FOLDER=$DATA_DIR/uploads
export DB_FILE=$DATA_DIR/users.db

# Create necessary directories
mkdir -p $DATA_DIR
mkdir -p $UPLOAD_FOLDER

# Set proper permissions
chmod 755 $DATA_DIR
chmod 755 $UPLOAD_FOLDER

# Initialize database only if it doesn't exist AND is empty
if [ ! -f "$DB_FILE" ] || [ ! -s "$DB_FILE" ]; then
    echo "Database doesn't exist or is empty. Initializing..."
    python3 -c "
import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_FILE = os.environ['DB_FILE']

# Create new database connection
with sqlite3.connect(DB_FILE) as conn:
    # Read and execute schema
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    
    # Check if any users exist
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    user_count = cursor.fetchone()[0]
    
    # Only create admin if no users exist
    if user_count == 0:
        print('No users found. Creating default admin...')
        cursor.execute('''
            INSERT INTO users (username, password_hash, is_admin, is_approved, status)
            VALUES (?, ?, 1, 1, 'active')
        ''', ('OPERATOR_1337', generate_password_hash('ITgwXqkIl2co6RsgAvBhvQ')))
        conn.commit()
        print('Default admin user created')
    else:
        print(f'Database already has {user_count} users. Skipping admin creation.')
"
fi

# Start the server
exec gunicorn server:app 
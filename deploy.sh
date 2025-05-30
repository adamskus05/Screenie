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

# Initialize database only if it doesn't exist
if [ ! -f "$DB_FILE" ]; then
    echo "Initializing database..."
    python3 -c "
import sqlite3
import os

DB_FILE = os.environ['DB_FILE']
with sqlite3.connect(DB_FILE) as conn:
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    
    # Create default admin user only if no admin exists
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    if cursor.fetchone()[0] == 0:
        from werkzeug.security import generate_password_hash
        cursor.execute('''
            INSERT INTO users (username, password_hash, is_admin, is_approved, status)
            VALUES (?, ?, 1, 1, 'active')
        ''', ('OPERATOR_1337', generate_password_hash('ITgwXqkIl2co6RsgAvBhvQ')))
        conn.commit()
"
fi

# Start the server
exec gunicorn server:app 
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

# Get the database path
DATA_DIR = '/opt/render/project/src/data'
DB_FILE = os.path.join(DATA_DIR, 'users.db')

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)

# Connect to database
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Create admin user
username = "OPERATOR_1337"
password = "ITgwXqkIl2co6RsgAvBhvQ"
email = "admin@example.com"  # Change this to your email

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

conn.commit()
conn.close()
print("Admin user created successfully!") 
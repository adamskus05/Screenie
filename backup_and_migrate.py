import sqlite3
import os

def backup_and_migrate():
    # Paths
    DB_FILE = 'users.db'
    BACKUP_FILE = 'users_backup.db'
    SCHEMA_FILE = 'schema.sql'
    
    # Backup existing users if database exists
    existing_users = []
    if os.path.exists(DB_FILE):
        try:
            # Connect to existing database
            with sqlite3.connect(DB_FILE) as old_conn:
                cursor = old_conn.cursor()
                # Get existing users
                cursor.execute('SELECT id, username, password_hash, is_admin, is_approved, status FROM users')
                existing_users = cursor.fetchall()
        except Exception as e:
            print(f"Error backing up users: {e}")
            return False
    
    # Rename old database
    if os.path.exists(DB_FILE):
        try:
            if os.path.exists(BACKUP_FILE):
                os.remove(BACKUP_FILE)
            os.rename(DB_FILE, BACKUP_FILE)
            print(f"Backed up existing database to {BACKUP_FILE}")
        except Exception as e:
            print(f"Error backing up database: {e}")
            return False
    
    # Create new database with updated schema
    try:
        with sqlite3.connect(DB_FILE) as new_conn:
            with open(SCHEMA_FILE, 'r') as f:
                new_conn.executescript(f.read())
            
            # Restore users with new schema
            if existing_users:
                cursor = new_conn.cursor()
                for user in existing_users:
                    cursor.execute('''
                        INSERT INTO users 
                        (id, username, password_hash, is_admin, is_approved, status, email)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (user[0], user[1], user[2], user[3], user[4], user[5], None))
                new_conn.commit()
                print(f"Restored {len(existing_users)} users to new database")
        
        print("Database migration completed successfully")
        return True
        
    except Exception as e:
        print(f"Error creating new database: {e}")
        # Try to restore backup if something went wrong
        if os.path.exists(BACKUP_FILE):
            try:
                if os.path.exists(DB_FILE):
                    os.remove(DB_FILE)
                os.rename(BACKUP_FILE, DB_FILE)
                print("Restored original database due to error")
            except:
                print("ERROR: Could not restore original database!")
        return False

if __name__ == '__main__':
    backup_and_migrate() 
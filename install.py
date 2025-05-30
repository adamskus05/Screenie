import os
import sys
import subprocess
import sqlite3
import secrets
from pathlib import Path
import shutil

def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 7):
        print("Error: Python 3.7 or higher is required")
        sys.exit(1)

def install_requirements():
    """Install required packages."""
    print("Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except subprocess.CalledProcessError:
        print("Error: Failed to install required packages")
        sys.exit(1)

def setup_database():
    """Set up the SQLite database."""
    print("Setting up database...")
    if not os.path.exists('schema.sql'):
        print("Error: schema.sql not found")
        sys.exit(1)

    try:
        with sqlite3.connect('users.db') as conn:
            with open('schema.sql', 'r') as f:
                conn.executescript(f.read())
        print("Database setup complete")
    except Exception as e:
        print(f"Error setting up database: {e}")
        sys.exit(1)

def create_directories():
    """Create necessary directories."""
    print("Creating directories...")
    directories = ['uploads', 'static', 'logs']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def create_config():
    """Create configuration file."""
    print("Creating configuration...")
    config = {
        'SECRET_KEY': secrets.token_hex(32),
        'UPLOAD_FOLDER': 'uploads',
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024
    }
    
    with open('config.py', 'w') as f:
        for key, value in config.items():
            if isinstance(value, str):
                f.write(f'{key} = "{value}"\n')
            else:
                f.write(f'{key} = {value}\n')

def setup_ssl():
    """Set up SSL certificates."""
    print("Setting up SSL certificates...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "pyopenssl"
        ])
        from OpenSSL import crypto
        
        # Generate key
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)
        
        # Generate certificate
        cert = crypto.X509()
        cert.get_subject().CN = "localhost"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for one year
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha256')
        
        # Save certificate and private key
        with open("cert.pem", "wb") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        with open("key.pem", "wb") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
            
    except Exception as e:
        print(f"Warning: Failed to set up SSL certificates: {e}")
        print("The application will fall back to HTTP")

def create_startup_scripts():
    """Create startup scripts for different platforms."""
    print("Creating startup scripts...")
    
    # Windows batch script
    with open('start.bat', 'w') as f:
        f.write('@echo off\n')
        f.write('echo Starting Screenie Server...\n')
        f.write(f'"{sys.executable}" server.py\n')
        f.write('pause\n')
    
    # Unix shell script
    with open('start.sh', 'w') as f:
        f.write('#!/bin/bash\n')
        f.write('echo "Starting Screenie Server..."\n')
        f.write(f'python3 server.py\n')
    
    # Make shell script executable on Unix
    if os.name != 'nt':
        os.chmod('start.sh', 0o755)

def main():
    """Main installation function."""
    print("=== Screenie Installation ===")
    
    # Check Python version
    check_python_version()
    
    # Install requirements
    install_requirements()
    
    # Create directories
    create_directories()
    
    # Set up database
    setup_database()
    
    # Create configuration
    create_config()
    
    # Set up SSL
    setup_ssl()
    
    # Create startup scripts
    create_startup_scripts()
    
    print("\nInstallation complete!")
    print("\nTo start the server:")
    if os.name == 'nt':
        print("1. Double-click start.bat")
    else:
        print("1. Open terminal in this directory")
        print("2. Run: ./start.sh")
    print("\nThen open your browser and go to:")
    print("https://localhost:5000")
    
    print("\nNote: On first run, you'll need to create an admin account.")

if __name__ == "__main__":
    main() 
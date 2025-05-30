import os
import zipfile
import sys
from datetime import datetime

def create_package():
    """Create a distributable package of the application."""
    print("Creating Screenie distribution package...")
    
    # Files to include
    required_files = [
        'server.py',
        'screenshot_app.py',
        'install.py',
        'requirements.txt',
        'schema.sql',
        'README.md'
    ]
    
    # Directories to include
    required_dirs = [
        'static'
    ]
    
    # Verify all required files exist
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print("Error: Missing required files:")
        for f in missing_files:
            print(f"  - {f}")
        sys.exit(1)
    
    # Verify all required directories exist
    missing_dirs = [d for d in required_dirs if not os.path.exists(d)]
    if missing_dirs:
        print("Error: Missing required directories:")
        for d in missing_dirs:
            print(f"  - {d}")
        sys.exit(1)
    
    # Create version-stamped filename
    version = datetime.now().strftime("%Y%m%d")
    zip_filename = f'screenie_v{version}.zip'
    
    # Create ZIP file
    print(f"\nCreating {zip_filename}...")
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add individual files
        for file in required_files:
            print(f"Adding {file}")
            zipf.write(file)
        
        # Add directories
        for dir_name in required_dirs:
            for root, dirs, files in os.walk(dir_name):
                for file in files:
                    file_path = os.path.join(root, file)
                    print(f"Adding {file_path}")
                    zipf.write(file_path)
    
    print("\nPackage created successfully!")
    print(f"You can find the package at: {os.path.abspath(zip_filename)}")
    print("\nTo share with friends:")
    print("1. Send them the ZIP file")
    print("2. Tell them to:")
    print("   a. Install Python 3.7 or higher")
    print("   b. Extract the ZIP file")
    print("   c. Run: python install.py")
    print("   d. Follow the instructions in README.md")

if __name__ == "__main__":
    create_package() 
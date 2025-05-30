# Screenie - Screenshot Management Tool

Screenie is a secure, multi-user screenshot management tool that allows you to capture, organize, and share screenshots easily.

## Prerequisites

1. Python 3.7 or higher
2. pip (Python package installer)

## Installation

1. Download and extract the Screenie package
2. Open a terminal/command prompt in the extracted folder
3. Run the installer:
   ```bash
   python install.py
   ```

## Starting the Server

### Windows
- Double-click `start.bat`

### Linux/Mac
- Open terminal in the installation directory
- Run: `./start.sh`

## First-Time Setup

1. Open your browser and go to `https://localhost:5000`
2. You'll see a security warning (because of self-signed certificate) - this is normal
3. Click "Advanced" and proceed to the website
4. Register your first account - this will be the admin account
5. Log in with your credentials

## Features

- Multi-monitor screenshot capture
- Secure user authentication
- Folder organization
- Dark/light theme
- Admin panel for user management
- Secure storage with encryption

## Security Features

- HTTPS encryption
- Secure password storage
- User isolation
- Rate limiting
- Protection against common web vulnerabilities

## Troubleshooting

1. If the server won't start:
   - Make sure Python is installed and in your PATH
   - Check if port 5000 is available
   - Run as administrator if necessary

2. If you can't access the website:
   - Make sure the server is running
   - Check if your firewall is blocking port 5000
   - Try using `http://localhost:5000` if HTTPS doesn't work

3. If screenshots don't save:
   - Check folder permissions
   - Make sure you have enough disk space

## Support

For issues or questions, please create an issue in the GitHub repository.

## License

This software is provided as-is, free to use and modify. 
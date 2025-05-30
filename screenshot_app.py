import keyboard
import pyautogui
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageGrab
import os
from datetime import datetime
import json
import requests
from io import BytesIO
import threading
from pystray import Icon, Menu, MenuItem
from PIL import Image
import queue
import time
from pynput import keyboard as pynput_keyboard
import concurrent.futures
import ctypes
import win32con
import win32gui
import warnings
import urllib3
from urllib3.exceptions import InsecureRequestWarning
import sys
import io
import logging
import mss
import numpy as np

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ScreenshotApp')

# Suppress only the specific warning for unverified HTTPS requests
warnings.simplefilter('ignore', InsecureRequestWarning)

class ScreenshotApp:
    def __init__(self):
        logger.info("Initializing Screenshot App...")
        
        # Load configuration
        try:
            with open('screenshot_config.json', 'r') as f:
                self.config = json.load(f)
            logger.info("Loaded configuration from screenshot_config.json")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self.config = {
                "server": {
                    "url": "https://screenie.onrender.com",
                    "verify_ssl": True
                },
                "upload": {
                    "max_retries": 3,
                    "timeout": 30,
                    "max_size": 16777216
                },
                "ui": {
                    "tray_icon": "💩",
                    "show_notifications": True
                }
            }
            # Save default configuration
            try:
                with open('screenshot_config.json', 'w') as f:
                    json.dump(self.config, f, indent=4)
                logger.info("Created default configuration file")
            except Exception as e:
                logger.error(f"Failed to save default configuration: {e}")
        
        # Create a session to reuse for all requests
        self.session = requests.Session()
        self.session.verify = self.config["server"]["verify_ssl"]
        logger.info(f"Created HTTP session with SSL verification: {self.session.verify}")
        
        self.is_selecting = False
        self.start_x = None
        self.start_y = None
        self.current_screenshot = None
        self.screenshot = None
        self.select_window = None
        self.options_window = None
        self.running = True
        self.screenshot_queue = queue.Queue()
        self.upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.upload_futures = []
        self.icon = None  # Store reference to system tray icon
        
        # Get system DPI scaling
        try:
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            logger.info("Set DPI awareness")
        except Exception as e:
            logger.warning(f"Failed to set DPI awareness: {e}")
        
        logger.info("Creating root window...")
        # Create root window for handling clipboard operations
        self.root = tk.Tk()
        self.root.title("Screenie")
        
        # Configure styles
        self.setup_styles()
        logger.info("Styles configured")
        
        # Check if credentials exist and authenticate
        logger.info("Checking credentials...")
        if not self.check_credentials():
            logger.info("No valid credentials found, showing login window")
            self.show_login_window()
        else:
            logger.info("Valid credentials found")
            self.finish_initialization()
        
        # Hide the root window but keep it running
        self.root.withdraw()
        
        self.sct = mss.mss()  # Initialize mss for multi-monitor support

    def finish_initialization(self):
        """Complete the initialization after successful login"""
        # Create system tray icon
        logger.info("Creating system tray icon...")
        self.create_system_tray()
        
        # Start key listener in a separate thread
        logger.info("Starting keyboard listener...")
        self.keyboard_listener = pynput_keyboard.Listener(on_press=self.on_key_press)
        self.keyboard_listener.start()
        
        # Start window handler thread
        logger.info("Starting window handler thread...")
        self.window_thread = threading.Thread(target=self.handle_windows, daemon=True)
        self.window_thread.start()
        
        # Schedule periodic check for screenshot queue
        self.root.after(100, self.check_screenshot_queue)
        
        # Schedule periodic check for upload futures
        self.root.after(100, self.check_upload_futures)
        
        logger.info("Screenshot App initialization complete")
        logger.info("Press Print Screen to take a screenshot")
        logger.info("Look for the system tray icon (💩) to access the menu")
    
    def setup_styles(self):
        """Setup custom styles for the UI"""
        style = ttk.Style()
        style.configure('Screenshot.TFrame', relief='raised', borderwidth=1)
        style.configure('Title.TLabel', 
                       font=('Arial', 10, 'bold'),
                       padding=2,
                       background='#f0f0f0')
        style.configure('Screenshot.TButton', 
                       padding=3,
                       width=15,
                       font=('Arial', 9))
        style.configure('Login.TButton',
                       padding=(10, 5),
                       font=('Arial', 10, 'bold'))
        style.configure('Screenshot.TLabel',
                       font=('Arial', 9),
                       padding=2,
                       background='#f0f0f0')
        style.configure('Screenshot.Horizontal.TProgressbar',
                       background='#4a90e2',
                       troughcolor='#e1e1e1')

    def on_key_press(self, key):
        try:
            if key == pynput_keyboard.Key.print_screen:
                logger.info("Print Screen key pressed")
                self.screenshot_queue.put('take_screenshot')
        except Exception as e:
            logger.error(f"Error in key press handler: {e}")
    
    def check_screenshot_queue(self):
        try:
            if not self.screenshot_queue.empty():
                action = self.screenshot_queue.get_nowait()
                if action == 'take_screenshot':
                    logger.info("Processing screenshot request")
                    self.start_screenshot()
        except Exception as e:
            logger.error(f"Error checking screenshot queue: {e}")
        finally:
            if self.running:
                self.root.after(100, self.check_screenshot_queue)
    
    def handle_windows(self):
        while self.running:
            time.sleep(0.1)
    
    def create_system_tray(self):
        """Create system tray icon."""
        try:
            logger.info("Creating system tray icon...")
            
            # Create a new image with a transparent background
            width = 64
            height = 64
            image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            
            # Draw the poop emoji (💩)
            font_size = 48
            font = None
            
            try:
                from PIL import ImageFont
                if sys.platform == 'win32':
                    font = ImageFont.truetype('seguiemj.ttf', font_size)
                elif sys.platform == 'darwin':
                    font = ImageFont.truetype('Apple Color Emoji.ttc', font_size)
                else:
                    font = ImageFont.truetype('NotoColorEmoji.ttf', font_size)
            except Exception as e:
                logger.warning(f"Failed to load emoji font: {e}")
                font = None

            # Calculate text position to center it
            emoji = "💩"
            if font:
                text_bbox = draw.textbbox((0, 0), emoji, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else:
                text_width = font_size
                text_height = font_size
            
            x = (width - text_width) // 2
            y = (height - text_height) // 2
            
            # Draw the emoji
            draw.text((x, y), emoji, font=font, fill='black')

            # Create system tray menu
            menu = Menu(
                MenuItem('Take Screenshot', lambda: self.screenshot_queue.put('take_screenshot')),
                MenuItem('Exit', lambda: self.quit_app())
            )
            
            # Create and run system tray icon
            self.icon = Icon('Screenie', image, 'Screenie', menu)
            threading.Thread(target=self.icon.run, daemon=True).start()
            
            logger.info("System tray icon created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create system tray icon: {e}")
            messagebox.showerror("Error", "Failed to create system tray icon. The application may not work correctly.")
    
    def quit_app(self):
        """Safely quit the application."""
        try:
            logger.info("Quitting application...")
            self.running = False
            
            # Stop keyboard listener
            if hasattr(self, 'keyboard_listener'):
                self.keyboard_listener.stop()
            
            # Stop system tray icon
            if self.icon:
                self.icon.stop()
            
            # Clean up executor
            if hasattr(self, 'upload_executor'):
                self.upload_executor.shutdown(wait=False)
            
            # Destroy any remaining windows
            if self.select_window:
                self.select_window.destroy()
            if self.options_window:
                self.options_window.destroy()
            
            # Quit the main window
            self.root.quit()
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Force quit if cleanup fails
            os._exit(1)
    
    def start_screenshot(self):
        if hasattr(self, 'select_window') and self.select_window:
            self.select_window.destroy()
            self.select_window = None
            return
            
        logger.info("Taking screenshot of active monitor")
        try:
            # Get the current mouse position
            mouse_x, mouse_y = pyautogui.position()
            
            # Get all monitors
            all_monitors = self.sct.monitors[1:]  # Skip the first monitor which is the "all in one"
            
            # Find the monitor that contains the mouse cursor
            active_monitor = None
            for monitor in all_monitors:
                if (monitor["left"] <= mouse_x < monitor["left"] + monitor["width"] and
                    monitor["top"] <= mouse_y < monitor["top"] + monitor["height"]):
                    active_monitor = monitor
                    break
            
            if not active_monitor:
                active_monitor = all_monitors[0]  # Fallback to first monitor if not found
            
            # Take screenshot of only the active monitor
            screen = self.sct.grab(active_monitor)
            self.screenshot = Image.frombytes('RGB', screen.size, screen.rgb)
            
            # Create selection window
            self.select_window = tk.Toplevel(self.root)
            self.select_window.withdraw()
            
            # Remove window decorations and make it semi-transparent
            self.select_window.overrideredirect(True)
            self.select_window.attributes('-alpha', 0.3, '-topmost', True)
            
            # Position window to cover only the active monitor
            geometry = f"{active_monitor['width']}x{active_monitor['height']}+{active_monitor['left']}+{active_monitor['top']}"
            self.select_window.geometry(geometry)
            
            # Hide from taskbar
            hwnd = self.select_window.winfo_id()
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            style = style & ~win32con.WS_EX_APPWINDOW
            style = style | win32con.WS_EX_TOOLWINDOW
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
            
            # Create canvas
            self.canvas = tk.Canvas(
                self.select_window,
                                  cursor="cross",
                                  highlightthickness=0,
                bg='grey'
            )
            self.canvas.pack(fill=tk.BOTH, expand=True)
            
            # Display the screenshot
            self.photo = ImageTk.PhotoImage(self.screenshot)
            self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
            
            # Store monitor info for coordinate translation
            self.monitor_info = {
                'virtual_left': active_monitor['left'],
                'virtual_top': active_monitor['top'],
                'virtual_width': active_monitor['width'],
                'virtual_height': active_monitor['height']
            }
            
            # Bind events
            self.canvas.bind("<ButtonPress-1>", self.on_press)
            self.canvas.bind("<B1-Motion>", self.on_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_release)
            self.select_window.bind("<Escape>", lambda e: self.select_window.destroy())
            
            # Show window
            self.select_window.deiconify()
            self.select_window.focus_force()
            
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            if self.select_window:
                self.select_window.destroy()
                self.select_window = None
    
    def on_press(self, event):
        # Store raw canvas coordinates
        self.start_x = event.x
        self.start_y = event.y
        # Create selection rectangle
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='red', width=2
        )
    
    def on_drag(self, event):
        # Update selection rectangle
        x = max(0, min(event.x, self.monitor_info['virtual_width']))
        y = max(0, min(event.y, self.monitor_info['virtual_height']))
        self.canvas.coords(self.rect, self.start_x, self.start_y, x, y)
    
    def on_release(self, event):
        try:
            # Get selection coordinates
            x1 = min(self.start_x, event.x)
            y1 = min(self.start_y, event.y)
            x2 = max(self.start_x, event.x)
            y2 = max(self.start_y, event.y)
            
            # Ensure coordinates are within bounds
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(self.monitor_info['virtual_width'], x2)
            y2 = min(self.monitor_info['virtual_height'], y2)
            
            # Crop the screenshot
            self.current_screenshot = self.screenshot.crop((x1, y1, x2, y2))
            
            if self.select_window:
                self.select_window.destroy()
                self.select_window = None
            
            self.root.after(0, self.show_options)
            
        except Exception as e:
            logger.error(f"Error in on_release: {e}")
            if self.select_window:
                self.select_window.destroy()
                self.select_window = None
    
    def show_options(self):
        if hasattr(self, 'options_window') and self.options_window:
            return
            
        self.options_window = tk.Toplevel(self.root)
        self.options_window.title("Screenie")
        self.options_window.attributes('-topmost', True)
        
        # Hide from taskbar
        self.options_window.wm_withdraw()
        hwnd = self.options_window.winfo_id()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style = style & ~win32con.WS_EX_APPWINDOW
        style = style | win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        self.options_window.wm_deiconify()
        
        # Set window icon to poop emoji
        icon_size = 32
        icon_img = Image.new('RGBA', (icon_size, icon_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon_img)
        try:
            if sys.platform == 'win32':
                font = ImageFont.truetype('seguiemj.ttf', icon_size)  # Windows Segoe UI Emoji
            elif sys.platform == 'darwin':
                font = ImageFont.truetype('Apple Color Emoji.ttc', icon_size)  # macOS
            else:
                font = ImageFont.truetype('NotoColorEmoji.ttf', icon_size)  # Linux
        except Exception:
            font = None
            
        # Draw the poop emoji
        emoji = "💩"
        if font:
            text_bbox = draw.textbbox((0, 0), emoji, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = (icon_size - text_width) // 2
            y = (icon_size - text_height) // 2
            draw.text((x, y), emoji, font=font, embedded_color=True)
            
        # Convert to PhotoImage and set as window icon
        icon = ImageTk.PhotoImage(icon_img)
        self.options_window.iconphoto(True, icon)
        
        # Main frame
        main_frame = ttk.Frame(self.options_window, style='Screenshot.TFrame', padding=2)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title with emoji
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, padx=2, pady=(2, 0))
        
        # Create emoji label with larger font
        emoji_label = ttk.Label(title_frame, 
                              text="💩",
                              font=('Segoe UI Emoji', 24),
                              style='Title.TLabel',
                              anchor='center')
        emoji_label.pack(side=tk.LEFT, padx=5)
        
        title_label = ttk.Label(title_frame, 
                              text="Screenshot Taken!",
                              style='Title.TLabel',
                              anchor='center')
        title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Preview frame
        preview_frame = ttk.Frame(main_frame, style='Screenshot.TFrame')
        preview_frame.pack(padx=2, pady=2)
        
        # Preview
        preview = self.current_screenshot.copy()
        preview.thumbnail((250, 150))  # Smaller preview
        photo = ImageTk.PhotoImage(preview)
        
        preview_label = ttk.Label(preview_frame, image=photo, style='Screenshot.TLabel')
        preview_label.image = photo
        preview_label.pack(padx=1, pady=1)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=2)
        
        # Buttons
        copy_btn = ttk.Button(button_frame, 
                            text="Copy to Clipboard",
                            style='Screenshot.TButton',
                            command=self.handle_copy)
        copy_btn.pack(side=tk.LEFT, padx=2)
        
        upload_btn = ttk.Button(button_frame,
                             text="Upload to Website",
                             style='Screenshot.TButton',
                             command=self.handle_upload)
        upload_btn.pack(side=tk.LEFT, padx=2)
        
        # Progress frame
        self.progress_frame = ttk.Frame(main_frame, style='Screenshot.TFrame')
        self.progress_frame.pack(fill=tk.X, padx=2, pady=2)
        
        self.progress_label = ttk.Label(self.progress_frame,
                                      text="",
                                      style='Screenshot.TLabel',
                                      anchor='center')
        self.progress_label.pack(fill=tk.X)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame,
                                          style='Screenshot.Horizontal.TProgressbar',
                                          mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, padx=2, pady=2)
        self.progress_frame.pack_forget()
        
        # Center window
        self.options_window.update_idletasks()
        width = 300  # More compact width
        height = 250  # More compact height
        x = (self.options_window.winfo_screenwidth() // 2) - (width // 2)
        y = (self.options_window.winfo_screenheight() // 2) - (height // 2)
        self.options_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Set minimum size
        self.options_window.minsize(width, height)
        
        # Add window border
        self.options_window.configure(relief='raised', bd=1)
        
        self.options_window.focus_force()
        self.options_window.protocol("WM_DELETE_WINDOW", self.close_options_window)

    def handle_copy(self):
        self.copy_to_clipboard()
        self.close_options_window()
    
    def handle_upload(self):
        """Handle screenshot upload."""
        if not self.screenshot:
            return

        def upload_task():
            try:
                # Optimize image
                img_byte_arr = BytesIO()
                self.current_screenshot.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()

                # Prepare upload
                url = f"{self.config['server']['url']}/upload"
                files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
                
                # Get current date for folder name
                today = datetime.now().strftime('%Y-%m-%d')
                
                # Upload with retry logic
                for attempt in range(self.config["upload"]["max_retries"]):
                    try:
                        response = self.session.post(
                            url,
                            files=files,
                            data={'folder': today},
                            timeout=self.config["upload"]["timeout"]
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            return {
                                'success': True,
                                'url': f"{self.config['server']['url']}{data['path']}"
                            }
                        else:
                            logger.error(f"Upload failed with status {response.status_code}")
                            
                    except Exception as e:
                        logger.error(f"Upload attempt {attempt + 1} failed: {e}")
                        if attempt < self.config["upload"]["max_retries"] - 1:
                            time.sleep(1)  # Wait before retrying
                            continue
                        break
                
                return {'success': False, 'error': 'Upload failed after retries'}
                
            except Exception as e:
                logger.error(f"Upload task error: {e}")
                return {'success': False, 'error': str(e)}
        
        # Submit upload task
        future = self.upload_executor.submit(upload_task)
        self.upload_futures.append(future)
        
        # Close windows immediately
        if self.options_window:
            self.options_window.destroy()
            self.options_window = None
        
        # Show a small notification that upload is in progress
        self.root.after(0, lambda: messagebox.showinfo("Upload Started", "Screenshot upload started in background"))

    def check_credentials(self):
        """Check if we have valid credentials."""
        try:
            creds_file = os.path.join(os.path.expanduser('~'), '.screenie_user_credentials')
            if os.path.exists(creds_file):
                with open(creds_file, 'r') as f:
                    creds = json.load(f)
                    if 'username' in creds and 'password' in creds:
                        # Try to authenticate with stored credentials
                        if self.authenticate(creds['username'], creds['password']):
                            return True
            return False
        except Exception as e:
            logger.error(f"Error checking credentials: {e}")
            return False

    def save_credentials(self, username, password):
        """Save user credentials securely."""
        try:
            creds_file = os.path.join(os.path.expanduser('~'), '.screenie_user_credentials')
            with open(creds_file, 'w') as f:
                json.dump({
                    'username': username,
                    'password': password
                }, f)
        except Exception as e:
            logger.error(f"Error saving credentials: {e}")

    def show_login_window(self):
        """Show login window for user credentials."""
        logger.info("Creating login window...")
        
        # Check server connection first
        if not self.check_server_connection():
            self.quit_app()
            return
        
        login_window = tk.Toplevel(self.root)
        login_window.title("Screenie Login")
        login_window.geometry("300x250")  # Made window slightly taller
        login_window.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        # Ensure this window stays on top and is visible
        login_window.lift()
        login_window.attributes('-topmost', True)
        login_window.focus_force()
        
        # Center the window
        login_window.update_idletasks()
        width = 300
        height = 250  # Adjusted height
        x = (login_window.winfo_screenwidth() // 2) - (width // 2)
        y = (login_window.winfo_screenheight() // 2) - (height // 2)
        login_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # Main frame with padding
        frame = ttk.Frame(login_window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Title with icon
        title_frame = ttk.Frame(frame)
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_icon = ttk.Label(title_frame, text="💩", font=('Segoe UI Emoji', 24))
        title_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        title_label = ttk.Label(title_frame, text="Screenie Login", font=('Arial', 16, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # Username field
        username_frame = ttk.Frame(frame)
        username_frame.pack(fill=tk.X, pady=(0, 10))
        
        username_label = ttk.Label(username_frame, text="Username:", font=('Arial', 10))
        username_label.pack(anchor='w')
        
        username_entry = ttk.Entry(username_frame, font=('Arial', 10))
        username_entry.pack(fill=tk.X, pady=(2, 0))
        
        # Password field
        password_frame = ttk.Frame(frame)
        password_frame.pack(fill=tk.X, pady=(0, 20))
        
        password_label = ttk.Label(password_frame, text="Password:", font=('Arial', 10))
        password_label.pack(anchor='w')
        
        password_entry = ttk.Entry(password_frame, show="•", font=('Arial', 10))
        password_entry.pack(fill=tk.X, pady=(2, 0))
        
        def handle_login():
            username = username_entry.get()
            password = password_entry.get()
            
            if not username or not password:
                messagebox.showerror("Error", "Please enter both username and password")
                return
            
            # Log exact input values (username only for security)
            logger.debug(f"Login attempt - Username length: {len(username)}, Password length: {len(password)}")
            logger.debug(f"Username characters: {[ord(c) for c in username]}")
            
            if self.authenticate(username, password):
                self.save_credentials(username, password)
                login_window.destroy()
                self.finish_initialization()
            else:
                messagebox.showerror(
                    "Login Failed",
                    "Invalid username or password.\n\n"
                    "Please make sure you're using the same credentials\n"
                    "as on the screenshot website."
                )
        
        # Login button with improved styling
        login_btn = ttk.Button(
            frame,
            text="Sign In",
            style='Login.TButton',
            command=handle_login
        )
        login_btn.pack(fill=tk.X, pady=(0, 10))
        
        # Help text
        help_text = ttk.Label(
            frame,
            text="Use the same credentials as on\nthe screenshot website",
            font=('Arial', 9),
            justify='center'
        )
        help_text.pack(fill=tk.X)
        
        # Pre-fill the admin credentials for testing
        username_entry.insert(0, "OPERATOR_1337")
        password_entry.insert(0, "ITgwXqkIl2co6RsgAvBhvQ")
        
        # Bind Enter key to login button
        login_window.bind('<Return>', lambda e: handle_login())
        
        # Focus the username entry
        username_entry.focus_force()
        
        # Make window modal
        login_window.transient(self.root)
        login_window.grab_set()
        
        logger.info("Login window created and displayed")

    def authenticate(self, username, password):
        """Authenticate with the server."""
        try:
            logger.info(f"Attempting to authenticate with server: {self.config['server']['url']}")
            logger.info(f"Using username: {username} (password length: {len(password)})")
            
            # Create a new session with proper settings
            self.session = requests.Session()
            self.session.verify = self.config["server"]["verify_ssl"]
            
            # Set headers to match browser request exactly
            headers = {
                'Content-Type': 'application/json',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'app://screenie',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://screenie.space/',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Dest': 'empty',
                'Connection': 'keep-alive'
            }
            self.session.headers.update(headers)
            
            logger.info("Using headers: %s", headers)
            
            # First make a GET request to get any necessary cookies
            try:
                logger.info("Making initial GET request to /")
                self.session.get(f"{self.config['server']['url']}/")
            except Exception as e:
                logger.warning(f"Initial GET request failed: {e}")
            
            # Attempt login
            url = f"{self.config['server']['url']}/login"
            logger.info("Making login request to: %s", url)
            
            # Format credentials exactly as the web form
            login_data = {
                "username": username,
                "password": password,
                "_permanent": True
            }
            
            # Log non-sensitive debug info
            logger.debug(f"Request payload size: {len(str(login_data))} bytes")
            logger.info(f"Sending login request for user: {username}")
            
            # Make the login request with form data
            response = self.session.post(
                url,
                json=login_data,
                timeout=self.config["upload"]["timeout"],
                allow_redirects=True
            )
            
            logger.info(f"Login response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(f"Response cookies: {dict(response.cookies)}")
            
            try:
                response_data = response.json()
                safe_response = {k: v for k, v in response_data.items() if k != 'password'}
                logger.info(f"Response data: {safe_response}")
            except Exception as e:
                logger.error(f"Failed to parse response JSON: {e}")
                logger.error(f"Raw response content: {response.text}")
                response_data = {}
            
            if response.status_code == 200:
                # Store cookies
                self.save_auth_cookies(dict(response.cookies))
                logger.info("Authentication successful")
                
                # Verify the session is working
                check_auth_url = f"{self.config['server']['url']}/check-auth"
                logger.info("Verifying session with check-auth endpoint")
                
                auth_check = self.session.get(
                    check_auth_url,
                    headers={'Origin': 'app://screenie'}
                )
                logger.info(f"Auth check response: {auth_check.status_code}")
                
                try:
                    auth_data = auth_check.json()
                    logger.info(f"Auth check data: {auth_data}")
                    if auth_data.get('authenticated'):
                        return True
                    else:
                        logger.error("Auth check failed after successful login")
                        return False
                except Exception as e:
                    logger.error(f"Failed to parse auth check response: {e}")
                    logger.error(f"Raw auth check response: {auth_check.text}")
                    return False
            
            # Handle error responses
            error_message = response_data.get('error', 'Unknown error')
            logger.error(f"Authentication failed: {error_message}")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            if isinstance(e, requests.exceptions.SSLError):
                logger.error("SSL verification failed. Check your SSL settings.")
            elif isinstance(e, requests.exceptions.ConnectionError):
                logger.error("Connection failed. Check if the server is accessible.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            logger.exception("Full authentication error traceback:")
            return False
    
    def get_auth_cookies(self):
        """Get authentication cookies from the session."""
        return dict(self.session.cookies)

    def save_auth_cookies(self, cookies):
        """Save authentication cookies to the session."""
        self.session.cookies.update(cookies)

    def close_options_window(self):
        if self.options_window:
            self.options_window.destroy()
            self.options_window = None
    
    def copy_to_clipboard(self):
        output = BytesIO()
        self.current_screenshot.save(output, 'BMP')
        data = output.getvalue()[14:]
        output.close()
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(data, type='image/bmp')
            messagebox.showinfo("Success", "Screenshot copied to clipboard!")
        except tk.TclError:
            messagebox.showerror("Error", "Failed to copy to clipboard")
    
    def optimize_image(self, image, max_size=(1920, 1080), quality=85):
        """Optimize image size and quality for faster upload."""
        # Make a copy to avoid modifying the original
        img = image.copy()
        
        # Resize if larger than max_size while maintaining aspect ratio
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (removes alpha channel)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Save to BytesIO with optimized settings
        optimized = BytesIO()
        img.save(optimized, format='PNG', optimize=True, quality=quality)
        return optimized.getvalue()

    def show_progress(self, message=""):
        """Show progress bar with optional message."""
        if hasattr(self, 'progress_frame'):
            self.progress_frame.pack(pady=10, fill=tk.X, padx=20)
            self.progress_bar.start(10)
            if message:
                self.progress_label.config(text=message)

    def hide_progress(self):
        """Hide progress bar."""
        if hasattr(self, 'progress_frame'):
            self.progress_bar.stop()
            self.progress_frame.pack_forget()

    def check_upload_futures(self):
        """Check status of background uploads and clean up completed ones."""
        if self.upload_futures:
            completed = [f for f in self.upload_futures if f.done()]
            for future in completed:
                try:
                    result = future.result()
                    if result.get('success'):
                        logger.info("Upload completed successfully")
                        messagebox.showinfo("Success", "Screenshot uploaded successfully!")
                    else:
                        logger.error(f"Upload failed: {result.get('error', 'Unknown error')}")
                        messagebox.showerror("Error", f"Upload failed: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    logger.error(f"Upload failed: {e}")
                    messagebox.showerror("Error", f"Upload failed: {str(e)}")
                self.upload_futures.remove(future)
        
        if self.running:
            self.root.after(100, self.check_upload_futures)

    def check_server_connection(self):
        """Check if the server is accessible."""
        try:
            url = f"{self.config['server']['url']}/check-auth"
            response = self.session.get(
                url,
                timeout=self.config["upload"]["timeout"]
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Server connection error: {e}")
            messagebox.showerror(
                "Connection Error",
                "Cannot connect to the screenshot server.\n\n"
                "Please make sure the server (server.py) is running first.\n\n"
                "To start the server:\n"
                "1. Open a new terminal\n"
                "2. Navigate to the screenie folder\n"
                "3. Run: python server.py"
            )
            return False

def run_app():
    print("Starting Screenie...")
    print("=" * 50)
    logger.info("Starting Screenshot App...")
    
    try:
        app = ScreenshotApp()
        logger.info("Screenshot app is running in the background")
        logger.info("Press Print Screen to take a screenshot")
        logger.info("Look for the system tray icon (💩) to access the menu")
        
        def check_icon(app):
            if not app.icon:
                app.create_system_tray()
            return True
        
        # Schedule system tray icon creation
        app.root.after(1000, check_icon, app)
        
        # Start the main event loop
        app.root.mainloop()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        if 'app' in locals():
            app.quit_app()
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        if 'app' in locals():
            app.quit_app()

if __name__ == "__main__":
    run_app()
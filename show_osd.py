#!/usr/bin/env python3
# type: ignore
import sys
import os
import argparse
import socket
import json
import time
import threading
import tempfile
import atexit
import signal
import re
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, QPoint, pyqtSignal, QObject
from PyQt5.QtGui import QScreen, QCursor

# Socket for IPC
PORT = 9876  # Use a fixed port for IPC
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'show_osd.lock')

# Default settings
DEFAULT_SETTINGS = {
    "window_width": 480,
    "window_height": 288,
    "x_offset": 0,
    "y_offset": 0,
    "duration": 2000
}

# Settings file path
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osd_settings.json")

def load_settings():
    """Load settings from settings file, or use defaults if file doesn't exist"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            return settings
        else:
            # Create default settings file if it doesn't exist
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(DEFAULT_SETTINGS, f, indent=4)
            return DEFAULT_SETTINGS
    except Exception as e:
        print(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS

class SignalReceiver(QObject):
    # Signal to update the OSD from the main Qt thread
    update_signal = pyqtSignal(str, float, int, int, int, int, bool)

class OSDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.template = None
        self.value = None
        self.duration = 2000
        self.close_timer = None
        self.page_loaded = False
        self.server = None
        self.server_thread = None
        self.muted = False
        # Setup signal receiver
        self.signal_receiver = SignalReceiver()
        self.signal_receiver.update_signal.connect(self.update_content)
        
        # Setup UI
        self.setup_ui()
        
        # Make the window visible on all workspaces (sticky)
        if QApplication.instance().platformName() == "xcb":
            try:
                import Xlib
                import Xlib.display
                display = Xlib.display.Display()
                window_id = int(self.winId())
                window = display.create_resource_object('window', window_id)
                atom = display.intern_atom('_NET_WM_DESKTOP')
                window.change_property(atom, Xlib.Xatom.CARDINAL, 32, [0xFFFFFFFF])
                display.sync()
            except ImportError:
                print("Warning: python-xlib not installed, cannot set window to all workspaces")
            except Exception as e:
                print(f"Error setting window to all workspaces: {e}")
        
        # Create lock file to signal we're running
        self.create_lock_file()
        
        # Start server in separate thread
        self.start_server()
        
        # Register cleanup handler for clean exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def create_lock_file(self):
        """Create a lock file to indicate the server is running"""
        try:
            with open(LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            print(f"Warning: Could not create lock file: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.cleanup()
        sys.exit(0)

    def setup_ui(self):
        """Initialize the UI components"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Load settings for window size
        settings = load_settings()
        window_width = settings.get("window_width", 280)
        window_height = settings.get("window_height", 188)
        
        self.webview = QWebEngineView(self)
        self.webview.page().setBackgroundColor(Qt.transparent)
        self.webview.loadFinished.connect(self.on_load_finished)
        
        # Set fixed size from settings
        self.webview.setFixedSize(window_width, window_height)
        self.resize(window_width, window_height)
        
        # Use layout to let window resize with content
        self.setCentralWidget(self.webview)

        # Load the index.html template from file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(script_dir, "templates", "index.html")
        
        if os.path.exists(index_path):
            self.webview.load(QUrl.fromLocalFile(index_path))
        else:
            # Fallback if the file doesn't exist
            self.webview.setHtml("<html><body><h1>Error: index.html not found</h1></body></html>")

    def start_server(self):
        """Start the server in a separate thread"""
        self.running = True
        self.server_thread = threading.Thread(target=self.run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
    
    def run_server(self):
        """Run the socket server to listen for incoming requests"""
        retries = 0
        max_retries = 5
        
        while self.running and retries < max_retries:
            try:
                self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.server.bind(('127.0.0.1', PORT))
                self.server.listen(5)
                self.server.settimeout(1)  # 1 second timeout for clean shutdown
                
                print(f"OSD server running on port {PORT}")
                retries = 0  # Reset retries on successful binding
                
                # Main server loop
                while self.running:
                    try:
                        client, _ = server_accept_with_timeout(self.server, 1)
                        if not client:
                            continue
                            
                        data = client.recv(1024).decode('utf-8')
                        client.close()
                        
                        try:
                            if not data:
                                print("Warning: Empty data received")
                                continue
                            
                            params = json.loads(data)
                            template = params.get('template')
                            muted = params.get('muted')
                            value = float(params.get('value'))
                            duration = int(params.get('duration', 2000))
                            fade = int(params.get('fade', 500))
                            
                            # Update via signal to ensure thread safety - pass dummy values for width/height
                            # until we update the signal parameters
                            self.signal_receiver.update_signal.emit(
                                template, value, duration, fade, 0, 0, muted
                            )
                        except json.JSONDecodeError as e:
                            print(f"Error parsing JSON: {e}, received data: '{data}'")
                        except Exception as e:
                            print(f"Error processing request: {e}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            print(f"Error in server loop: {e}")
                            break
                
                # Close socket when loop ends
                if self.server:
                    self.server.close()
                
            except Exception as e:
                print(f"Server error: {e}")
                retries += 1
                time.sleep(1)  # Wait before retry
                
            # Reset server for next attempt
            self.server = None
        
        print("Server thread exiting")
    
    def update_content(self, template, value, duration, fade, width, height, muted=False):
        """Update the OSD content with new values"""
        self.template = template
        self.value = int(value)
        self.muted = muted
        
        # Load duration from settings file
        settings = load_settings()
        self.duration = settings.get("duration", 2000)
        
        # Cancel any running timers
        if self.close_timer and self.close_timer.isActive():
            self.close_timer.stop()
        
        # Update content if page is loaded
        if self.page_loaded:
            # For subsequent calls, update content first, then show
            self.update_display()
            
            # Now make window visible - always call show() since super().hide() was used
            self.setWindowOpacity(1.0)
            
            # Position window on the screen with the cursor BEFORE showing
            self.position_window()
            
            self.show()
            self.raise_() # Ensure it's on top
        
        # Set new close timer
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.hide_window)
        self.close_timer.start(self.duration)
    
    def position_window(self):
        """Position the window on the correct screen"""
        # Load current settings
        settings = load_settings()
        x_offset = settings.get("x_offset", 0)
        y_offset = settings.get("y_offset", 0)
        
        cursor_pos = QCursor.pos()
        app = QApplication.instance()
        current_screen = app.primaryScreen()
        
        for screen in app.screens():
            if screen.geometry().contains(cursor_pos):
                current_screen = screen
                break
        
        # Get current window size
        window_size = self.size()
        window_width = window_size.width()
        window_height = window_size.height()
        
        # Calculate x position
        if x_offset == 0:
            # Center horizontally
            x = current_screen.geometry().x() + (current_screen.geometry().width() - window_width) / 2
        elif x_offset > 0:
            # Position from right edge
            x = current_screen.geometry().x() + (current_screen.geometry().width() - window_width) - x_offset
        else:
            # Position from left edge for negative values
            x = current_screen.geometry().x() - x_offset
        
        # Calculate y position
        if y_offset == 0:
            # Center vertically
            y = current_screen.geometry().y() + (current_screen.geometry().height() - window_height) / 2
        elif y_offset > 0:
            # Position from bottom edge
            y = current_screen.geometry().y() + (current_screen.geometry().height() - window_height) - y_offset
        else:
            # Position from top edge for negative values
            y = current_screen.geometry().y() - y_offset
        
        # Convert coordinates to integers
        self.move(int(x), int(y))

    def on_load_finished(self):
        """Called when the webview finishes loading"""
        self.page_loaded = True
        if self.template and self.value is not None:
            self.update_display()
            
            # Set fixed window size instead of adjusting to content
            settings = load_settings()
            window_width = settings.get("window_width", 280)
            window_height = settings.get("window_height", 188)
            self.webview.setFixedSize(window_width, window_height)
            self.resize(window_width, window_height)
            
            # Position window
            self.position_window()
            
            # Load duration from settings
            self.duration = settings.get("duration", 2000)
            
            # Set timer for hiding
            self.close_timer = QTimer()
            self.close_timer.setSingleShot(True)
            self.close_timer.timeout.connect(self.hide_window)
            self.close_timer.start(self.duration)
    
    def update_display(self):
        """Update the HTML content with new values"""
        try:
            # Load template files
            template_html = self.template_content()
            index_html = self.get_index_content()
            
            capped_value = min(self.value, 150)
            
            # Calculate display values
            cyan_width = min(capped_value, 100) / 150 * 100
            red_width = (capped_value - 100) / 150 * 100 if capped_value > 100 else 0
            red_offset = 66.67 if capped_value > 100 else 0
            
            # Extract head content from index.html
            head_match = re.search(r'<head>(.*?)</head>', index_html, re.DOTALL)
            if head_match:
                head_content = head_match.group(1)
                
                # Create script to update everything
                script = f"""
                // First, update the entire head content
                document.head.innerHTML = `{head_content}`;
                
                // Update the content div with the template
                document.getElementById('content').innerHTML = `{template_html}`;
                
                // Now update the dynamic elements
                document.getElementById('progress-standard-vol').style.width = '{cyan_width}%';
                document.getElementById('progress-excess-vol').style.width = '{red_width}%';
                document.getElementById('progress-excess-vol').style.left = '{red_offset}%';
                document.getElementById('volume-value').innerText = '{self.value}';            
                document.getElementById('muted-container').style.display = '{'block' if self.muted else 'none'}';
                """
                self.webview.page().runJavaScript(script)
                
                # We no longer adjust size here - using fixed size from settings
            else:
                print("Warning: Could not extract head section from index.html")
        except FileNotFoundError as e:
            print(f"Template error: {e}")
            script = f"document.body.innerHTML = '<h1>Template {self.template} not found</h1>';"
            self.webview.page().runJavaScript(script)
        except Exception as e:
            print(f"Error updating display: {e}")

    def get_index_content(self):
        """Get the content of the index.html template file"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(script_dir, "templates", "index.html")
        with open(index_path, "r") as f:
            return f.read()

    def template_content(self):
        """Get the content of the template file"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "templates", f"{self.template}.html")
        with open(template_path, "r") as f:
            return f.read()

    def hide_window(self):
        """Hide the window immediately"""
        # We need to call super().hide() to ensure the window is removed from the system
        super().hide()
    
    def cleanup(self):
        """Clean up resources when closing"""
        print("Cleaning up...")
        self.running = False
        
        # Remove lock file
        try:
            if os.path.exists(LOCK_FILE):
                os.unlink(LOCK_FILE)
        except Exception:
            pass
        
        # Close server socket
        if self.server:
            try:
                self.server.close()
            except Exception:
                pass
    
    def closeEvent(self, event):
        """Handle window close event"""
        self.cleanup()
        super().closeEvent(event)

    def adjust_size_to_content(self):
        """Set window size from settings"""
        settings = load_settings()
        window_width = settings.get("window_width", 280)
        window_height = settings.get("window_height", 188)
        
        self.webview.setFixedSize(window_width, window_height)
        self.resize(window_width, window_height)
        self.position_window()

def server_accept_with_timeout(server, timeout):
    """Accept a connection with timeout handling"""
    try:
        server.settimeout(timeout)
        return server.accept()
    except socket.timeout:
        return None, None
    except Exception as e:
        print(f"Accept error: {e}")
        return None, None

def send_update_to_server(args):
    """Send an update request to a running server"""
    # Check if server is running
    if not os.path.exists(LOCK_FILE):
        return False
    
    try:
        # Try to connect to the server
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1)  # 1 second timeout
        client.connect(('127.0.0.1', PORT))
        
        # Send parameters as JSON - remove duration as it's read from settings
        params = {
            'template': args.template,
            'value': args.value,
            'muted': args.muted
        }
        client.send(json.dumps(params).encode('utf-8'))
        client.close()
        return True
    except Exception as e:
        print(f"Failed to send update: {e}")
        # If server failed to respond, clean up the stale lock
        try:
            os.unlink(LOCK_FILE)
        except Exception:
            pass
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Display an OSD popup")
    parser.add_argument("--template", required=True, help="HTML template name (e.g., volume)")
    parser.add_argument("--value", type=float, required=True, help="Value to display (e.g., volume percentage)")
    parser.add_argument("--muted", action="store_true", help="Show as muted (for volume)")
    args = parser.parse_args()

    # Try to send update to existing server
    if send_update_to_server(args):
        print("Update sent to existing server")
        sys.exit(0)
    
    # If we get here, we need to start a new server
    print("Starting new OSD server")
    
    # Start the server in a separate process
    if os.fork() == 0:
        # This is the child process - it will become the server
        app = QApplication(sys.argv)
        window = OSDWindow()
        
        # Initialize content but don't show window yet
        window.setWindowOpacity(0)  # Start invisible
        window.template = args.template
        window.value = args.value
        window.muted = args.muted
        
        # Start the event loop without explicitly showing the window
        sys.exit(app.exec_())
    else:
        # This is the parent process - wait for server to start then send the message
        # Give the server some time to initialize
        max_retries = 5
        for i in range(max_retries):
            time.sleep(0.5)  # Half-second delay between attempts
            if os.path.exists(LOCK_FILE):
                # Try to connect to the new server
                if send_update_to_server(args):
                    print("Update sent to newly started server")
                    sys.exit(0)
            
        print("Failed to connect to server after multiple attempts")
        sys.exit(1)
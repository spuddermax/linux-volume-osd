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
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, QPoint, pyqtSignal, QObject
from PyQt5.QtGui import QScreen, QCursor

# Socket for IPC
PORT = 9876  # Use a fixed port for IPC
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'show_osd.lock')

class SignalReceiver(QObject):
    # Signal to update the OSD from the main Qt thread
    update_signal = pyqtSignal(str, float, int, int, int, int, bool)

class OSDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.template = None
        self.value = None
        self.duration = 2000
        self.fade_duration = 500
        self.width = 300
        self.height = 300
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
        self.setGeometry(0, 0, self.width, self.height)

        self.webview = QWebEngineView(self)
        self.webview.setGeometry(0, 0, self.width, self.height)
        self.webview.page().setBackgroundColor(Qt.transparent)
        self.webview.loadFinished.connect(self.on_load_finished)

        # Load template - just once at startup
        script_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(script_dir, "templates", f"index.html")
        if os.path.exists(index_path):
            self.webview.load(QUrl.fromLocalFile(index_path))
        else:
            self.webview.setHtml("<html><body><h1>OSD Placeholder</h1></body></html>")

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
                            params = json.loads(data)
                            template = params.get('template')
                            muted = params.get('muted')
                            value = float(params.get('value'))
                            duration = int(params.get('duration', 2000))
                            fade = int(params.get('fade', 500))
                            width = int(params.get('width', 300))
                            height = int(params.get('height', 300))
                            
                            # Update via signal to ensure thread safety
                            self.signal_receiver.update_signal.emit(
                                template, value, duration, fade, width, height, muted
                            )
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
        # Update window properties
        if width != self.width or height != self.height:
            self.width = width
            self.height = height
            self.setGeometry(0, 0, self.width, self.height)
            self.webview.setGeometry(0, 0, self.width, self.height)
        
        self.template = template
        self.value = int(value)
        self.muted = muted
        self.duration = duration
        self.fade_duration = fade
        
        # Position the window
        self.position_window()
        
        # Cancel any running timers or animations
        if hasattr(self, 'anim') and self.anim.state() == QPropertyAnimation.Running:
            self.anim.stop()
        
        if self.close_timer and self.close_timer.isActive():
            self.close_timer.stop()
        
        # Update content if page is loaded
        if self.page_loaded:
            # For subsequent calls, update content first, then show
            self.update_display()
            # Now make window visible
            self.setWindowOpacity(1.0)
            if not self.isVisible():
                self.show()
                self.raise_()
        
        # Set new close timer
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.start_fade_out)
        self.close_timer.start(self.duration)
    
    def position_window(self):
        """Position the window on the correct screen"""
        cursor_pos = QCursor.pos()
        app = QApplication.instance()
        current_screen = app.primaryScreen()
        
        for screen in app.screens():
            if screen.geometry().contains(cursor_pos):
                current_screen = screen
                break
        
        screen_geometry = current_screen.geometry()
        x = screen_geometry.x() + (screen_geometry.width() - self.width) - 40
        y = screen_geometry.y() + (screen_geometry.height() - self.height) - 40
        self.move(x, y)

    def on_load_finished(self):
        """Called when the webview finishes loading"""
        self.page_loaded = True
        if self.template and self.value is not None:
            self.update_display()
            # Now that content is updated, make window visible if it's the initial load
            if not self.isVisible():
                self.position_window()
                self.setWindowOpacity(1.0)
                self.show()
                self.raise_()
                # Set timer for hiding
                self.close_timer = QTimer()
                self.close_timer.setSingleShot(True)
                self.close_timer.timeout.connect(self.start_fade_out)
                self.close_timer.start(self.duration)
    
    def update_display(self):
        """Update the HTML content with new values"""
        try:
            template_html = self.template_content()
            capped_value = min(self.value, 150)
            
            # Calculate display values
            cyan_width = min(capped_value, 100) / 150 * 100
            red_width = (capped_value - 100) / 150 * 100 if capped_value > 100 else 0
            red_offset = 66.67 if capped_value > 100 else 0
            
            # Create and run JavaScript
            script = f"""
            document.getElementById('content').innerHTML = `{template_html}`;
            document.getElementById('progress-standard-vol').style.width = '{cyan_width}%';
            document.getElementById('progress-excess-vol').style.width = '{red_width}%';
            document.getElementById('progress-excess-vol').style.left = '{red_offset}%';
            document.getElementById('volume-value').innerText = '{self.value}';            
            document.getElementById('muted-container').style.display = '{'block' if self.muted else 'none'}';

            """
            self.webview.page().runJavaScript(script)
        except FileNotFoundError:
            script = f"document.body.innerHTML = '<h1>Template {self.template} not found</h1>';"
            self.webview.page().runJavaScript(script)
        except Exception as e:
            print(f"Error updating display: {e}")

    def template_content(self):
        """Get the content of the template file"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "templates", f"{self.template}.html")
        with open(template_path, "r") as f:
            return f.read()

    def start_fade_out(self):
        """Start the fade-out animation"""
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(self.fade_duration)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.finished.connect(self.make_invisible)
        self.anim.start()
    
    def make_invisible(self):
        """Make the window invisible but don't actually hide it"""
        # Instead of calling super().hide(), we'll just make the window transparent
        # but keep it technically visible to the system
        self.setWindowOpacity(0.0)
        
        # Force a repaint of parent widgets to ensure the transparency takes effect
        if self.parentWidget():
            self.parentWidget().update()
    
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
        
        # Send parameters as JSON
        params = {
            'template': args.template,
            'value': args.value,
            'duration': args.duration,
            'fade': args.fade,
            'width': args.width,
            'height': args.height,
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
    parser.add_argument("--duration", type=int, default=2000, help="Display duration in ms")
    parser.add_argument("--fade", type=int, default=500, help="Fade-out duration in ms")
    parser.add_argument("--width", type=int, default=300, help="Window width in pixels")
    parser.add_argument("--height", type=int, default=300, help="Window height in pixels")
    args = parser.parse_args()

    # Try to send update to existing server
    if send_update_to_server(args):
        print("Update sent to existing server")
        sys.exit(0)
    
    print("Starting new OSD server")
    app = QApplication(sys.argv)
    window = OSDWindow()
    
    # Initialize content but don't show window yet
    window.setWindowOpacity(0)  # Start invisible
    window.template = args.template
    window.value = args.value
    window.duration = args.duration
    window.fade_duration = args.fade
    window.muted = args.muted
    
    # Start the event loop without explicitly showing the window
    sys.exit(app.exec_())
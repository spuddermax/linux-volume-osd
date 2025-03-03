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
import subprocess
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineScript
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, QPoint, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QScreen, QCursor
from PyQt5.QtWebChannel import QWebChannel

# Constants
PORT = 9876  # Fixed port for IPC
LOCK_FILE = os.path.join(tempfile.gettempdir(), 'show_osd.lock')
DEFAULT_SETTINGS = {
    "window_width": 420,
    "window_height": 200,
    "x_offset": 0,
    "y_offset": 1,
    "duration": 2000,
    "volume_step": 4
}
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osd_settings.json")
MAX_VOLUME = 150
MAX_VOLUME_STEP = 20

# Setup logging
def setup_logging():
    """Setup logging with fallback to user's home directory if needed"""
    log_file = '/var/log/show_osd.log'
    try:
        # Try to create a log file with world-writable permissions
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                pass
            os.chmod(log_file, 0o666)  # World-writable

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    except Exception as e:
        # Fallback to user's home directory if can't write to /var/log
        user_log_file = os.path.expanduser("~/show_osd.log")
        logging.basicConfig(
            filename=user_log_file,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logging.error(f"Could not use {log_file}, falling back to {user_log_file}: {e}")
        log_file = user_log_file
    
    logging.debug("=== OSD Application Requested ===")
    return log_file

LOG_FILE = setup_logging()

@dataclass
class OsdArgs:
    """Data class to hold OSD arguments"""
    template: str = ""
    value: float = 0.0
    muted: bool = False
    sinks: str = "[]"
    debug: bool = False

def load_settings():
    """Load settings from JSON file or use defaults"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Make sure we have all default settings
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = value
                
                # Enforce MAX_VOLUME_STEP limit
                settings["volume_step"] = min(settings["volume_step"], MAX_VOLUME_STEP)
                
                return settings
        else:
            # Create default settings file if it doesn't exist
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(DEFAULT_SETTINGS, f, indent=4)
                
        return DEFAULT_SETTINGS.copy()
    
    except Exception as e:
        logging.error(f"Error loading settings: {e}")
    
    # Return defaults if we can't load settings
    return DEFAULT_SETTINGS.copy()

def get_active_sink():
    """Get the currently active audio sink"""
    try:
        result = subprocess.run(['pactl', 'info'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if line.startswith("Default Sink:"):
                sink = line.split(":", 1)[1].strip()
                if sink:
                    logging.debug(f"Found active sink: {sink}")
                    return sink
        
        logging.error("No sink found in pactl info")
        return None
    except Exception as e:
        logging.error(f"Error getting active sink: {e}")
        return None

def get_sink_volume(sink):
    """Get the current volume of the specified sink"""
    try:
        result = subprocess.run(['pactl', 'get-sink-volume', sink], capture_output=True, text=True)
        # Extract volume percentage from output like: "Volume: front-left: 22282 /  34% / -28.11 dB,   front-right: 22282 /  34% / -28.11 dB"
        match = re.search(r'(\d+)%', result.stdout)
        if match:
            volume = int(match.group(1))
            logging.debug(f"Current volume for sink {sink}: {volume}%")
            return volume
        else:
            logging.error(f"Could not parse volume from: {result.stdout}")
            return 0
    except Exception as e:
        logging.error(f"Error getting sink volume: {e}")
        return 0

def is_sink_muted(sink):
    """Check if the specified sink is muted"""
    try:
        result = subprocess.run(['pactl', 'get-sink-mute', sink], capture_output=True, text=True)
        muted = "yes" in result.stdout
        logging.debug(f"Sink {sink} mute status: {muted}")
        return muted
    except Exception as e:
        logging.error(f"Error checking if sink is muted: {e}")
        return False

def set_sink_volume(sink, volume):
    """Set the volume of the specified sink"""
    try:
        # Clamp volume between 0 and MAX_VOLUME
        volume = max(0, min(MAX_VOLUME, volume))
        logging.debug(f"Setting sink {sink} volume to {volume}%")
        subprocess.run(['pactl', 'set-sink-volume', sink, f"{volume}%"], capture_output=True, text=True)
        return volume
    except Exception as e:
        logging.error(f"Error setting sink volume: {e}")
        return None

def set_sink_mute(sink, mute):
    """Set the mute state of the specified sink"""
    try:
        logging.debug(f"Setting sink {sink} mute to {mute}")
        mute_val = "1" if mute else "0"
        subprocess.run(['pactl', 'set-sink-mute', sink, mute_val], capture_output=True, text=True)
        return True
    except Exception as e:
        logging.error(f"Error setting sink mute: {e}")
        return False

def get_available_sinks(active_sink):
    """Get a list of all available sinks and format as JSON"""
    try:
        result = subprocess.run(['pactl', 'list', 'sinks'], capture_output=True, text=True)
        
        sinks = []
        current_sink = {}
        
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                if current_sink and "name" in current_sink:
                    sinks.append(current_sink)
                current_sink = {"name": line.split(":", 1)[1].strip()}
                current_sink["active"] = (current_sink["name"] == active_sink)
            elif line.startswith("Description:") and "name" in current_sink:
                current_sink["description"] = line.split(":", 1)[1].strip()
        
        # Add the last sink
        if current_sink and "name" in current_sink and "description" in current_sink:
            sinks.append(current_sink)
            
        logging.debug(f"Found {len(sinks)} audio sinks")
        # sort the sinks by description
        sinks = sorted(sinks, key=lambda x: x['description'])
        return sinks
    except Exception as e:
        logging.error(f"Error getting available sinks: {e}")
        return []

def create_osd_args(template, value, muted=False, debug=False):
    """Create a common OSD arguments object"""
    sink = get_active_sink()
    if not sink:
        logging.error("No sink found")
        return None
        
    sinks_json = json.dumps(get_available_sinks(sink))
    
    args = OsdArgs()
    args.template = template
    args.value = value
    args.muted = muted
    args.sinks = sinks_json
    args.debug = debug
    
    return args

def display_osd(args):
    """Send update to OSD server or start a new one"""
    if not send_update_to_server(args):
        logging.info(f"Starting OSD for {args.template}")
        start_osd(args)
    return True

def volume_up():
    """Increase volume by VOLUME_STEP% and show OSD"""
    sink = get_active_sink()
    if not sink:
        logging.error("No sink found")
        return False
        
    current_volume = get_sink_volume(sink)
    settings = load_settings()
    new_volume = min(current_volume + settings["volume_step"], MAX_VOLUME)
    
    set_sink_volume(sink, new_volume)
    muted = is_sink_muted(sink)
    
    args = create_osd_args("volume", new_volume, muted)
    return display_osd(args)

def volume_down():
    """Decrease volume by VOLUME_STEP% and show OSD"""
    sink = get_active_sink()
    if not sink:
        logging.error("No sink found")
        return False
        
    current_volume = get_sink_volume(sink)
    settings = load_settings()
    new_volume = max(current_volume - settings["volume_step"], 0)
    
    set_sink_volume(sink, new_volume)
    muted = is_sink_muted(sink)
    
    args = create_osd_args("volume", new_volume, muted)
    return display_osd(args)

def volume_mute():
    """Toggle mute status and show OSD"""
    sink = get_active_sink()
    if not sink:
        logging.error("No sink found")
        return False
    
    current_volume = get_sink_volume(sink)
    muted = is_sink_muted(sink)
    
    # Toggle mute
    set_sink_mute(sink, not muted)
    muted = not muted
    
    args = create_osd_args("volume", current_volume, muted)
    return display_osd(args)

def clean_up_old_instance():
    """Clean up any existing instance"""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, 'r') as f:
                old_pid = f.read().strip()
                logging.warning(f"Found old lock file with PID {old_pid}, attempting cleanup")
                try:
                    old_pid = int(old_pid)
                    os.kill(old_pid, signal.SIGKILL)
                    logging.info(f"Killed old process with PID {old_pid}")
                except (ValueError, ProcessLookupError):
                    logging.info("Old process not running, continuing")
                except Exception as e:
                    logging.warning(f"Error killing old process: {e}")
            os.unlink(LOCK_FILE)
    except Exception as e:
        logging.warning(f"Error cleaning up old lock file: {e}")

def create_lock_file():
    """Create a lock file to indicate the server is running"""
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logging.debug(f"Created lock file at {LOCK_FILE}")
    except Exception as e:
        logging.warning(f"Could not create lock file: {e}")

def start_osd(args):
    """Start OSD application with given arguments"""
    # First make sure there are no other running instances
    clean_up_old_instance()
    
    # Create application
    app = QApplication(sys.argv)
    
    # Set application name for user settings
    app.setApplicationName("VolumeOSD")
    app.setOrganizationName("VolumeOSD")
    
    # Enable high-DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Create main window, run app
    window = OSDWindow()
    
    # Update content with provided arguments
    window.template = args.template
    window.value = args.value
    window.muted = args.muted
    window.sinks = args.sinks
    
    # Show window (after values are set)
    window.show()
    
    # Make sure window appears on top
    window.raise_()
    window.activateWindow()
    
    # Position window according to settings
    window.position_window()
    
    # Main event loop
    exit_code = app.exec_()
    
    # Proper cleanup upon exit
    logging.info("Application exiting, cleaning up...")
    if hasattr(window, 'cleanup'):
        window.cleanup()
    
    sys.exit(exit_code)

class SignalReceiver(QObject):
    # Signal to update the OSD from the main Qt thread
    update_signal = pyqtSignal(str, float, int, int, int, int, bool, str)

class JsBridge(QObject):
    """Bridge class for JavaScript to Python communication"""
    
    def __init__(self, window):
        super().__init__()
        self.window = window
    
    @pyqtSlot(str)
    def selectSink(self, sink_name):
        """Method exposed to JavaScript to select a sink"""
        logging.debug(f"JsBridge: Received sink selection request for {sink_name}")
        self.window.select_sink(sink_name)

    @pyqtSlot()
    def pinWindow(self):
        """Method exposed to JavaScript to pin the window"""
        logging.debug("JsBridge: Received pin window request")
        self.window.pinned = not self.window.pinned
        # If self.window.pinned is False, reset the timer to hide the window
        if not self.window.pinned:
            logging.info("JsBridge: Window is not pinned, resetting timer")
            self.window.close_timer.start(self.window.duration)
        else:
            logging.info("JsBridge: Window is pinned, stopping timer")
            self.window.close_timer.stop()
    
    @pyqtSlot(str)
    def log(self, message):
        """Method to log messages from JavaScript"""
        logging.debug(f"JS Bridge Log: {message}")

class OSDWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        logging.debug("Initializing OSDWindow")
        self.template = None
        self.value = None
        self.duration = 2000
        self.close_timer = None
        self.page_loaded = False
        self.server = None
        self.server_thread = None
        self.muted = False
        self.sinks = "[]"  # Default empty JSON array for sinks
        self.current_sink = None
        self.pinned = False
        
        # Create JS bridge
        self.js_bridge = JsBridge(self)
        
        # Setup signal receiver
        self.signal_receiver = SignalReceiver()
        self.signal_receiver.update_signal.connect(self.update_content)
        
        # Setup UI
        self.setup_ui()
        
        # Make the window sticky (visible on all workspaces)
        self.ensure_window_sticky()
        
        # Create lock file to signal we're running
        create_lock_file()
        
        # Start server in separate thread
        self.start_server()
        
        # Register cleanup handler for clean exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logging.debug("OSDWindow initialization complete")
    
    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        logging.info(f"Received signal {signum}, cleaning up")
        self.cleanup()
        sys.exit(0)

    def setup_ui(self):
        """Initialize the UI components"""
        logging.debug("Setting up UI components")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Load settings for window size
        settings = load_settings()
        window_width = settings.get("window_width", 480)
        window_height = settings.get("window_height", 200)
        
        self.webview = QWebEngineView(self)
        
        # Create and set custom page with proper error handling
        class WebEnginePage(QWebEnginePage):
            def javaScriptConsoleMessage(self_, level, message, lineNumber, sourceID):
                levels = {
                    0: logging.DEBUG,
                    1: logging.INFO,
                    2: logging.WARNING,
                    3: logging.ERROR
                }
                logging.log(levels.get(level, logging.DEBUG), f"JS: {message} (line {lineNumber}, source: {sourceID})")
        
        self.page = WebEnginePage(self.webview)
        
        # Set up web channel for JavaScript to Python communication
        # IMPORTANT: Create the channel and register the bridge object BEFORE setting the page
        self.channel = QWebChannel()
        self.js_bridge = JsBridge(self)
        self.channel.registerObject("bridge", self.js_bridge)
        logging.debug("Bridge object registered with WebChannel")
        
        # Set the WebChannel on the page
        self.page.setWebChannel(self.channel)
        logging.debug("WebChannel set on page")
        
        # Now set the page on the webview
        self.webview.setPage(self.page)
        
        # Set transparent background
        self.webview.page().setBackgroundColor(Qt.transparent)
        
        # Connect load finished signal
        self.webview.loadFinished.connect(self.on_load_finished)
        
        # Enable debug output for WebEngine
        os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
        
        # Set fixed size from settings
        self.webview.setFixedSize(window_width, window_height)
        self.resize(window_width, window_height)
        
        # Use layout to let window resize with content
        self.setCentralWidget(self.webview)
        
        # Force window to use the exact size we set
        self.setFixedSize(window_width, window_height)

        # Set up WebChannel JavaScript
        self.setup_webchannel_js()

        # Copy our bridge_tester.js to the templates folder if it doesn't exist
        self.copy_bridge_tester_js()

        # Load the index.html template from file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        index_path = os.path.join(script_dir, "templates", "index.html")
        
        if os.path.exists(index_path):
            logging.debug(f"Loading template from {index_path}")
            self.webview.load(QUrl.fromLocalFile(index_path))
        else:
            logging.error(f"Template file not found: {index_path}")
            self.webview.setHtml("<html><body><h1>Error: index.html not found</h1></body></html>")
    
    def copy_bridge_tester_js(self):
        """Copy bridge_tester.js to the templates folder if it doesn't exist"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            tester_js_path = os.path.join(script_dir, "templates", "bridge_tester.js")
            
            # Skip if file already exists
            if os.path.exists(tester_js_path):
                logging.debug("bridge_tester.js already exists")
                return
            
            # Check if we have the file in the same directory as the script
            source_path = os.path.join(script_dir, "bridge_tester.js")
            if os.path.exists(source_path):
                import shutil
                shutil.copy(source_path, tester_js_path)
                logging.debug(f"Copied bridge_tester.js to {tester_js_path}")
            else:
                # Create the file with minimal content
                with open(tester_js_path, 'w') as f:
                    f.write("""// Simple bridge tester
document.addEventListener('DOMContentLoaded', function() {
    console.log("Bridge tester loaded");
    var div = document.createElement('div');
    div.innerHTML = "Bridge: " + (window.bridge ? "Available" : "Not available");
    div.style.position = "absolute";
    div.style.top = "5px";
    div.style.left = "5px";
    div.style.fontSize = "10px";
    div.style.color = window.bridge ? "green" : "red";
    document.body.appendChild(div);
});
""")
                logging.debug(f"Created minimal bridge_tester.js at {tester_js_path}")
        except Exception as e:
            logging.error(f"Error setting up bridge_tester.js: {e}")
    
    def setup_webchannel_js(self):
        """Set up JavaScript for WebChannel communication"""
        script = QWebEngineScript()
        
        # Create the JavaScript code
        js_code = """
        // This script sets up the WebChannel for JavaScript to Python communication
        try {
            console.log("WebChannel transport script running");
            
            // Wait for page to be fully loaded
            document.addEventListener("DOMContentLoaded", function() {
                console.log("DOM content loaded, setting up WebChannel");
                setupWebChannel();
            });
            
            // Function to set up the WebChannel
            function setupWebChannel() {
                if (typeof QWebChannel === 'undefined') {
                    console.error("QWebChannel is not defined! Waiting for script to load...");
                    setTimeout(setupWebChannel, 100);
                    return;
                }
                
                if (!qt || !qt.webChannelTransport) {
                    console.error("Qt WebChannel transport not available yet, retrying...");
                    setTimeout(setupWebChannel, 100);
                    return;
                }
                
                try {
                    console.log("Creating QWebChannel with transport");
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        // Make the bridge object available globally
                        window.bridge = channel.objects.bridge;
                        console.log("WebChannel initialized, bridge object available: ", 
                                   window.bridge ? "YES" : "NO");
                        
                        // Set up the sink selection function using the bridge
                        window.sinkSelected = function(sinkName) {
                            console.log("Global sinkSelected initialized with: " + sinkName);
                            if (window.bridge) {
                                window.bridge.selectSink(sinkName);
                                return true;
                            } else {
                                console.error("Bridge not available for sink selection");
                                return false;
                            }
                        };
                        
                        // Let Python know WebChannel is ready
                        if (window.bridge) {
                            window.bridge.log("WebChannel setup complete in JavaScript");
                        }
                    });
                } catch (e) {
                    console.error("Error setting up WebChannel: " + e);
                }
            }
            
            // Try to set up immediately in case DOM is already loaded
            if (document.readyState === "complete" || document.readyState === "interactive") {
                console.log("Document already ready, setting up WebChannel immediately");
                setupWebChannel();
            }
        } catch (e) {
            console.error("Error in WebChannel setup script: " + e);
        }
        """
        
        script.setSourceCode(js_code)
        script.setName("webchannel.js")
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setRunsOnSubFrames(False)
        
        # Add the script to the page
        self.page.scripts().insert(script)
        logging.debug("WebChannel JavaScript injected")
    
    def start_server(self):
        """Start the server in a separate thread"""
        logging.debug("Starting IPC server thread")
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
                            sinks = params.get('sinks', '[]')
                            
                            # Update via signal to ensure thread safety
                            self.signal_receiver.update_signal.emit(
                                template, value, duration, fade, 0, 0, muted, sinks
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
    
    def update_content(self, template, value, duration, fade, width, height, muted=False, sinks="[]"):
        """Update the OSD content with new values"""
        self.template = template
        self.value = int(value)
        self.muted = muted
        self.sinks = sinks

        logging.debug(f"sinks={sinks}")
        
        # Load settings file (reload each time to pick up changes)
        settings = load_settings()
        self.duration = settings.get("duration", 2000)
        
        # Get window dimensions from settings
        window_width = settings.get("window_width", 480)
        window_height = settings.get("window_height", 200)
        
        # Update window size if changed in settings
        if self.width() != window_width or self.height() != window_height:
            print(f"Updating window size to {window_width}x{window_height} from settings")
            self.webview.setFixedSize(window_width, window_height)
            self.resize(window_width, window_height)
            self.setFixedSize(window_width, window_height)
        
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
            
            # Make sure window is sticky (visible on all workspaces) each time it's shown
            self.ensure_window_sticky()
        
        # Set new close timer
        self.close_timer = QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.hide_window)
        if not self.pinned:
            logging.debug("OSDWindow: window is not pinned, starting close timer")
            self.close_timer.start(self.duration)
        else:
            logging.debug("OSDWindow: window is pinned, not starting close timer")
    
    def position_window(self):
        """Position the window on the correct screen"""
        # If pinned, don't move the window
        if self.pinned:
            return

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
        logging.debug("WebView finished loading")
        self.page_loaded = True
        
        if self.template and self.value is not None:
            self.update_display()
            
            # Set fixed window size instead of adjusting to content
            settings = load_settings()
            window_width = settings.get("window_width", 480)
            window_height = settings.get("window_height", 200)
            
            # Apply size to webview and window
            self.webview.setFixedSize(window_width, window_height)
            self.resize(window_width, window_height)
            self.setFixedSize(window_width, window_height)
            
            # Position window
            self.position_window()
            
            # Load duration from settings
            self.duration = settings.get("duration", 2000)
            
            # Set timer for hiding
            self.close_timer = QTimer()
            self.close_timer.setSingleShot(True)
            self.close_timer.timeout.connect(self.hide_window)
            self.close_timer.start(self.duration)
            logging.debug(f"Window will auto-hide in {self.duration}ms")
    
    def update_display(self):
        """Update the HTML content with new values"""
        logging.debug(f"Updating display with template={self.template}, value={self.value}, muted={self.muted}, pinned={self.pinned}")
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
                document.getElementById('pin-icon').classList.toggle('pinned', {str(self.pinned).lower()});
                
                // Update sink devices list if element exists
                if (document.getElementById('sink-devices')) {{
                    const sinks = {self.sinks};
                    if (sinks && sinks.length > 0) {{
                        let sinksHtml = "";
                        sinks.forEach(sink => {{
                            const activeClass = sink.active ? "active-sink" : "";
                            const checkmark = sink.active ? "✓ " : "";
                            sinksHtml += `<div class="sink-item ${{activeClass}}" data-sink-name="${{sink.name}}">${{checkmark}}${{sink.description}}</div>`;
                        }});
                        document.getElementById('sink-devices').innerHTML = sinksHtml;
                        
                        // Add a click handler to the pin icon
                        document.getElementById('pin-icon').addEventListener('click', function(event) {{
                            console.log('Pin icon clicked!');
                            // Toggle the pin by adding or removing the 'pinned' class
                            const pinIcon = document.getElementById('pin-icon');
                            pinIcon.classList.toggle('pinned');
                            // Try with WebChannel first
                            if (window.bridge) {{
                                console.log('Using bridge.pinWindow');
                                window.bridge.pinWindow();
                            }} else if (window.pinWindow) {{
                                console.log('Using window.pinWindow');
                                window.pinWindow();
                            }} else {{
                                console.error('No pinWindow method available');
                            }}
                        }});

                        // Add click handlers directly to each sink item for redundancy
                        setTimeout(() => {{
                            const sinkItems = document.querySelectorAll('.sink-item');
                            console.log('Found ' + sinkItems.length + ' sink items');
                            sinkItems.forEach(item => {{
                                if (!item.getAttribute('data-click-init')) {{
                                    item.setAttribute('data-click-init', 'true');
                                    item.addEventListener('click', function(event) {{
                                        const sinkName = this.getAttribute('data-sink-name');
                                        console.log('Sink clicked: ' + sinkName);
                                        if (sinkName && !this.classList.contains('active-sink')) {{
                                            console.log('Calling sinkSelected with: ' + sinkName);
                                            
                                            // Try with WebChannel first
                                            if (window.bridge) {{
                                                console.log('Using bridge.selectSink');
                                                window.bridge.selectSink(sinkName);
                                            }} else if (window.sinkSelected) {{
                                                // Fall back to window.sinkSelected if available
                                                console.log('Using window.sinkSelected');
                                                window.sinkSelected(sinkName);
                                            }} else {{
                                                console.error('No sink selection method available');
                                            }}
                                        }}
                                    }});
                                }}
                            }});
                        }}, 100); // Short delay to ensure DOM is ready
                    }}
                }}
                
                // Log completion
                console.log('Display update complete');
                """
                self.webview.page().runJavaScript(script, lambda result: logging.debug("Display update script executed"))
                
                # We no longer adjust size here - using fixed size from settings
            else:
                logging.warning("Could not extract head section from index.html")
        except FileNotFoundError as e:
            logging.error(f"Template error: {e}")
            script = f"document.body.innerHTML = '<h1>Template {self.template} not found</h1>';"
            self.webview.page().runJavaScript(script)
        except Exception as e:
            logging.error(f"Error updating display: {e}")

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
        logging.info("Cleaning up...")
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
        window_width = settings.get("window_width", 480)
        window_height = settings.get("window_height", 200)
        
        # Apply size to webview and window
        self.webview.setFixedSize(window_width, window_height)
        self.resize(window_width, window_height)
        self.setFixedSize(window_width, window_height)
        
        self.position_window()

    def ensure_window_sticky(self):
        """Make the window sticky (visible on all workspaces)"""
        if QApplication.instance().platformName() == "xcb":
            try:
                import Xlib
                import Xlib.display
                display = Xlib.display.Display()
                window_id = int(self.winId())
                window = display.create_resource_object('window', window_id)
                
                # Set _NET_WM_DESKTOP to all desktops
                desktop_atom = display.intern_atom('_NET_WM_DESKTOP')
                window.change_property(desktop_atom, Xlib.Xatom.CARDINAL, 32, [0xFFFFFFFF])
                
                # Also set _NET_WM_STATE_STICKY for better compatibility
                state_atom = display.intern_atom('_NET_WM_STATE')
                sticky_atom = display.intern_atom('_NET_WM_STATE_STICKY')
                window.change_property(state_atom, Xlib.Xatom.ATOM, 32, [sticky_atom])
                
                display.sync()
                logging.debug("Window set to visible on all workspaces")
            except ImportError:
                logging.warning("python-xlib not installed, cannot set window to all workspaces")
            except Exception as e:
                logging.error(f"Error setting window to all workspaces: {e}")

    def pin_window(self):
        """Pin the window to the current workspace"""
        logging.info("OSDWindow: Pinning window")

    def select_sink(self, sink_name):
        """Set the specified sink as the default audio sink"""
        logging.debug(f"Selecting sink: {sink_name}")
        try:
            if sink_name:
                # Make sure we maintain the current mute state before changing the sink
                if self.muted:
                    cmd = ['pactl', 'set-sink-mute', sink_name, '1']
                    logging.debug(f"Running command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        logging.error(f"Command failed with return code {result.returncode}")
                else:
                    cmd = ['pactl', 'set-sink-mute', sink_name, '0']
                    logging.debug(f"Running command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        logging.error(f"Command failed with return code {result.returncode}")

                # Log the command we're about to run
                cmd = ['pactl', 'set-default-sink', sink_name]
                logging.debug(f"Running command: {' '.join(cmd)}")
                
                # Run the command with detailed output capture
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logging.error(f"Command failed with return code {result.returncode}")
                    logging.error(f"Error output: {result.stderr}")
                else:
                    logging.debug(f"Command succeeded: {result.stdout}")
                
                # Update the current sink value
                info_cmd = ['pactl', 'info']
                logging.debug(f"Getting sink info with: {' '.join(info_cmd)}")
                result = subprocess.run(info_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    output = result.stdout
                    logging.debug(f"pactl info output: {output}")
                    for line in output.splitlines():
                        if "Default Sink:" in line:
                            self.current_sink = line.split(":")[-1].strip()
                            logging.debug(f"Current sink updated to: {self.current_sink}")
                            break
                else:
                    logging.error(f"Failed to get sink info: {result.stderr}")
                
                # Update the display to reflect the new active sink
                # Instead of waiting for next volume change, refresh sink list now
                try:
                    # Get the updated list of sinks with the newly active one marked
                    sink_cmd = [
                        'pactl', 'list', 'sinks', 
                        '|', 'grep', '-E', '"Name:|Description:"', 
                        '|', 'grep', '-v', '"Monitor"'
                    ]
                    # Use a more direct approach with a shell command to get sink info including the volume level
                    sink_cmd_str = " ".join(sink_cmd)
                    raw_sinks = subprocess.check_output(
                        f"pactl list sinks | grep -E 'Name:|Description:|Volume:' | grep -v 'Monitor'", 
                        shell=True, text=True
                    )
                    
                    # Process the output similar to the shell scripts
                    current_name = None
                    current_desc = None
                    current_volume = None
                    sink_data = []
                    
                    for line in raw_sinks.splitlines():
                        if line.strip().startswith("Name:"):
                            current_name = line.split(":", 1)[1].strip()
                        elif line.strip().startswith("Description:"):
                            current_desc = line.split(":", 1)[1].strip()
                        elif line.strip().startswith("Volume:"):
                            # Volume is in the format "Volume: front-left: 22282 /  34% / -28.11 dB,   front-right: 22282 /  34% / -28.11 dB"
                            # Extract the volume percentage with % stripped
                            current_volume = line.split(":", 1)[1].strip().split(" / ")[1].replace("%", "").strip()
                            logging.debug(f"Current volume: {current_volume}")
                            if current_name and current_desc and current_volume:
                                # Add to our list
                                logging.debug(f"Adding sink: {current_name}, {current_desc}, {current_volume}")
                                is_active = (current_name == sink_name)
                                if is_active:
                                    logging.debug(f"Setting active sink: {current_name}")
                                    self.value = int(current_volume)
                                sink_data.append({
                                    "name": current_name,
                                    "description": current_desc,
                                    "value": current_volume,
                                    "active": is_active
                                })

                                current_name = None
                                current_desc = None
                    
                    # Update the sinks property with the new JSON data
                    if sink_data:
                        # display in alphabetical order
                        sink_data.sort(key=lambda x: x['name'])
                        self.sinks = json.dumps(sink_data)
                        logging.debug(f"Updated sink list: {self.sinks}")
                        
                        # Refresh the display with the updated sink list
                        self.update_display()
                        logging.debug("Display refreshed with updated sink list")
                except Exception as e:
                    logging.error(f"Error refreshing sink list: {e}", exc_info=True)
                
                # Reset the close timer to give user time to see the notification
                if self.close_timer and self.close_timer.isActive():
                    self.close_timer.stop()
                    logging.debug("Stopped existing close timer")
                
                self.close_timer = QTimer()
                self.close_timer.setSingleShot(True)
                self.close_timer.timeout.connect(self.hide_window)
                if not self.pinned:
                    self.close_timer.start(self.duration)
                    logging.debug("Started new close timer with 4000ms duration")
                else:
                    logging.debug("Window is pinned, not starting close timer")
        except Exception as e:
            logging.error(f"Error changing sink: {e}", exc_info=True)
            # Show toast notification for error
            error_script = f"""
            if (window.showToast) {{
                window.showToast('Error switching audio output: {str(e).replace("'", "\\'")}', 3000);
            }}
            """
            self.webview.page().runJavaScript(error_script)

def server_accept_with_timeout(server, timeout):
    """Accept a connection with timeout handling"""
    try:
        server.settimeout(timeout)
        return server.accept()
    except socket.timeout:
        return None, None
    except Exception as e:
        logging.error(f"Accept error: {e}")
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
            'muted': args.muted,
            'sinks': args.sinks
        }
        client.send(json.dumps(params).encode('utf-8'))
        client.close()
        return True
    except Exception as e:
        logging.error(f"Failed to send update: {e}")
        # If server failed to respond, clean up the stale lock
        try:
            os.unlink(LOCK_FILE)
        except Exception:
            pass
        return False

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Display an OSD popup or control volume")
    
    # Add a command group
    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument("--volume-up", action="store_true", help="Increase volume by 2%")
    command_group.add_argument("--volume-down", action="store_true", help="Decrease volume by 2%")
    command_group.add_argument("--volume-mute", action="store_true", help="Toggle mute state")
    
    # Legacy OSD display arguments
    parser.add_argument("--template", help="HTML template name (e.g., volume)")
    parser.add_argument("--value", type=float, help="Value to display (e.g., volume percentage)")
    parser.add_argument("--muted", action="store_true", help="Show as muted (for volume)")
    parser.add_argument("--sinks", help="JSON array of available audio sinks")
    parser.add_argument("--debug", action="store_true", help="Enable extra debug mode")
    
    args = parser.parse_args()

    # Set extra debug mode if requested
    if args.debug:
        logging.info("Debug mode enabled")
        os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
    
    # Handle volume commands
    if args.volume_up:
        logging.info("Processing volume up command")
        volume_up()
        sys.exit(0)
    elif args.volume_down:
        logging.info("Processing volume down command")
        volume_down()
        sys.exit(0)
    elif args.volume_mute:
        logging.info("Processing volume mute command")
        volume_mute()
        sys.exit(0)
    
    # Legacy OSD display handling
    if not args.template:
        parser.error("--template is required unless a volume command is specified")
    if args.value is None:
        parser.error("--value is required unless a volume command is specified")
    
    # Convert args to OsdArgs dataclass
    osd_args = OsdArgs(
        template=args.template,
        value=args.value,
        muted=args.muted,
        sinks=args.sinks if args.sinks else "[]",
        debug=args.debug
    )
    
    # Try to send update to existing server
    if send_update_to_server(osd_args):
        logging.debug("Update sent to existing server")
        sys.exit(0)
    
    # If we get here, we need to start a new server
    logging.info("Starting new OSD server")
    
    start_osd(osd_args)

if __name__ == "__main__":
    main()
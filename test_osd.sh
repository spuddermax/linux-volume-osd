#!/bin/bash
# Test script for debugging the OSD application

# Kill any existing instances
echo "Killing any existing OSD processes..."
pkill -f show_osd.py || true

# Clear the log file
echo "Clearing the log file..."
sudo rm -f /var/log/show_osd.log
sudo touch /var/log/show_osd.log
sudo chmod 666 /var/log/show_osd.log

# Set up debugging environment
export QTWEBENGINE_REMOTE_DEBUGGING=9222

# Run the application with test data
echo "Starting OSD application with test data..."
./show_osd.py --template volume --value 50 --sinks '[{"name":"alsa_output.pci-0000_00_1b.0.analog-stereo", "description":"Built-in Audio", "active":true}, {"name":"alsa_output.usb-SteelSeries_SteelSeries_Arctis_7-00.analog-stereo", "description":"SteelSeries Arctis 7", "active":false}]' --debug

# Tail the log file in a new terminal window
echo "Opening log viewer..."
xterm -e "tail -f /var/log/show_osd.log" &

# Browser to debug WebEngine (Chromium based, must have Chrome/Chromium installed)
echo "Opening Chrome DevTools for WebEngine debugging..."
sleep 1 # Wait for the app to start
which google-chrome > /dev/null && google-chrome http://localhost:9222 || \
which chromium-browser > /dev/null && chromium-browser http://localhost:9222 || \
which chromium > /dev/null && chromium http://localhost:9222 || \
echo "Chrome/Chromium not found, cannot open DevTools" 
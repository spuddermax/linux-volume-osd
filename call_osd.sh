#!/bin/bash
# Wrapper script to run show_osd.py with correct environment

# Check if the log file exists and is writable, if not try to set it up
LOG_FILE="/var/log/show_osd.log"
if [ ! -w "$LOG_FILE" ]; then
    # Try to create log file with user permissions first
    if [ -d "/var/log" ] && [ -w "/var/log" ]; then
        touch "$LOG_FILE" 2>/dev/null && chmod 666 "$LOG_FILE" 2>/dev/null
    else
        # If that fails, try with sudo
        echo "Attempting to set up logging with sudo..."
        script_dir="$(dirname "$0")"
        sudo "$script_dir/setup_logging.sh" 2>/dev/null
    fi
fi

# Handle simple volume commands
if [ "$1" = "volume-up" ]; then
    # Forward to Python script with appropriate flag
    env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 "$(dirname "$0")/show_osd.py" --volume-up
    exit $?
elif [ "$1" = "volume-down" ]; then
    # Forward to Python script with appropriate flag
    env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 "$(dirname "$0")/show_osd.py" --volume-down
    exit $?
elif [ "$1" = "volume-mute" ]; then
    # Forward to Python script with appropriate flag
    env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 "$(dirname "$0")/show_osd.py" --volume-mute
    exit $?
fi

# Regular operation - pass all arguments to the Python script
env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 "$(dirname "$0")/show_osd.py" "$@" 
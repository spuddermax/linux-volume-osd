#!/bin/bash

LOG_FILE="/var/log/show_osd.log"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
	echo "Creating log file with proper permissions"
	touch "$LOG_FILE"
	chmod 666 "$LOG_FILE"
	echo "Log file created at $LOG_FILE with world-writable permissions"
else
	echo "Not running as root, attempting to create log file using sudo"
	# Try to create the log file using sudo
	sudo touch "$LOG_FILE" 2>/dev/null
	sudo chmod 666 "$LOG_FILE" 2>/dev/null
	
	# Check if we were successful
	if [ -w "$LOG_FILE" ]; then
		echo "Log file created successfully at $LOG_FILE"
	else
		echo "Warning: Could not create $LOG_FILE with write permissions"
		echo "The application will fall back to logging in your home directory"
	fi
fi

echo "Logging setup complete" 
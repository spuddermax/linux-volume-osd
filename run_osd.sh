#!/bin/bash
# Wrapper script to run show_osd.py with correct environment

# Unset problematic environment variables
env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 "$(dirname "$0")/show_osd.py" "$@" 
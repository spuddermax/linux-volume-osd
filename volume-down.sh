#!/bin/bash

# Find the active sink
SINK=$(pactl info | grep 'Default Sink' | cut -d' ' -f3)

# Ensure the sink exists
if [ -z "$SINK" ]; then
    echo "Sink not found!" >&2
    exit 1
fi

# Adjust volume down
CURRENT=$(pactl get-sink-volume "$SINK" | grep -o '[0-9]*%' | head -1 | tr -d '%')
NEW=$((CURRENT - 2))
if [ $NEW -gt 150 ]; then NEW=150; fi
if [ $NEW -lt 0 ]; then NEW=0; fi
pactl set-sink-volume "$SINK" "$NEW%"

# Get mute status
IS_MUTED=$(pactl get-sink-mute "$SINK" | grep -o "yes")

# Show OSD with cyan text, centered in a virtual 200x200 box
if [ "$IS_MUTED" = "yes" ]; then
    $(dirname "$0")/run_osd.sh --template volume --value $NEW --muted &
else
    $(dirname "$0")/run_osd.sh --template volume --value $NEW &
fi

#!/bin/bash

# Find the active sink
SINK=$(pactl info | grep 'Default Sink' | cut -d' ' -f3)

# Ensure the sink exists
if [ -z "$SINK" ]; then
    echo "Sink not found!" >&2
    exit 1
fi

# Get mute status
IS_MUTED=$(pactl get-sink-mute "$SINK" | grep -o "yes")

# Adjust volume up
CURRENT=$(pactl get-sink-volume "$SINK" | grep -o '[0-9]*%' | head -1 | tr -d '%')
NEW=$((CURRENT + 2))
if [ $NEW -gt 150 ]; then NEW=150; fi
if [ $NEW -lt 1 ]; then NEW=1; fi
pactl set-sink-volume "$SINK" "$NEW%"

if [ "$IS_MUTED" = "yes" ]; then
    $(dirname "$0")/run_osd.sh --template volume --value $NEW --muted &
else
    $(dirname "$0")/run_osd.sh --template volume --value $NEW &
fi

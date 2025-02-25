#!/bin/bash

# Find the active sink
SINK=$(pactl info | grep 'Default Sink' | cut -d' ' -f3)

# Ensure the sink exists
if [ -z "$SINK" ]; then
    echo "Sink not found!" >&2
    exit 1
fi

# Get current volume before making changes
CURRENT_VOL=$(pactl get-sink-volume "$SINK" | grep -oP '\d+(?=%)' | head -1)

# Get mute status
IS_MUTED=$(pactl get-sink-mute "$SINK" | grep -o "yes")

if [ "$IS_MUTED" = "yes" ]; then
    # Currently muted, unmute it
    pactl set-sink-mute "$SINK" 0
    $(dirname "$0")/run_osd.sh --template volume --value "$CURRENT_VOL" &
else
    # Currently unmuted, mute it
    pactl set-sink-mute "$SINK" 1

    # Show OSD with muted state
    $(dirname "$0")/run_osd.sh --template volume --value "$CURRENT_VOL" --muted &
fi
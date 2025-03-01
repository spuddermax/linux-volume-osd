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

# Get all sinks and their descriptions, then format as JSON array
SINKS=$(pactl list sinks | grep -E "Name:|Description:" | grep -v "Monitor" | awk '{
    if ($1 == "Name:") {
        name=$2;
    } else if ($1 == "Description:") {
        desc=substr($0, index($0,$2));
        printf "%s:%s\n", name, desc;
    }
}' | sort -k2 | awk -v active="$SINK" '{
    split($0, parts, ":");
    name = parts[1];
    desc = parts[2];
    if (name == active) { 
        printf "{\"name\":\"%s\",\"description\":\"%s\",\"active\":true},", name, desc;
    } else {
        printf "{\"name\":\"%s\",\"description\":\"%s\",\"active\":false},", name, desc;
    }
}' | sed 's/,$//')
SINKS="[$SINKS]"

# Show OSD with cyan text, centered in a virtual 200x200 box
if [ "$IS_MUTED" = "yes" ]; then
    $(dirname "$0")/run_osd.sh --template volume --value $NEW --muted --sinks "$SINKS" &
else
    $(dirname "$0")/run_osd.sh --template volume --value $NEW --sinks "$SINKS" &
fi

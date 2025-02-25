#!/bin/bash
# This script adjusts the volume setting to 2% of the maximum volume.
# It is used to reduce the volume of the system to a lower level when the
# default volume is too high for a given hardware configuration.
# It depends on the pw-cli tool to be installed and the PulseAudio sound
# system to be running, and you must supply the name of the sink to adjust.

# The volume level is set to 2% of the maximum volume.
VOLUME_LEVEL=0.02

# The name of the sink to adjust.
SINK_NAME="alsa_output.usb-GeneralPlus_USB_Audio_Device-00.analog-stereo"

# Run pw-dump and parse the JSON to find the object ID
SINK_ID=$(pw-dump | jq -r '.[] | select(.info.props."node.name" == "'"$SINK_NAME"'") | .id')

# Check if we found an ID, then output it
if [ -n "$SINK_ID" ]; then
    echo "$SINK_ID"
else
    echo "No object found with node.name '$SINK_NAME'"
    exit 1
fi

echo "Sink ID $SINK_ID found. Setting..."

# Set the volume to 2%
pw-cli set-param "$SINK_ID" Props '{ volume: '"$VOLUME_LEVEL"' }' 2>/dev/null || echo "Failed to set volume"

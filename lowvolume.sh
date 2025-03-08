#!/bin/bash
# Echo some best practice information about the purpose and use of this script
echo "Purpose: Set the percentage of volume level of a selected audio sink using PipeWire."
echo "Usage: Run the script and follow the prompts to select a sink and enter a volume level (0.001 to 1.000)."
echo "       Use --defaults to apply saved default settings."
echo

# Configuration file path
CONFIG_FILE="$HOME/.config/lowvolume.conf"

# Check if --defaults parameter was passed
USE_DEFAULTS=false
if [[ "$1" == "--defaults" ]]; then
    USE_DEFAULTS=true
fi

# Check for required dependencies
for cmd in jq; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: Required command '$cmd' not found."
        echo "You can install it first with the command 'sudo apt install $cmd'."
        echo "Would you like to attempt to install it now?"
        read -p "(Y/n): " INSTALL_CHOICE
        # Default to yes if no input is provided
        if [ -z "$INSTALL_CHOICE" ]; then
            INSTALL_CHOICE="Y"
        fi
        if [ "$INSTALL_CHOICE" = "Y" -o "$INSTALL_CHOICE" = "y" ]; then
            sudo apt install $cmd
            # echo proceeding with a new line
            echo "Installation complete. Proceeding..."
            echo
        else
            exit 1
        fi
    fi
done

# Get the available sink names and descriptions
SINK_LIST=$(pw-dump | jq -r '[.[] | select(.info.props."media.class" == "Audio/Sink") | {name: .info.props."node.name", description: .info.props."node.description", id: .id}]')

# If using defaults and the config file exists, read from it
if [[ "$USE_DEFAULTS" == true ]] && [[ -f "$CONFIG_FILE" ]]; then
    echo "Using default settings from $CONFIG_FILE"
    source "$CONFIG_FILE"
    
    # Verify the saved sink ID still exists
    if [[ -n "$DEFAULT_SINK_ID" ]]; then
        SINK_EXISTS=$(echo "$SINK_LIST" | jq -r '.[] | select(.id == '"$DEFAULT_SINK_ID"') | .id')
        if [[ -z "$SINK_EXISTS" ]]; then
            echo "Warning: Default sink no longer exists. Falling back to manual selection."
            USE_DEFAULTS=false
        else
            SINK_ID=$DEFAULT_SINK_ID
            SINK_NAME=$(echo "$SINK_LIST" | jq -r '.[] | select(.id == '"$SINK_ID"') | .name')
            SINK_DESCRIPTION=$(echo "$SINK_LIST" | jq -r '.[] | select(.id == '"$SINK_ID"') | .description')
            VOLUME_LEVEL=$DEFAULT_VOLUME
            echo "Using sink: $SINK_DESCRIPTION"
            echo "Using volume level: $VOLUME_LEVEL"
        fi
    else
        echo "Warning: Default sink not properly defined in config. Falling back to manual selection."
        USE_DEFAULTS=false
    fi
fi

# If not using defaults, prompt for user input
if [[ "$USE_DEFAULTS" == false ]]; then
    echo "Available sinks:"
    # Use jq to iterate through the array and display numbered options
    echo "$SINK_LIST" | jq -r 'to_entries | .[] | "\(.key + 1). \(.value.description)"'

    read -p "Enter the number of the sink you want to adjust: " SINK_NUMBER

    # Validate and get the selected sink
    SINK_INDEX=$((SINK_NUMBER - 1))
    SINK_NAME=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].name")
    SINK_DESCRIPTION=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].description")
    SINK_ID=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].id")

    # if a valid sink number is not entered, ask again until a valid number is entered
    while [ -z "$SINK_NAME" ] || [ "$SINK_NAME" = "null" ]; do
        read -p "Invalid sink number. Please try again: " SINK_NUMBER
        SINK_INDEX=$((SINK_NUMBER - 1))
        SINK_NAME=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].name")
        SINK_DESCRIPTION=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].description")
        SINK_ID=$(echo "$SINK_LIST" | jq -r ".[$SINK_INDEX].id")
    done

    # ask for the volume level
    read -p "Enter the volume level for $SINK_DESCRIPTION (between 0.001 and 1.000): " VOLUME_LEVEL

    # validate the volume level is a number between 0.001 and 1.000, non-leading zeros allowed
    while ! echo "$VOLUME_LEVEL" | grep -qE '^([0-9]+\.?[0-9]*|\.?[0-9]+)$' || \
          ! awk "BEGIN {exit !($VOLUME_LEVEL >= 0.001 && $VOLUME_LEVEL <= 1.000)}"; do
        read -p "Invalid volume level. Please try again: " VOLUME_LEVEL
    done
fi

echo "Setting volume to $VOLUME_LEVEL..."

# Set the volume to the percentage of the maximum volume without showing the command output
pw-cli set-param "$SINK_ID" Props '{ volume: '"$VOLUME_LEVEL"' }' 2>/dev/null || echo "Failed to set volume"

# If we're not using defaults, ask if user wants to save these settings as defaults
if [[ "$USE_DEFAULTS" == false ]]; then
    read -p "Do you want to save these settings as defaults? (y/N): " SAVE_DEFAULTS
    if [[ "$SAVE_DEFAULTS" =~ ^[Yy]$ ]]; then
        # Ensure directory exists
        mkdir -p "$(dirname "$CONFIG_FILE")"
        
        # Save to config file
        cat > "$CONFIG_FILE" << EOF
# Default lowvolume settings
DEFAULT_SINK_ID=$SINK_ID
DEFAULT_VOLUME=$VOLUME_LEVEL
EOF
        echo "Settings saved to $CONFIG_FILE"
        echo "You can use them next time with: $(basename "$0") --defaults"
    fi
fi

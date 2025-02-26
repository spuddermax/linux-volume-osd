# Linux Volume OSD Popup Project

A Python-based On-Screen Display (OSD) for volume control using PyQt5 and QtWebEngine.

## Features

- Displays volume changes with a visual popup.
- Supports muted state with dedicated icon and messaging.
- Simple HTML and CSS styling for ease of customization.
- Uses a persistent server to update content smoothly.
- Persists across all Workspace, and appears on the screen where the mouse cursor resides.
- Designed for Linux and integrated with Pipewire.
- Tested to run successfully in Mint 22 MATE and Mint 22.1 Cinnamon.

## Installation Requirements

- **Python 3.6+**
- **PyQt5** (with QtWebEngine support)
- Linux desktop environment (X11 or Wayland)
- **Additional Packages:**  
  Install on Debian/Ubuntu with:
  ```bash
  sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine
  ```
## Screenshots

OSD Popup Example

![OSD Popup Example](screenshots/osd_64.png)


OSD Muted Example

![OSD Muted Example](screenshots/osd_64_muted.png)


OSD Excess Volume Example

![OSD Excess Volume Example](screenshots/osd_130_muted.png)

OSD Opacity Example

![OSD Excess Volume Example](screenshots/osd_36_opacity.png)

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/spuddermax/linux-volume-osd.git
   cd linux-volume-osd
   ```

2. Make sure the scripts are executable:
   ```bash
   chmod +x run_osd.sh show_osd.py volume-up.sh volume-down.sh volume-mute.sh lowvolume.sh
   ```

3. To run the OSD run the server wrapper script directly, or run any of the three volume adjustment scripts and the server will be started automatically, e.g.:

Volume up:
   ```bash
   ./volume-up.sh
   ```

Run the server directly (This will start the server in the background, and you will need to use a kill command or kill it from the System Monitor if you want it to stop. Better handling of this to come later, I hope):
   ```bash
   ./run_osd.sh --template volume --value 75
   ```

## Bonus Script

An optional low volume adjuster script is included, `./lowvolume.sh`, and was created to allow one to adjust the
low-end volume on headphones or whatever device one might need. The low-end volume was found to be too loud, and
dropping the volume to around 20% in the case in question would be too loud for the bottom end, but going less
than 20% the sound would mute. Thus, this was built so at least at around 20% the volume is barely audible.
Use at your own discretion.

## Usage

- **Volume Up:** `./volume-up.sh`  
- **Volume Down:** `./volume-down.sh`  
- **Mute/Unmute:** `./volume-mute.sh`  
- **Set Low Volume (optional):** `./lowvolume.sh`  

## Configuration

The OSD can be configured using the `osd_settings.json` file which is automatically created on first run. This file allows you to customize:

- `x_offset`: Horizontal position of the OSD (0 for center, positive values offset from right edge, negative values offset from left edge)
- `y_offset`: Vertical position of the OSD (0 for center, positive values offset from bottom edge, negative values offset from top edge)
- `duration`: How long the OSD remains visible (in milliseconds)

Example settings file:
```json
{
    "x_offset": 0,
    "y_offset": 40,
    "duration": 2000
}
```

Changes to the settings file take effect immediately without needing to restart the server.

## Command-line Arguments

The OSD supports the following command-line arguments:

- `--template`: HTML template name (e.g., volume)
- `--value`: Value to display (e.g., volume percentage)
- `--muted`: Flag to show the muted state (for volume)

Note: Display duration is controlled via the settings file.

## Customization

The OSD appearance can be customized by:

1. Editing the HTML templates in the `templates/` directory
2. Modifying CSS styles within these templates
3. Creating new templates for different types of notifications

The content div in `index.html` controls the main dimensions of the OSD window.

## Window Positioning

The OSD will automatically:
- Appear on the screen where your cursor is currently located
- Position itself according to the x_offset and y_offset values in the settings file
- Resize itself based on the content of the template

Positioning Guide:
- Center (both axes): x_offset=0, y_offset=0
- Top-right corner: x_offset=40, y_offset=-40
- Bottom-left corner: x_offset=-40, y_offset=40

## Key Bindings

You can create your own custom key bindings to replace the default volume controls of your system as desired.
Ask Google or your favorite AI how to do this if you're not sure.

## Contributing

Feel free to open issues, submit pull requests, or contribute with new features. Please review our [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
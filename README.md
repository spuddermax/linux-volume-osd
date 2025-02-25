# OSD Popup Project

A Python-based On-Screen Display (OSD) for volume control using PyQt5 and QtWebEngine.

## Features

- Displays volume changes with a visual popup.
- Supports muted state with dedicated icon and messaging.
- Uses a persistent server to update content smoothly.
- Designed for Linux (X11/Wayland) and integrated with PulseAudio.

## Installation Requirements

- **Python 3.6+**
- **PyQt5** (with QtWebEngine support)
- Linux desktop environment (X11 or Wayland)
- **Additional Packages:**  
  Install on Debian/Ubuntu with:
  ```bash
  sudo apt install python3 python3-pip python3-pyqt5 python3-pyqt5.qtwebengine
  ```

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/my-osd-project.git
   cd my-osd-project
   ```

2. Make sure the scripts are executable:
   ```bash
   chmod +x run_osd.sh show_osd.py volume-up.sh volume-down.sh volume-mute.sh lowvolume.sh
   ```

3. To run the OSD:
   ```bash
   ./run_osd.sh --template volume --value 75
   ```

## Usage

- **Volume Up:** `./volume-up.sh`  
- **Volume Down:** `./volume-down.sh`  
- **Mute/Unmute:** `./volume-mute.sh`  
- **Set Low Volume (optional):** `./lowvolume.sh`  

## Contributing

Feel free to open issues, submit pull requests, or contribute with new features. Please review our [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
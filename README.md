# Automated Followspot System

A comprehensive multi-camera IR beacon tracking system with automated followspot capabilities, designed for live performance applications.

## Features

- **Dual Stack Architecture**: Separate Control and Node stacks for flexible deployment
- **GUI Launcher**: Comprehensive graphical interface for installation, configuration, and management
- **Real-time Video Processing**: WebRTC streaming with low-latency IR beacon detection
- **Multi-Camera Support**: Composite video feeds from multiple camera sources
- **Demo Mode**: Full simulation mode for testing without hardware
- **Automated Installation**: Guided installation process with dependency management
- **System Diagnostics**: Built-in health checks and maintenance tools
- **Built-in Help System**: Independent help window with keyboard shortcuts and operator guidelines

## Quick Start

### 1. Launch the System (GUI by Default)

```bash
python launcher.py
# OR
./followspot
```

The system launches with a graphical interface by default, providing:
- Installing Control and Node stacks
- Managing dependencies  
- Configuration management
- System diagnostics
- Running applications

### 2. Command Line Installation (Optional)

For control stack (camera management and tracking):
```bash
python setup.py  # Choose option 1
# OR
python launcher.py --install-deps control
```

For node stack (camera server):
```bash
python setup.py  # Choose option 2
# OR
python launcher.py --install-deps node
```

### 3. Quick Launch Options

```bash
# Launch GUI interface (default behavior)
python launcher.py
./followspot

# Use command-line interface
python launcher.py --cli
./followspot --cli

# Launch camera configuration
python launcher.py --configure
./followspot --configure

# Run in demo mode (no hardware required)
python launcher.py --demo
./followspot --demo

# Run live mode
python launcher.py --run
./followspot --run

# Check system status
python launcher.py --status
./followspot --status

# Start node server
python launcher.py --node
./followspot --node
```

## System Architecture

### Control Stack
The control stack manages camera feeds, performs IR beacon detection, and provides the user interface:

- **Camera Aggregator**: Manages multiple camera connections via WebRTC
- **IR Beacon Detection**: Real-time detection and tracking algorithms
- **Configuration GUI**: Camera setup and calibration interface
- **Video Display**: Composite video output with overlay information
- **Demo Mode**: Simulated cameras with moving beacons for testing
- **Help System**: Independent help window accessible via Help menu or 'H' key with complete keyboard shortcuts reference

**Key Files:**
- `control/main.py` - Main application entry point
- `control/camera_aggregator.py` - Multi-camera management
- `control/camera_config_gui.py` - Configuration interface
- `control/video_display_gui.py` - Video display GUI
- `control/demo_mode.py` - Demo/simulation mode

### Node Stack
The node stack runs on camera devices (typically Raspberry Pi) to stream video:

- **Camera Server**: WebRTC streaming server for camera feeds
- **Hardware Integration**: Raspberry Pi camera module support
- **Network Streaming**: Low-latency video transmission
- **Remote Management**: Command-line interface for headless operation

**Key Files:**
- `node/server.py` - Camera streaming server
- `node/README.md` - Node-specific documentation

### Launcher System
Unified management interface for both stacks:

- **GUI Launcher** (`launcher_gui.py`): Full graphical management interface
- **CLI Launcher** (`launcher.py`): Command-line interface and interactive menus
- **Setup Script** (`setup.py`): Dependency installation utility
- **Configuration** (`launcher_config.json`): System state tracking

## Installation Modes

### Control Stack Installation
When you install the Control Stack, the launcher provides these options:

1. **Launch Configuration**: Set up camera connections and layout
2. **Offline Mode**: Run with demo cameras (no hardware required)
3. **Live Mode**: Connect to real cameras for operation

Additional maintenance options:
- Repair installation (reinstall dependencies)
- Uninstall stack

### Node Stack Installation
When you install the Node Stack, the launcher provides these options:

1. **Start/Stop Node Server**: Manual server control
2. **Add to Cron**: Automatic startup at boot (Linux/Pi)
3. **Diagnostics**: System health checks
4. **Repair**: Reinstall dependencies
5. **Reinstall**: Complete reinstallation
6. **Uninstall**: Remove stack

## Configuration

### Camera Configuration
Use the configuration GUI to set up cameras:

```bash
python launcher.py --configure
```

Configuration includes:
- Camera server URLs (WebRTC endpoints)
- Crop rectangles for each camera
- Grid layout and positioning
- IR detection parameters

### Example Configuration File (`camera_config.json`):
```json
{
  "cameras": [
    {
      "server_url": "http://192.168.1.100:8080",
      "crop_rect": [0, 0, 640, 480],
      "position": [0, 0],
      "camera_id": "cam_1",
      "enabled": true
    }
  ],
  "grid_config": {
    "cameras_per_row": 2,
    "total_cameras": 4,
    "cell_width": 320,
    "cell_height": 240
  }
}
```

## Usage Modes

### Demo Mode
Perfect for testing and development without hardware:
- Simulated moving IR beacons
- Multiple virtual cameras
- All detection and tracking features work
- No network or hardware requirements

```bash
python launcher.py --demo
```

### Live Mode
Connect to real cameras for production use:
- WebRTC streaming from camera nodes
- Real-time IR beacon detection
- Composite video from multiple cameras
- Interactive controls and overlays

```bash
python launcher.py --run
```

### Node Server Mode
Run camera server on Pi or other devices:
- Streams video via WebRTC
- Handles camera hardware
- Can run headless
- Supports auto-start via cron

```bash
python launcher.py --node
```

## Controls and Keyboard Shortcuts

### Video Display Controls
- **Q**: Quit application
- **+/-**: Adjust IR threshold
- **S**: Save screenshot
- **R**: Reset view/reload configuration
- **Space**: Start/Stop video display
- **O**: Toggle raw overlay
- **G**: Toggle coordinate grid
- **C**: Toggle coordinate info
- **B**: Toggle IR beacon overlay

### Mouse Controls
- **Click**: Show coordinates at clicked position
- **Drag**: Pan view (when implemented)

## System Requirements

### Control Stack
- Python 3.7+
- OpenCV (opencv-python)
- NumPy
- aiohttp
- aiortc
- Pillow (PIL)
- Tkinter (usually included with Python)

### Node Stack
- Python 3.7+
- Flask
- OpenCV (opencv-python)
- NumPy
- aiohttp
- aiortc
- picamera2 (Raspberry Pi only)
- scikit-image
- requests

### Platform Support
- **Control Stack**: Windows, macOS, Linux
- **Node Stack**: Linux (optimized for Raspberry Pi)
- **Launcher**: Cross-platform GUI and CLI

## Troubleshooting

### Common Issues

1. **Dependencies Missing**
   ```bash
   python launcher.py --check-deps all
   python setup.py  # Reinstall dependencies
   ```

2. **Camera Connection Failed**
   - Check network connectivity
   - Verify camera server URLs
   - Try demo mode first: `python launcher.py --demo`

3. **GUI Won't Start**
   ```bash
   python launcher.py  # Use CLI interface
   ```

4. **No Video Display**
   - Check if running in headless environment
   - Use `--dry-run` flag for headless operation
   - Verify camera configuration

### Diagnostics
Use built-in diagnostics to check system health:

```bash
python launcher.py --status          # Overall system status
python launcher.py --check           # Quick dependency check
python launcher.py --gui             # GUI diagnostics tools
```

### Log Files
Terminal output can be saved from the GUI launcher for debugging.

## Development

### Project Structure
```
Automated-Followspot-System/
├── launcher.py              # CLI launcher
├── launcher_gui.py          # GUI launcher
├── setup.py                # Dependency installer
├── launcher_config.json    # System configuration
├── camera_config.json      # Camera configuration
├── control/                # Control stack
│   ├── main.py
│   ├── camera_aggregator.py
│   ├── camera_config_gui.py
│   ├── video_display_gui.py
│   ├── demo_mode.py
│   └── requirements.txt
├── node/                   # Node stack
│   ├── server.py
│   ├── requirements.txt
│   └── README.md
└── README.md
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with both stacks
5. Submit a pull request

## License

This project is licensed under the GNU Affero General Public License v3.0. See the `LICENSE` file for details.

## Support

- **Documentation**: This README and inline help
- **Issues**: [GitHub Issues](https://github.com/Stavro-Purdie/Automated-Followspot-System/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Stavro-Purdie/Automated-Followspot-System/discussions)

## Acknowledgments

Built for live performance applications requiring precise automated lighting control and tracking.

# Multi-Camera IR Beacon Tracker

A streamlined GUI application for tracking IR beacons across multiple camera feeds using WebRTC streaming.

## Features

- **Connection Dialog**: User-friendly interface to choose between Live Mode, Demo Mode, or Configuration
- **Real-time Video Display**: Shows composite video feed from multiple cameras via WebRTC
- **IR Beacon Detection**: Automatically detects and highlights IR beacons with overlay
- **Coordinate System**: Interactive coordinate grid and position tracking
- **Demo Mode**: Simulated cameras with moving beacons for testing without hardware
- **Interactive Controls**: Adjustable IR threshold, display options, and more
- **WebRTC Streaming**: Low-latency camera feeds using modern web standards

## Quick Start

1. **Navigate to Client Directory**:
   ```bash
   cd rpi-webrtc-camera/client
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Application** (shows connection dialog):
   ```bash
   python3 main.py
   ```

   Or use specific modes:
   - **Configure Cameras**: `python3 main.py --configure`
   - **Demo Mode**: `python3 main.py --demo`
   - **Skip Dialog**: `python3 main.py --no-dialog`

## GUI Controls

### Mouse Controls
- **Click on video**: Show pixel coordinates at clicked position

### Keyboard Shortcuts
- **Q**: Quit application
- **+/-**: Adjust IR threshold
- **S**: Save screenshot
- **R**: Reset view to defaults
- **Space**: Start/Stop video display
- **O**: Toggle raw overlay
- **G**: Toggle coordinate grid
- **C**: Toggle coordinate info
- **B**: Toggle IR beacon overlay

### GUI Elements
- **IR Threshold Slider**: Adjust sensitivity for IR beacon detection
- **Display Options**: Toggle coordinate grid, beacon overlay, and coordinate info
- **Statistics**: Real-time FPS, beacon count, and frame size
- **Control Buttons**: Start/Stop, Save Screenshot, Reset View

## File Structure

### Main Application
- `main.py` - Main application launcher with connection dialog integration
- `connection_dialog.py` - GUI dialog for selecting application mode (Live/Demo/Config)
- `video_display_gui.py` - GUI for video display and controls
- `camera_aggregator.py` - Core camera management and WebRTC processing
- `demo_mode.py` - Simulated camera feeds for testing

### Configuration & Setup
- `camera_config_gui.py` - Configuration interface for camera setup
- `camera_config.json` - Camera configuration file
- `launcher.py` - Alternative launcher with additional options

### Support Files
- `client.py` - Basic WebRTC client implementation
- `requirements.txt` - Python dependencies
- `setup.py` - Package setup configuration

## Configuration

The application uses `camera_config.json` for camera settings:

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

### Connection Dialog

When you run `python3 main.py`, a connection dialog appears with three options:

1. **Live Mode**: Connect to real cameras (requires configuration file)
2. **Demo Mode**: Run with simulated cameras and moving beacons
3. **Configuration**: Launch the camera setup interface

The dialog will automatically disable Live Mode if no configuration file is found.

## Demo Mode

Demo mode provides a fully functional simulation with:
- Multiple moving IR beacons with realistic physics
- Simulated camera feeds from different virtual positions
- All detection and tracking features working
- No hardware or network requirements
- Perfect for testing and development

## Command Line Options

- `python3 main.py` - Show connection dialog (default)
- `python3 main.py --demo` - Run directly in demo mode
- `python3 main.py --configure` - Launch configuration GUI
- `python3 main.py --no-dialog` - Skip dialog, use command line args
- `python3 main.py --config path/to/config.json` - Use custom config file

## Troubleshooting

1. **Connection Dialog Issues**: If the dialog doesn't appear, use `--no-dialog` flag
2. **No video display**: Check camera connections and configuration file
3. **GUI not responding**: Ensure all dependencies are installed
4. **Import errors**: Run `pip install -r requirements.txt` in the client directory
5. **WebRTC connection fails**: Verify camera server URLs and network connectivity
6. **Display issues**: Try demo mode first to verify GUI functionality

## Development

The application uses:
- **OpenCV** for video processing and IR beacon detection
- **Tkinter** for GUI interface and connection dialog
- **PIL/Pillow** for image handling and display
- **aiohttp/aiortc** for WebRTC camera communication
- **numpy** for image processing and mathematical operations

### Architecture
- **WebRTC**: Low-latency streaming from camera servers
- **Asyncio**: Non-blocking camera communication
- **Threading**: Separate threads for GUI and video processing
- **Queue-based**: Frame processing pipeline with thread-safe queues

## License

This project is part of the Automated Followspot System.

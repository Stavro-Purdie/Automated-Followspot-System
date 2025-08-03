# Multi-Camera IR Beacon Tracker

A streamlined GUI application for tracking IR beacons across multiple camera feeds.

## Features

- **Real-time Video Display**: Shows composite video feed from multiple cameras
- **IR Beacon Detection**: Automatically detects and highlights IR beacons with overlay
- **Coordinate System**: Interactive coordinate grid and position tracking
- **Demo Mode**: Simulated cameras for testing without hardware
- **Interactive Controls**: Adjustable IR threshold, display options, and more

## Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Cameras** (first time only):
   ```bash
   python3 main.py --configure
   ```

3. **Run Application**:
   ```bash
   python3 main.py
   ```

4. **Run Demo Mode** (no cameras required):
   ```bash
   python3 main.py --demo
   ```

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

- `main.py` - Main application launcher
- `video_display_gui.py` - GUI for video display and controls
- `multi_camera_client.py` - Core camera management and processing
- `demo_mode.py` - Simulated camera feeds for testing
- `camera_config_gui.py` - Configuration interface
- `connection_dialog.py` - Connection retry dialogs
- `ir_processor.py` - IR beacon detection algorithms
- `camera_config.json` - Camera configuration file

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

## Demo Mode

Demo mode provides a fully functional simulation with:
- Moving IR beacons with realistic physics
- Multiple simulated camera feeds
- All detection and tracking features
- No hardware requirements

## Troubleshooting

1. **No video display**: Check camera connections and configuration
2. **GUI not responding**: Ensure you're running on the main thread
3. **Import errors**: Install all requirements with `pip install -r requirements.txt`
4. **Display issues**: Try demo mode first to verify GUI functionality

## Development

The application uses:
- **OpenCV** for video processing and IR detection
- **Tkinter** for GUI interface
- **PIL/Pillow** for image handling
- **asyncio/aiohttp** for camera communication
- **numpy** for image processing

## License

This project is part of the Automated Followspot System.

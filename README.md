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

For the front truss node (IMX477/RS485 build):
```bash
python launcher.py --install-deps front-node
```

During either node installation you'll be prompted for static IP, hostname, camera device, and port information. The launcher captures those values, writes network setup notes, and provisions a user-level systemd service so the node boots automatically.

### 3. Quick Launch Options

```bash
# Launch GUI interface (default behavior)
python launcher.py
./followspot

# Use industrial command-line launcher
python launcher.py --cli   # or -cli
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

# Install the front truss node stack headlessly
python launcher.py --install-deps front-node

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

Run the front truss node on a Raspberry Pi with the HQ (IMX477) camera and RS485 HAT using the dedicated profile:

```bash
python node/server.py --profile front_truss --port 8000
```

The DMX endpoint (`/dmx`) is wired but returns a placeholder response until RS485 output is ready.

On headless deployments, launch the industrial CLI to provision any stack—including the front truss node—without a desktop session:

```bash
python launcher.py --cli
```

Follow the on-screen menu or run `python launcher.py --install-deps front-node` directly for unattended scripts.

### Launcher System
Unified management interface for both stacks:

- **GUI Launcher** (`launcher_gui.py`): Full graphical management interface
- **CLI Launcher** (`launcher.py`): Industrial text console for headless installs
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

## Front Camera Calibration (Complete Guide)

Accurate XYZ tracking and spotlight tilt depend on a precise calibration of the front ReID camera. Follow the end-to-end workflow below whenever you install the system in a new venue or move the camera rig.

### 1. Understand the Coordinate System

- **Stage origin**: The point $(0, 0, 0)$ sits on the stage floor. By default, the $+X$ axis runs to stage right, $+Y$ toward upstage (away from the audience), and $+Z$ points upward.
- **Camera frame**: The ReID camera reports detections in its own 3D frame. Calibration computes a rotation matrix and translation vector that map those detections into stage coordinates.
- **Spotlight rig**: The spotlight controller assumes the same stage origin, so camera misalignment directly affects pan/tilt accuracy.

### 2. Gather Tools and Measurements

| Item | Purpose |
| --- | --- |
| Tape measure or laser rangefinder | Measure camera height and offsets from stage origin |
| Inclinometer or protractor | Measure camera tilt if you are not running the automated calibration |
| Laptop with the configurator | Enter values and capture calibration points |
| Clearly marked stage corners | Improve click accuracy during calibration |

Record the following before you open the configurator:

- Stage width, depth, and height
- Desired stage origin (often center front edge or downstage-left corner)
- Camera position relative to the origin (X/Y on the floor plane, Z for height)
- Approximate camera pitch (tilt downward). Note the yaw (rotation around Z) if it is not facing straight downstage.

### 3. Enter Stage Geometry

1. Launch the front camera configurator:
  ```bash
  python launcher.py --configure
  ```
2. Open the **Stage Geometry** tab.
3. Fill in the stage width, depth, and height in meters.
4. Set the origin coordinates to the physical point you chose. If you want the origin at the front-center of the stage, use `X = 0`, `Y = 0`, and `Z = 0`. For a downstage-left corner origin, set `X = -width/2`, `Y = 0`, `Z = 0`, etc.
5. Click **Save Configuration** to persist the updated stage definition.

### 4. Capture Stage Corners (2D Reference)

1. In the **Camera Preview** panel, start the camera feed (or load a still image if you have one captured from the same pose).
2. Press **Calibrate**. You will be prompted to click the four stage corners in this order:
  1. Front-left (downstage left)
  2. Front-right (downstage right)
  3. Back-right (upstage right)
  4. Back-left (upstage left)
3. Click carefully; the pixel selections establish the homography used for downstream alignment.
4. When all four points are selected, the configurator timestamps the run and marks `calibration.calibrated = true` in `front_array_config.json`.

### 5. Solve the Camera Extrinsics (3D Pose)

Two options give you the Z alignment the fusion pipeline needs:

#### A. Quick Manual Entry

1. Still in **Front Node Settings**, locate **Camera Position (X, Y, Z m)**. Enter the measured offsets from the stage origin.
2. Set **Camera Angle (deg)** to the measured pitch. Positive values tip the camera toward the stage.
3. If the camera is yawed (rotated left/right), update the yaw inside the **Rotation Matrix** (see table below for help editing matrices manually).

This approach is suitable when you only need approximate Z values or you have highly accurate measurements from rigging drawings.

#### B. Calibration Matrix Workflow (Recommended)

1. After recording the stage corners, measure three or more distinct reference points on the stage (for example, known marks or spike strips) and note their stage coordinates.
2. Enter each reference point in the **Calibration** panel of the configurator (under `calibration.reference_points`).
3. Use the guidance in `docs/front_camera_z_calibration.md` to run the projection solver. The solver updates `camera.front_camera.extrinsics.rotation_matrix` and `translation_vector`, and marks the set as calibrated.
4. Press **Save Configuration** once the solver completes. The fusion layer will now treat the extrinsics as authoritative and ignore the simple `angle` field.

### 6. Verify Depth in the Fusion View

1. Launch the fused control loop (`python control/fused_main.py`) or start the system via the launcher.
2. Watch the fused person coordinates. A performer centered at stage origin should report `X ≈ 0`, `Y ≈ 0`. When they walk upstage, the Y value should increase. A tall performer and a short performer should produce sensible Z differences (around their actual height).
3. If the Z value is mirrored or sign-flipped, revisit the rotation matrix—swap axes or adjust signs until upstage/downstage behave correctly.

### 7. Align the Spotlight Rig

Once the camera pose is correct, open the **Spotlight Rig** tab in the configurator:

1. Enter the fixture position, stage origin repeat, and zero angles as measured.
2. Set the same origin reference you used for the camera so both systems align.
3. Save the configuration; `config/spotlight_config.json` is written alongside `front_array_config.json`.

### 8. Final Checklist

- [ ] `front_array_config.json` contains the measured stage geometry and extrinsics with `calibrated: true`.
- [ ] `spotlight_config.json` matches the same stage origin so pan/tilt math is consistent.
- [ ] Operators can run **Test System** in the configurator to ensure configuration sanity before a show.
- [ ] Optional: keep a copy of the JSON files in `backups/` once calibration is verified.

### Reference: Editing the Rotation Matrix Manually

The rotation matrix follows the standard right-handed convention. If you need to adjust it manually:

| Desired effect | Matrix edit |
| --- | --- |
| Tilt camera down by angle θ | Multiply the first row/column by the rotation matrix $R_x(θ)$ |
| Yaw camera toward audience left | Apply $R_z(+θ)$ |
| Roll camera clockwise | Apply $R_y(-θ)$ |

Combine rotations by multiplying the matrices (order matters). The solver described above automates this, so manual edits are typically only necessary for quick tweaks.

For a printable, no-fiducial walkthrough see `docs/front_camera_z_calibration.md`. That guide also covers an optional high-precision photogrammetry workflow if you ever need to step up from the tape-measure method.

### Example Configuration File (`roof_array_config.json`):
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

## Apple Silicon Acceleration

The control stack now detects Apple Silicon hardware automatically, and the launcher's **Settings → ReID Acceleration** panel lets you toggle these options without editing JSON files:

- **Metal (MPS)**: When PyTorch is installed with MPS support, all detector and ReID models run on the GPU without any configuration changes.
- **Neural Engine (Core ML)**: For the lowest power draw, you can supply a Core ML version of the ReID embedding model and enable it in `config/reid_config.json`:

  Available accelerator modes:
  - **Neural Engine (ANE)** → `CPU_AND_NE`
  - **GPU (Metal)** → `CPU_AND_GPU`
  - **CPU only** → `CPU_ONLY`
  - **Automatic (All accelerators)** → `ALL`

  ```json
  "optimization": {
    "coreml_reid_enabled": true,
    "coreml_model_path": "reid/models/osnet_x0_5.mlpackage",
    "coreml_compute_unit": "CPU_AND_NE",
    "coreml_skip_torch": true
  }
  ```

  1. Install Core ML tooling (optional, only needed to use the Neural Engine):

     ```bash
     pip install coremltools==6.4
     ```

  2. Convert your ReID PyTorch checkpoint to Core ML (for example, with `coremltools.convert` or a custom script) and place the produced `.mlpackage` in `reid/models/`.

  3. Toggle `coreml_reid_enabled` to `true`. You can do this visually from the launcher or by editing the JSON directly. The loader will verify the model on startup and fall back to the Torch backend if anything goes wrong.

When Core ML is active, Torch-based ReID inference can be skipped entirely (`coreml_skip_torch: true`) so the pipeline uses only the Neural Engine for embeddings while the detector continues to run on MPS.

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
├── launcher.py              # Industrial CLI launcher
├── launcher_gui.py          # GUI launcher
├── setup.py                # Dependency installer
├── launcher_config.json    # System configuration
├── config/
│   ├── roof_array_config.json   # Roof array camera configuration (primary)
│   └── front_array_config.json  # Front array camera configuration (placeholder)
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

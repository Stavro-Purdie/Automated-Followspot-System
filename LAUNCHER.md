# Automated Followspot System Launcher

This document describes the launcher system for the Automated Followspot System, which provides a unified interface for managing both Control and Node stacks.

## Overview

The launcher system consists of several components:
- **GUI Launcher** (`launcher_gui.py`): Full graphical interface with installation wizards
- **CLI Launcher** (`launcher.py`): Command-line interface with interactive menus
- **Setup Script** (`setup.py`): Dependency installation utility
- **Configuration** (`launcher_config.json`): Tracks system state and installations

## Quick Start

### First Time Setup
1. Run the setup to install dependencies:
   ```bash
   python setup.py
   ```

2. Launch the system (GUI by default):
   ```bash
   python launcher.py
   # OR
   ./followspot
   ```

### Command Reference

```bash
# GUI Interface (Default)
python launcher.py              # Launch graphical interface (default)
./followspot                    # Same as above

# CLI Interface (Optional)
python launcher.py --cli        # Force command-line interface
./followspot --cli              # Same as above

# Installation & Dependencies
python setup.py                 # Interactive dependency installer
./followspot --install-deps control  # Install control stack deps
./followspot --install-deps node     # Install node stack deps

# System Information
./followspot --status           # Show detailed system status
./followspot --check-deps all   # Check all dependencies
./followspot --check            # Quick system check

# Application Launching
./followspot --configure        # Launch camera configuration
./followspot --demo             # Run in demo mode
./followspot --run              # Run live mode
./followspot --node             # Start node server

# Help
./followspot --help             # Show all options
python launcher.py --help       # Same as above
```

## System States

The launcher manages different system states based on what's installed:

### No Stacks Installed
When no stacks are installed, the launcher offers:
1. Launch GUI installer
2. Install control stack dependencies
3. Install node stack dependencies
4. About information
5. Bug reporting
6. Exit

### Control Stack Only
When only the control stack is installed:
1. Launch Configuration GUI
2. Launch Offline Mode (Demo)
3. Launch Live Mode
4. Install Node Stack
5. Launch GUI
6. Exit

### Node Stack Only
When only the node stack is installed:
1. Start Node Server
2. Install Control Stack
3. Node Diagnostics
4. Launch GUI
5. Exit

### Both Stacks Installed
When both stacks are installed:
1. Launch Configuration (Control)
2. Launch Offline Mode (Control)
3. Launch Live Mode (Control)
4. Start Node Server
5. Launch GUI
6. System Status
7. Exit

## Configuration Files

### Launcher Configuration (`launcher_config.json`)
Tracks installation state and system settings:
```json
{
  "installations": {
    "control_stack": {
      "installed": true,
      "version": "1.0.0",
      "install_date": "2025-08-06T...",
      "dependencies_verified": true,
      "last_dependency_check": "2025-08-06T..."
    },
    "node_stack": {
      "installed": false,
      "cron_enabled": false
    }
  },
  "settings": {
    "auto_dependency_check": true,
    "check_interval_days": 7
  }
}
```

### Camera Configuration (`camera_config.json`)
Stores camera setup and layout information (created by configuration GUI).

## GUI Launcher Features

The GUI launcher (`launcher_gui.py`) provides:

### Installation Wizards
- **Control Stack Installer**: GUI-guided installation with progress tracking
- **Node Stack Installer**: Similar wizard for node stack
- **Dependency Management**: Real-time installation progress and error handling
- **Terminal Window**: Live view of installation process

### System Management
- **Status Dashboard**: Visual overview of installed stacks and health
- **Dependency Checking**: Background verification of installed packages
- **Configuration Management**: Easy access to camera setup
- **Diagnostics**: Built-in system health checks

### Application Launching
- **One-Click Launch**: Direct access to all system modes
- **Mode Selection**: Easy switching between demo, live, and configuration modes
- **Error Handling**: Graceful handling of missing dependencies or configurations

### Maintenance Tools
- **Repair Functions**: Reinstall dependencies for problematic installations
- **Uninstall Options**: Clean removal of stacks
- **Log Management**: Save and view system logs
- **Settings**: Configure auto-checking and other preferences

## Node Stack Specific Features

### Cron Job Management
The launcher can manage automatic startup of the node server:
- **Enable/Disable**: Toggle automatic startup at boot
- **Cron Integration**: Manages system cron entries
- **Status Monitoring**: Shows current cron status

### Diagnostics
Built-in diagnostics for node stack:
- **Hardware Detection**: Raspberry Pi detection
- **File Verification**: Check for required files
- **Dependency Validation**: Verify all packages are available
- **Network Testing**: Basic connectivity checks

## Error Handling

The launcher includes comprehensive error handling:

### Dependency Issues
- **Missing Packages**: Clear indication of what's missing
- **Installation Failures**: Detailed error messages
- **Platform Compatibility**: Warnings for unsupported features

### Configuration Problems
- **Missing Files**: Guidance on creating configurations
- **Invalid Settings**: Validation and correction suggestions
- **Permission Issues**: Clear error messages and solutions

### Runtime Errors
- **Process Management**: Graceful handling of subprocess failures
- **Network Issues**: Timeout handling and retry logic
- **GUI Failures**: Fallback to CLI mode when GUI unavailable

## Development Notes

### Adding New Features
1. Update `launcher_config.json` structure if needed
2. Add new CLI arguments to `launcher.py`
3. Add corresponding GUI elements to `launcher_gui.py`
4. Update interactive menus in both interfaces
5. Add documentation to this file

### Testing
- Test both GUI and CLI interfaces
- Verify all installation and uninstallation flows
- Check error handling with missing dependencies
- Test on different platforms (where applicable)

### Configuration Updates
When the configuration schema changes:
1. Update the default configuration in both launcher files
2. Add migration logic for existing configurations
3. Test with existing configuration files

## Troubleshooting

### Common Issues

**GUI Won't Start**
```bash
# Use CLI interface instead
python launcher.py
```

**Dependencies Won't Install**
```bash
# Update pip first
python -m pip install --upgrade pip
# Try manual installation
python setup.py
```

**Permission Errors (Linux/Mac)**
```bash
# Make scripts executable
chmod +x launcher.py launcher_gui.py setup.py
# Or use the helper script
./make_executable.sh
```

**Configuration Corruption**
```bash
# Reset configuration
rm launcher_config.json
python launcher.py --status  # Recreates with defaults
```

### Debug Mode
Enable debug mode in launcher settings for verbose output and additional diagnostics.

## Platform Notes

### Windows
- Use `python` instead of `python3`
- Some Unix-specific features may not work
- GUI should work normally

### macOS
- All features supported
- Use `python3` if multiple Python versions installed
- GUI requires proper Python/Tkinter installation

### Linux (including Raspberry Pi)
- Full feature support
- Cron job management available
- Hardware detection works on Pi
- Node stack optimized for Pi hardware

## Support

For issues with the launcher system:
1. Check this documentation
2. Run diagnostics: `./followspot --status`
3. Check dependencies: `./followspot --check-deps all`
4. Report issues on GitHub with debug output

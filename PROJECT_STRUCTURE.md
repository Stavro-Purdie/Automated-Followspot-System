# Automated Followspot System - Project Structure

## Directory Structure

```
Automated-Followspot-System/
├── launcher.py                    # Main entry point for all operations
├── LICENSE
├── README.md
├── PROJECT_STRUCTURE.md          # This file
│
├── config/                       # Configuration files
│   ├── launcher_config.json      # System installation and settings
│   └── camera_config.json        # Camera configuration
│
├── installer_scripts/            # Installation and GUI components
│   ├── README.md                 # Installer components documentation
│   ├── launcher_gui.py          # Comprehensive GUI interface
│   ├── installer_wizard.py      # InstallShield-style step-by-step installer
│   └── test_installer.py        # Testing and validation script
│
├── control/                      # Control stack (main application)
│   ├── main.py                  # Multi-camera client entry point
│   ├── camera_aggregator.py     # Camera management and aggregation
│   ├── camera_config_gui.py     # Camera configuration interface
│   ├── connection_dialog.py     # Connection management dialogs
│   ├── demo_mode.py             # Demo mode implementation
│   ├── setup.py                 # Control stack setup utilities
│   ├── video_display_gui.py     # Video display interface
│   ├── requirements.txt         # Control stack dependencies
│   └── client.py                # Client connection utilities
│
└── node/                        # Node stack (camera servers)
    ├── README.md                # Node stack documentation
    ├── server.py               # Node server implementation
    └── requirements.txt        # Node stack dependencies
```
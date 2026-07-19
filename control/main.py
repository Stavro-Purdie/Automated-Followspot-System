#!/usr/bin/env python3
"""
Decides whether we enter into live mode, camera configurator, or
launch the demos. 
"""


import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so package-qualified imports resolve
_proj = Path(__file__).resolve().parent.parent
if str(_proj) not in sys.path:
    sys.path.insert(0, str(_proj))

import logging
import argparse
import re
from typing import Any
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")

def _sanitize_for_log(value) -> str:
    """Return a log-safe, single-line string with control chars escaped."""
    text = str(value)
    escaped = text.encode("unicode_escape", errors="backslashreplace").decode("ascii", errors="ignore")
    return escaped

def main():
    """Parse CLI flags, present the mode chooser, and start the requested tools."""
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Multi-Camera IR Beacon Tracker")
    parser.add_argument(
        "--config",
        type=str,
        default=str(project_root / "config" / "roof_array_config.json"),
        help="Configuration file path (default: config/roof_array_config.json)",
    )
    parser.add_argument("--demo", action="store_true",
                        help="Run in demo mode with simulated cameras")
    parser.add_argument("--configure", action="store_true",
                        help="Launch configuration GUI")
    parser.add_argument("--no-dialog", action="store_true",
                        help="Skip the connection dialog and use command line arguments")
    
    args = parser.parse_args()
    args.config = _sanitize_for_log(args.config)
    
    # If no specific mode is requested and no-dialog is not set, show the connection dialog
    if not args.demo and not args.configure and not args.no_dialog:
        try:
            from control.camera_aggregator import show_connection_dialog
            logger.info("Showing connection dialog...")
            dialog_fn = show_connection_dialog
            if not callable(dialog_fn):
                raise ImportError("connection dialog is unavailable")
            result: Any = dialog_fn(args.config)
            
            if not result:
                logger.info("Dialog cancelled, exiting...")
                return
            
            # Update args based on dialog result
            if result["mode"] == "demo":
                args.demo = True
            elif result["mode"] == "config":
                args.configure = True
            elif result["mode"] == "live":
                args.demo = False
                args.configure = False
            
            args.config = _sanitize_for_log(result["config"])
            
        except ImportError as e:
            logger.warning("Could not import connection dialog: %s", _sanitize_for_log(e))
            logger.info("Continuing with command line arguments...")
        except Exception as e:
            logger.warning("Error showing connection dialog: %s", _sanitize_for_log(e))
            logger.info("Continuing with command line arguments...")
        
        # Launch configuration GUI if requested
        if args.configure:
            try:
                from control.camera_config_gui import main as config_main
                config_main()
            except ImportError as e:
                logger.error("Could not import configuration GUI: %s", _sanitize_for_log(e))
                logger.info("Please ensure all dependencies are installed")
            return
    
    try:
        # Import required modules
        from control.camera_aggregator import MultiCameraManager
        from control.video_display_gui import VideoDisplayGUI
    
        # Create camera manager
        manager = MultiCameraManager(args.config, demo_mode=args.demo)
    
        if not manager.cameras:
            if args.demo:
                logger.info("No cameras configured; demo mode will run with placeholder feeds.")
            else:
                logger.warning(
                    "No cameras configured; live mode will open with placeholders and wait for connections."
                )
    
        # Create and run GUI
        mode_text = "Demo Mode" if args.demo else "Live Mode"
        logger.info(f"Starting Multi-Camera IR Beacon Tracker GUI in {mode_text}...")
        gui = VideoDisplayGUI(manager)
        gui.run()
    
    except ImportError as e:
        logger.error("Could not import required modules: %s", _sanitize_for_log(e))
        logger.info("Please ensure all dependencies are installed with: pip install -r requirements.txt")
    except Exception as e:
        logger.error("Error starting application: %s", _sanitize_for_log(e))
        sys.exit(1)

if __name__ == "__main__":
    main()

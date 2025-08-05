#!/usr/bin/env python3
"""
Main launcher for the Multi-Camera IR Beacon Tracker GUI
"""

import sys
import os
import logging
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("main")

def main():
    parser = argparse.ArgumentParser(description="Multi-Camera IR Beacon Tracker")
    parser.add_argument("--config", type=str, default="camera_config.json",
                        help="Configuration file path (default: camera_config.json)")
    parser.add_argument("--demo", action="store_true",
                        help="Run in demo mode with simulated cameras")
    parser.add_argument("--configure", action="store_true",
                        help="Launch configuration GUI")
    parser.add_argument("--no-dialog", action="store_true",
                        help="Skip the connection dialog and use command line arguments")
    
    args = parser.parse_args()
    
    # If no specific mode is requested and no-dialog is not set, show the connection dialog
    if not args.demo and not args.configure and not args.no_dialog:
        try:
            from connection_dialog import show_connection_dialog
            logger.info("Showing connection dialog...")
            result = show_connection_dialog(args.config)
            
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
            
            args.config = result["config"]
            
        except ImportError as e:
            logger.warning(f"Could not import connection dialog: {e}")
            logger.info("Continuing with command line arguments...")
        except Exception as e:
            logger.warning(f"Error showing connection dialog: {e}")
            logger.info("Continuing with command line arguments...")
    
    # Launch configuration GUI if requested
    if args.configure:
        try:
            from camera_config_gui import main as config_main
            config_main()
        except ImportError as e:
            logger.error(f"Could not import configuration GUI: {e}")
            logger.info("Please ensure all dependencies are installed")
        return
    
    # Check if config file exists
    if not os.path.exists(args.config) and not args.demo:
        logger.error(f"Configuration file '{args.config}' not found.")
        logger.info("Run with --configure to create configuration or --demo for demo mode")
        return
    
    try:
        # Import required modules
        from camera_aggregator import MultiCameraManager
        from video_display_gui import VideoDisplayGUI
        
        # Create camera manager
        manager = MultiCameraManager(args.config, demo_mode=args.demo)
        
        if not manager.cameras:
            logger.error("No cameras configured.")
            if not args.demo:
                logger.info("Run with --configure to set up cameras or --demo for demo mode")
                return
        
        # Create and run GUI
        mode_text = "Demo Mode" if args.demo else "Live Mode"
        logger.info(f"Starting Multi-Camera IR Beacon Tracker GUI in {mode_text}...")
        gui = VideoDisplayGUI(manager)
        gui.run()
        
    except ImportError as e:
        logger.error(f"Could not import required modules: {e}")
        logger.info("Please ensure all dependencies are installed with: pip install -r requirements.txt")
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

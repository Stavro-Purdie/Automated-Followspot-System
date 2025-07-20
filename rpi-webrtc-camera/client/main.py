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
    
    args = parser.parse_args()
    
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
        from multi_camera_client import MultiCameraManager
        from video_display_gui import VideoDisplayGUI
        
        # Create camera manager
        manager = MultiCameraManager(args.config, demo_mode=args.demo)
        
        if not manager.cameras:
            logger.error("No cameras configured.")
            if not args.demo:
                logger.info("Run with --configure to set up cameras or --demo for demo mode")
                return
        
        # Create and run GUI
        logger.info("Starting Multi-Camera IR Beacon Tracker GUI...")
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

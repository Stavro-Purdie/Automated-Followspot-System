#!/usr/bin/env python3
"""
Multi-Camera System Launcher
Simple launcher for the multi-camera configuration and client.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = ['cv2', 'numpy', 'aiohttp', 'aiortc', 'PIL']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'cv2':
                import cv2
            elif package == 'PIL':
                from PIL import Image
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n📦 Install dependencies with:")
        print("   python setup.py")
        print("   # OR")
        print("   pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies are installed")
    return True

def check_config_file():
    """Check if configuration file exists"""
    config_file = "camera_config.json"
    if os.path.exists(config_file):
        print(f"✅ Configuration file found: {config_file}")
        return True
    else:
        print(f"⚠️  Configuration file not found: {config_file}")
        return False

def launch_config_gui():
    """Launch the configuration GUI"""
    script_path = Path(__file__).parent / "camera_config_gui.py"
    
    if not script_path.exists():
        print(f"❌ Configuration GUI script not found: {script_path}")
        return False
    
    print("🚀 Launching configuration GUI...")
    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        print(f"❌ Error launching configuration GUI: {e}")
        return False

def launch_client(config_file="camera_config.json"):
    """Launch the multi-camera client"""
    script_path = Path(__file__).parent / "multi_camera_client.py"
    
    if not script_path.exists():
        print(f"❌ Multi-camera client script not found: {script_path}")
        return False
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file not found: {config_file}")
        print("   Run configuration GUI first or create a configuration file")
        return False
    
    print(f"🚀 Launching multi-camera client with config: {config_file}")
    try:
        subprocess.run([sys.executable, str(script_path), "--config", config_file])
        return True
    except Exception as e:
        print(f"❌ Error launching client: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Multi-Camera System Launcher")
    parser.add_argument("--configure", action="store_true", 
                        help="Launch configuration GUI")
    parser.add_argument("--run", action="store_true", 
                        help="Launch multi-camera client")
    parser.add_argument("--config", type=str, default="camera_config.json",
                        help="Configuration file to use (default: camera_config.json)")
    parser.add_argument("--check", action="store_true",
                        help="Check system requirements and configuration")
    
    args = parser.parse_args()
    
    print("🎬 Multi-Camera System Launcher")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    if args.check:
        check_config_file()
        print("\n✅ System check complete")
        return
    
    if args.configure:
        launch_config_gui()
        return
    
    if args.run:
        launch_client(args.config)
        return
    
    # Interactive mode
    while True:
        print("\n📋 What would you like to do?")
        print("1. Configure cameras (GUI)")
        print("2. Run multi-camera client")
        print("3. Run demo mode")
        print("4. Check system status")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ").strip()
        
        if choice == "1":
            launch_config_gui()
        elif choice == "2":
            if check_config_file():
                launch_client(args.config)
            else:
                print("❌ No configuration found. Please configure cameras first (option 1).")
        elif choice == "3":
            launch_demo_mode()
        elif choice == "4":
            check_config_file()
        elif choice == "5":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1-5.")

def launch_demo_mode():
    """Launch demo mode"""
    script_path = Path(__file__).parent / "multi_camera_client.py"
    
    if not script_path.exists():
        print(f"❌ Multi-camera client script not found: {script_path}")
        return False
    
    print("🎮 Launching demo mode...")
    try:
        subprocess.run([sys.executable, str(script_path), "--demo"])
        return True
    except Exception as e:
        print(f"❌ Error launching demo mode: {e}")
        return False

if __name__ == "__main__":
    main()

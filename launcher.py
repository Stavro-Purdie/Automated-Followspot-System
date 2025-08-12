#!/usr/bin/env python3
"""
Enhanced launcher program for the Automated Followspot System.
Provides both GUI and command-line interfaces for managing Control and Node stacks.
Includes installation, configuration, dependency checking, and maintenance features.
"""

import os
import sys
import subprocess
import argparse
import json
import platform
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
except ImportError:
    tk = None

def load_launcher_config():
    """Load launcher configuration file"""
    config_file = "config/launcher_config.json"
    default_config = {
        "system_info": {
            "version": "1.0.0",
            "last_updated": datetime.now().isoformat(),
            "os_info": platform.platform(),
            "installation_path": str(Path(__file__).parent.absolute())
        },
        "installations": {
            "control_stack": {
                "installed": False,
                "version": None,
                "install_date": None,
                "dependencies_verified": False,
                "last_dependency_check": None
            },
            "node_stack": {
                "installed": False,
                "version": None,
                "install_date": None,
                "dependencies_verified": False,
                "last_dependency_check": None,
                "cron_enabled": False
            }
        },
        "settings": {
            "auto_dependency_check": True,
            "check_interval_days": 7,
            "allow_concurrent_stacks": False,
            "debug_mode": False
        }
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Merge with defaults to ensure all keys exist
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
                elif isinstance(default_config[key], dict):
                    for subkey in default_config[key]:
                        if subkey not in config[key]:
                            config[key][subkey] = default_config[key][subkey]
            return config
        except Exception as e:
            print(f"⚠️  Error loading launcher config: {e}")
            return default_config
    else:
        # Create default config file
        try:
            with open(config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"✅ Created launcher configuration: {config_file}")
        except Exception as e:
            print(f"⚠️  Could not create launcher config: {e}")
        return default_config

def save_launcher_config(config):
    """Save launcher configuration file"""
    config_file = "config/launcher_config.json"
    try:
        # Ensure config directory exists
        Path(config_file).parent.mkdir(exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving launcher config: {e}")
        return False

def check_dependencies(stack_type=None):
    """Check if required dependencies are installed for specified stack or both"""
    control_result = True
    node_result = True
    
    if stack_type == "control" or stack_type is None:
        control_result = check_stack_dependencies("control")
        if stack_type == "control":
            return control_result
    
    if stack_type == "node" or stack_type is None:
        node_result = check_stack_dependencies("node")
        if stack_type == "node":
            return node_result
    
    if stack_type is None:
        return control_result and node_result
    
    return False

def check_stack_dependencies(stack_type):
    """Check dependencies for a specific stack"""
    if stack_type == "control":
        requirements_file = Path(__file__).parent / "control" / "requirements.txt"
        stack_name = "Control Stack"
    elif stack_type == "node":
        requirements_file = Path(__file__).parent / "node" / "requirements.txt"
        stack_name = "Node Stack"
    else:
        return False
    
    if not requirements_file.exists():
        print(f"⚠️  Requirements file not found for {stack_name}: {requirements_file}")
        return False
    
    # Read requirements
    try:
        with open(requirements_file, 'r') as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"❌ Error reading requirements for {stack_name}: {e}")
        return False
    
    missing_packages = []
    
    for requirement in requirements:
        package_name = None
        try:
            # Simple package name extraction
            package_name = requirement.split('>=')[0].split('==')[0].split('[')[0].strip()
            
            if package_name == 'opencv-python':
                import cv2
            elif package_name == 'pillow':
                from PIL import Image
            elif package_name == 'picamera2':
                # Skip picamera2 on non-Pi systems
                if not is_raspberry_pi():
                    continue
                try:
                    import picamera2
                except ImportError:
                    # Only add to missing if we're on a Pi
                    if is_raspberry_pi():
                        missing_packages.append(package_name)
                    continue
            elif package_name == 'cv2':
                import cv2
            elif package_name == 'PIL':
                from PIL import Image
            else:
                __import__(package_name.replace('-', '_'))
        except ImportError:
            if package_name:
                missing_packages.append(package_name)
    
    if missing_packages:
        print(f"❌ {stack_name} - Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        return False
    else:
        print(f"✅ {stack_name} - All dependencies are installed")
        return True

def is_raspberry_pi():
    """Check if running on Raspberry Pi"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        return 'BCM' in cpuinfo or 'Raspberry Pi' in cpuinfo
    except:
        return False

def check_config_file():
    """Check if camera configuration file exists"""
    primary = "config/roof_array_config.json"
    legacy = "config/camera_config.json"
    if os.path.exists(primary):
        print(f"✅ Camera configuration file found: {primary}")
        return True
    elif os.path.exists(legacy):
        print(f"⚠️  Legacy configuration file found: {legacy}")
        print("   Please rename to roof_array_config.json when convenient")
        return True
    else:
        print(f"⚠️  Camera configuration file not found: {primary}")
        return False

def launch_gui():
    """Launch the graphical launcher interface"""
    gui_script = Path(__file__).parent / "installer_scripts" / "launcher_gui.py"
    
    if not gui_script.exists():
        print(f"❌ GUI launcher script not found: {gui_script}")
        return False
    
    print("🚀 Launching GUI interface...")
    try:
        subprocess.run([sys.executable, str(gui_script)])
        return True
    except Exception as e:
        print(f"❌ Error launching GUI: {e}")
        return False

def launch_gui_status():
    """Launch GUI status window"""
    status_script = Path(__file__).parent / "installer_scripts" / "launcher_gui.py"
    
    if not status_script.exists():
        print(f"❌ Status GUI script not found: {status_script}")
        return False
    
    print("🚀 Launching GUI status...")
    try:
        subprocess.run([sys.executable, str(status_script), "--status"])
        return True
    except Exception as e:
        print(f"❌ Error launching GUI status: {e}")
        return False


def launch_gui_installer(stack_type=None):
    """Launch step-by-step GUI installer"""
    installer_script = Path(__file__).parent / "installer_scripts" / "installer_wizard.py"
    
    if not installer_script.exists():
        print(f"❌ Installation wizard not found: {installer_script}")
        return False
    
    print("🚀 Launching installation wizard...")
    try:
        if stack_type:
            subprocess.run([sys.executable, str(installer_script), stack_type])
        else:
            subprocess.run([sys.executable, str(installer_script)])
        return True
    except Exception as e:
        print(f"❌ Failed to launch installation wizard: {e}")
        return False

def launch_config_gui():
    """Launch the camera configuration GUI"""
    script_path = Path(__file__).parent / "control" / "camera_config_gui.py"
    
    if not script_path.exists():
        print(f"❌ Configuration GUI script not found: {script_path}")
        return False
    
    print("🚀 Launching camera configuration GUI...")
    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        print(f"❌ Error launching configuration GUI: {e}")
        return False

def launch_reid_configurator():
    """Launch the ReID camera configurator"""
    script_path = Path(__file__).parent / "control" / "reid_configurator.py"
    
    if not script_path.exists():
        print(f"❌ ReID configurator script not found: {script_path}")
        return False
    
    print("🚀 Launching ReID camera configurator...")
    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        print(f"❌ Error launching ReID configurator: {e}")
        return False

def launch_client(config_file="config/roof_array_config.json"):
    """Launch the multi-camera client directly in live mode"""
    script_path = Path(__file__).parent / "control" / "main.py"
    
    if not script_path.exists():
        print(f"❌ Multi-camera client script not found: {script_path}")
        return False
    
    # Legacy fallback
    if not os.path.exists(config_file) and "roof_array_config.json" in config_file:
        legacy = config_file.replace("roof_array_config.json", "camera_config.json")
        if os.path.exists(legacy):
            print(f"⚠️  Using legacy configuration file: {legacy}")
            config_file = legacy
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file not found: {config_file}")
        print("   Run configuration GUI first or create a configuration file")
        return False
    
    print(f"🚀 Launching live mode with config: {config_file}")
    try:
        subprocess.run([sys.executable, str(script_path), "--config", config_file, "--no-dialog"])
        return True
    except Exception as e:
        print(f"❌ Error launching live mode: {e}")
        return False

def launch_demo_mode():
    """Launch demo mode"""
    script_path = Path(__file__).parent / "control" / "main.py"
    
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

def launch_node_server():
    """Launch node server"""
    script_path = Path(__file__).parent / "node" / "server.py"
    
    if not script_path.exists():
        print(f"❌ Node server script not found: {script_path}")
        return False
    
    print("🚀 Launching node server...")
    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        print(f"❌ Error launching node server: {e}")
        return False

def install_dependencies(stack_type):
    """Install dependencies for specified stack"""
    if stack_type == "control":
        requirements_file = Path(__file__).parent / "control" / "requirements.txt"
    elif stack_type == "node":
        requirements_file = Path(__file__).parent / "node" / "requirements.txt"
    else:
        print(f"❌ Unknown stack type: {stack_type}")
        return False
    
    if not requirements_file.exists():
        print(f"❌ Requirements file not found: {requirements_file}")
        return False
    
    print(f"📦 Installing {stack_type} stack dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)], check=True)
        print(f"✅ {stack_type.title()} stack dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing {stack_type} stack dependencies: {e}")
        return False

def show_system_status():
    """Display comprehensive system status"""
    config = load_launcher_config()
    
    print("🎬 Automated Followspot System Status")
    print("=" * 50)
    
    # System information
    print(f"Version: {config['system_info']['version']}")
    print(f"OS: {config['system_info']['os_info']}")
    print(f"Install Path: {config['system_info']['installation_path']}")
    print()
    
    # Control stack status
    control = config['installations']['control_stack']
    print("Control Stack:")
    if control['installed']:
        print(f"  ✅ Installed (v{control.get('version', 'Unknown')})")
        print(f"  📅 Install Date: {control.get('install_date', 'Unknown')}")
        deps_ok = control.get('dependencies_verified', False)
        print(f"  📦 Dependencies: {'✅ OK' if deps_ok else '❌ Issues'}")
        last_check = control.get('last_dependency_check', 'Never')
        print(f"  🔍 Last Check: {last_check}")
    else:
        print("  ❌ Not Installed")
    print()
    
    # Node stack status
    node = config['installations']['node_stack']
    print("Node Stack:")
    if node['installed']:
        print(f"  ✅ Installed (v{node.get('version', 'Unknown')})")
        print(f"  📅 Install Date: {node.get('install_date', 'Unknown')}")
        deps_ok = node.get('dependencies_verified', False)
        print(f"  📦 Dependencies: {'✅ OK' if deps_ok else '❌ Issues'}")
        last_check = node.get('last_dependency_check', 'Never')
        print(f"  🔍 Last Check: {last_check}")
        cron_enabled = node.get('cron_enabled', False)
        print(f"  ⏰ Start at Boot: {'✅ Enabled' if cron_enabled else '❌ Disabled'}")
    else:
        print("  ❌ Not Installed")
    print()
    
    # Configuration status
    print("Configuration:")
    if check_config_file():
        print("  ✅ Camera configuration found")
    else:
        print("  ❌ Camera configuration missing")
    print()

def main():
    parser = argparse.ArgumentParser(description="Automated Followspot System Launcher")
    parser.add_argument("--cli", action="store_true", 
                        help="Use command-line interface instead of GUI")
    parser.add_argument("--configure", action="store_true", 
                        help="Launch camera configuration GUI")
    parser.add_argument("--reid-config", action="store_true",
                        help="Launch ReID camera configurator")
    parser.add_argument("--run", action="store_true", 
                        help="Launch live camera tracking mode")
    parser.add_argument("--demo", action="store_true",
                        help="Launch in demo mode")
    parser.add_argument("--node", action="store_true",
                        help="Launch node server")
    parser.add_argument("--config", type=str, default="config/roof_array_config.json",
                        help="Configuration file to use (default: config/roof_array_config.json)")
    parser.add_argument("--check", action="store_true",
                        help="Check system requirements and configuration")
    parser.add_argument("--status", action="store_true",
                        help="Show detailed system status")
    parser.add_argument("--install-deps", choices=["control", "node"],
                        help="Install dependencies for specified stack")
    parser.add_argument("--check-deps", choices=["control", "node", "all"],
                        help="Check dependencies for specified stack")
    
    args = parser.parse_args()
    # Legacy fallback
    if (not os.path.exists(args.config) and "roof_array_config.json" in args.config):
        legacy = args.config.replace("roof_array_config.json", "camera_config.json")
        if os.path.exists(legacy):
            print(f"⚠️  Using legacy configuration file: {legacy}")
            args.config = legacy
    # Check if any CLI-specific arguments are provided
    cli_args = [args.configure, args.reid_config, args.run, args.demo, args.node, args.check, 
                args.install_deps, args.check_deps]
    
    # Add explicit CLI flag for status
    if args.status and args.cli:
        cli_args.append(True)
    
    # If no CLI arguments and not explicitly requesting CLI, launch GUI
    if not args.cli and not any(cli_args):
        launch_gui()
        return
    
    # Handle status display
    if args.status:
        if args.cli:
            show_system_status()
        else:
            # Launch GUI status instead
            launch_gui_status()
        return
    
    # Handle dependency operations
    if args.install_deps:
        install_dependencies(args.install_deps)
        return
    
    if args.check_deps:
        if args.check_deps == "all":
            check_dependencies()
        else:
            check_dependencies(args.check_deps)
        return
    
    # If we get here, we're in CLI mode (either explicitly requested or via specific arguments)
    print("🎬 Automated Followspot System Launcher")
    print("=" * 50)
    
    # Load configuration to determine available options
    config = load_launcher_config()
    control_installed = config['installations']['control_stack']['installed']
    node_installed = config['installations']['node_stack']['installed']
    
    # Check dependencies at startup
    if control_installed or node_installed:
        print("🔍 Checking dependencies...")
        if control_installed:
            check_dependencies("control")
        if node_installed:
            check_dependencies("node")
        print()
    
    # Handle specific commands
    if args.check:
        check_config_file()
        print("\n✅ System check complete")
        return
    
    if args.configure:
        launch_config_gui()
        return
    
    if args.reid_config:
        launch_reid_configurator()
        return
    
    if args.run:
        if control_installed:
            launch_client(args.config)
        else:
            print("❌ Control stack not installed. Please install it first or use --gui")
        return
    
    if args.demo:
        if control_installed:
            launch_demo_mode()
        else:
            print("❌ Control stack not installed. Please install it first or use --gui")
        return
    
    if args.node:
        if node_installed:
            launch_node_server()
        else:
            print("❌ Node stack not installed. Please install it first or use --gui")
        return
    
    # Interactive mode based on installed stacks
    if not control_installed and not node_installed:
        print("🚀 No stacks installed. Available options:")
        print("1. Launch GUI installer")
        print("2. Install control stack dependencies")
        print("3. Install node stack dependencies")
        print("4. About")
        print("5. Report bug")
        print("6. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-6): ").strip()
            
            if choice == "1":
                launch_gui()
                break
            elif choice == "2":
                install_dependencies("control")
                # Update config to mark as installed after successful dependency install
                if check_dependencies("control"):
                    config['installations']['control_stack']['installed'] = True
                    config['installations']['control_stack']['version'] = "1.0.0"
                    config['installations']['control_stack']['install_date'] = datetime.now().isoformat()
                    save_launcher_config(config)
                    print("✅ Control stack marked as installed")
                break
            elif choice == "3":
                install_dependencies("node")
                # Update config to mark as installed after successful dependency install
                if check_dependencies("node"):
                    config['installations']['node_stack']['installed'] = True
                    config['installations']['node_stack']['version'] = "1.0.0"
                    config['installations']['node_stack']['install_date'] = datetime.now().isoformat()
                    save_launcher_config(config)
                    print("✅ Node stack marked as installed")
                break
            elif choice == "4":
                print("\n🎬 Automated Followspot System")
                print(f"Version: {config['system_info']['version']}")
                print("A multi-camera IR beacon tracking system")
                print("For more information, visit: https://github.com/Stavro-Purdie/Automated-Followspot-System")
            elif choice == "5":
                print("🐛 Report bugs at: https://github.com/Stavro-Purdie/Automated-Followspot-System/issues")
            elif choice == "6":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-6.")
    
    elif control_installed and not node_installed:
        # Control stack installed
        print("📋 Control Stack Options:")
        print("1. Launch Configuration")
        print("2. Launch ReID Camera Configurator") 
        print("3. Launch Demo Mode")
        print("4. Launch Live Camera Tracking")
        print("5. Install Node Stack")
        print("6. Launch GUI")
        print("7. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-7): ").strip()
            
            if choice == "1":
                launch_config_gui()
                break
            elif choice == "2":
                launch_reid_configurator()
                break
            elif choice == "3":
                launch_demo_mode()
                break
            elif choice == "4":
                if check_config_file():
                    launch_client(args.config)
                else:
                    print("❌ No configuration found. Please configure cameras first (option 1).")
                break
            elif choice == "5":
                install_dependencies("node")
                if check_dependencies("node"):
                    config['installations']['node_stack']['installed'] = True
                    config['installations']['node_stack']['version'] = "1.0.0"
                    config['installations']['node_stack']['install_date'] = datetime.now().isoformat()
                    save_launcher_config(config)
                    print("✅ Node stack installed")
                break
            elif choice == "6":
                launch_gui()
                break
            elif choice == "7":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-7.")
    
    elif node_installed and not control_installed:
        # Node stack installed
        print("📋 Node Stack Options:")
        print("1. Start Node Server")
        print("2. Install Control Stack")
        print("3. Node Diagnostics")
        print("4. Launch GUI")
        print("5. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == "1":
                launch_node_server()
                break
            elif choice == "2":
                install_dependencies("control")
                if check_dependencies("control"):
                    config['installations']['control_stack']['installed'] = True
                    config['installations']['control_stack']['version'] = "1.0.0"
                    config['installations']['control_stack']['install_date'] = datetime.now().isoformat()
                    save_launcher_config(config)
                    print("✅ Control stack installed")
                break
            elif choice == "3":
                print("🔍 Running node diagnostics...")
                print("Node server script exists:", (Path(__file__).parent / "node" / "server.py").exists())
                print("Dependencies OK:", check_dependencies("node"))
                print("Raspberry Pi detected:", is_raspberry_pi())
            elif choice == "4":
                launch_gui()
                break
            elif choice == "5":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-5.")
    
    else:
        # Both stacks installed
        print("📋 What would you like to do?")
        print("1. Launch Configuration (Control)")
        print("2. Launch ReID Camera Configurator (Control)")
        print("3. Launch Demo Mode (Control)")
        print("4. Launch Live Camera Tracking (Control)")
        print("5. Start Node Server")
        print("6. Launch GUI")
        print("7. System Status")
        print("8. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-8): ").strip()
            
            if choice == "1":
                launch_config_gui()
                break
            elif choice == "2":
                launch_reid_configurator()
                break
            elif choice == "3":
                launch_demo_mode()
                break
            elif choice == "4":
                if check_config_file():
                    launch_client(args.config)
                else:
                    print("❌ No configuration found. Please configure cameras first (option 1).")
                break
            elif choice == "5":
                launch_node_server()
                break
            elif choice == "6":
                launch_gui()
                break
            elif choice == "7":
                show_system_status()
            elif choice == "8":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1-8.")

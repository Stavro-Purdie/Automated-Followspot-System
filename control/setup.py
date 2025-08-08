#!/usr/bin/env python3
"""
Multi-Camera System Setup Script
Automates the setup process for the multi-camera followspot system.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def run_command(command, description, verbose=False):
    """Run a command and return success status"""
    print(f"📦 {description}...")
    print(f"🔧 Running command: {command}")
    
    try:
        if verbose:
            # For verbose output, stream the output in real-time
            process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Print output in real-time
            if process.stdout:
                for line in process.stdout:
                    print(f"   {line.rstrip()}")
            
            process.wait()
            
            if process.returncode == 0:
                print(f"✅ {description} completed successfully")
                return True
            else:
                print(f"❌ {description} failed with return code {process.returncode}")
                return False
        else:
            # Non-verbose mode (capture output)
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {description} completed successfully")
                if result.stdout.strip():
                    print(f"   Output: {result.stdout.strip()}")
                return True
            else:
                print(f"❌ {description} failed:")
                if result.stderr.strip():
                    print(f"   Error: {result.stderr.strip()}")
                if result.stdout.strip():
                    print(f"   Output: {result.stdout.strip()}")
                return False
    except Exception as e:
        print(f"❌ {description} failed: {e}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 7:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} is not compatible")
        print("   Requires Python 3.7 or higher")
        return False

def check_existing_dependencies():
    """Check if dependencies are already installed"""
    required_packages = {
        'cv2': 'opencv-python',
        'numpy': 'numpy', 
        'aiohttp': 'aiohttp',
        'aiortc': 'aiortc',
        'PIL': 'pillow'
    }
    
    missing_packages = []
    installed_packages = []
    
    for import_name, package_name in required_packages.items():
        try:
            if import_name == 'cv2':
                import cv2
            elif import_name == 'PIL':
                from PIL import Image
            else:
                __import__(import_name)
            installed_packages.append(package_name)
        except ImportError:
            missing_packages.append(package_name)
    
    if installed_packages:
        print(f"✅ Already installed: {', '.join(installed_packages)}")
    
    if missing_packages:
        print(f"📦 Need to install: {', '.join(missing_packages)}")
        return False
    else:
        print("✅ All dependencies are already installed")
        return True

def find_pip_command():
    """Find the appropriate pip command to use"""
    print("🔍 Looking for pip installation...")
    # Try different pip commands in order of preference
    pip_commands = [
        f"{sys.executable} -m pip",  # Most reliable method
        "pip3",
        "pip"
    ]
    
    for cmd in pip_commands:
        print(f"🔧 Trying command: {cmd} --version")
        try:
            result = subprocess.run(f"{cmd} --version", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Found pip: {cmd}")
                print(f"   Version: {result.stdout.strip()}")
                return cmd
            else:
                print(f"❌ Command failed: {result.stderr.strip()}")
        except Exception as e:
            print(f"❌ Command failed: {e}")
            continue
    
    print("❌ No working pip command found")
    return None

def install_dependencies():
    """Install required Python packages"""
    requirements_file = Path(__file__).parent / "requirements.txt"
    
    if not requirements_file.exists():
        print("❌ requirements.txt not found")
        return False
    
    # Find the appropriate pip command
    pip_cmd = find_pip_command()
    if not pip_cmd:
        print("❌ No pip installation found")
        print("   Please install pip or ensure it's in your PATH")
        print("   Try one of these commands:")
        print("   - python -m ensurepip --upgrade")
        print("   - python3 -m ensurepip --upgrade")
        print("   - brew install python (on macOS)")
        return False
    
    # Create verbose pip command
    verbose_pip_cmd = f"{pip_cmd} install -v -r {requirements_file}"
    
    # Try to install dependencies with verbose output
    success = run_command(
        verbose_pip_cmd,
        "Installing Python dependencies",
        verbose=True
    )
    
    if not success:
        print("\n🔄 Trying alternative installation method...")
        # Try with --user flag in case of permission issues
        user_pip_cmd = f"{pip_cmd} install -v --user -r {requirements_file}"
        success = run_command(
            user_pip_cmd,
            "Installing Python dependencies with --user flag",
            verbose=True
        )
    
    if not success:
        print("\n❌ Automatic installation failed. Please install manually:")
        print(f"   {pip_cmd} install -r {requirements_file}")
        print("   Or install packages individually:")
        with open(requirements_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    print(f"   {pip_cmd} install {line}")
    
    return success

def create_default_config():
    """Create a default configuration file if it doesn't exist"""
    config_file = Path(__file__).parent.parent / "config" / "camera_config.json"
    
    if config_file.exists():
        print(f"✅ Configuration file already exists: {config_file}")
        return True
    
    print("📝 Creating default configuration file...")
    
    default_config = {
        "grid_config": {
            "cameras_per_row": 2,
            "total_cameras": 2,
            "cell_width": 320,
            "cell_height": 240,
            "auto_arrange": True
        },
        "cameras": [
            {
                "server_url": "http://192.168.1.100:8080",
                "crop_rect": [0, 0, 320, 240],
                "position": [0, 0],
                "camera_id": "camera_1",
                "enabled": True,
                "auto_crop": True,
                "overlap_threshold": 0.1
            },
            {
                "server_url": "http://192.168.1.101:8080",
                "crop_rect": [0, 0, 320, 240],
                "position": [1, 0],
                "camera_id": "camera_2",
                "enabled": True,
                "auto_crop": True,
                "overlap_threshold": 0.1
            }
        ]
    }
    
    try:
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        print(f"✅ Default configuration created: {config_file}")
        print("   Edit this file or use the configuration GUI to customize")
        return True
    except Exception as e:
        print(f"❌ Failed to create configuration file: {e}")
        return False

def make_scripts_executable():
    """Make Python scripts executable on Unix-like systems"""
    if os.name != 'posix':
        return True  # Skip on Windows
    
    scripts = [
        "launcher.py",
        "camera_config_gui.py",
        "multi_camera_client.py"
    ]
    
    success = True
    for script in scripts:
        script_path = Path(__file__).parent / script
        if script_path.exists():
            try:
                os.chmod(script_path, 0o755)
                print(f"✅ Made {script} executable")
            except Exception as e:
                print(f"❌ Failed to make {script} executable: {e}")
                success = False
        else:
            print(f"⚠️  Script not found: {script}")
    
    return success

def print_usage_instructions():
    """Print usage instructions"""
    print("\n" + "=" * 60)
    print("🎉 SETUP COMPLETE!")
    print("=" * 60)
    print("\n📋 Next Steps:")
    print("\n1. Configure your cameras:")
    print("   python launcher.py --configure")
    print("   # OR")
    print("   python camera_config_gui.py")
    
    print("\n2. Edit config/camera_config.json to match your network setup:")
    print("   - Update server URLs to match your camera IP addresses")
    print("   - Adjust camera IDs to meaningful names")
    print("   - Configure grid layout as needed")
    
    print("\n3. Ensure your camera servers are running:")
    print("   - Each Raspberry Pi should run server.py")
    print("   - Servers should be accessible on port 8080")
    print("   - Test connectivity from this machine")
    
    print("\n4. Run the multi-camera client:")
    print("   python launcher.py --run")
    print("   # OR")
    print("   python multi_camera_client.py")
    
    print("\n🎛️  Client Controls:")
    print("   q     - Quit")
    print("   +/-   - Adjust IR threshold")
    print("   s     - Save snapshots")
    print("   r     - Reload configuration")
    
    print("\n📁 Important Files:")
    print("   config/camera_config.json     - Camera configuration")
    print("   launcher.py           - Easy launcher script")
    print("   camera_config_gui.py  - Configuration GUI")
    print("   multi_camera_client.py - Main client")
    print("   README_multi_camera.md - Detailed documentation")
    
    print("\n🆘 Need Help?")
    print("   python launcher.py --check  # Check system status")
    print("   Read README_multi_camera.md for detailed instructions")

def main():
    print("🎬 Multi-Camera System Setup")
    print("=" * 40)
    print("📍 Working directory:", os.getcwd())
    print("🐍 Python executable:", sys.executable)
    print("📦 Python version:", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print()
    
    # Check Python version
    print("🔍 Step 1: Checking Python version compatibility...")
    if not check_python_version():
        sys.exit(1)
    print()
    
    # Check if dependencies are already installed
    print("🔍 Step 2: Checking existing dependencies...")
    if not check_existing_dependencies():
        print("\n📦 Step 3: Installing missing dependencies...")
        # Install dependencies if needed
        if not install_dependencies():
            print("\n❌ Setup failed during dependency installation")
            print("   Try installing manually:")
            print("   python -m pip install -r requirements.txt")
            print("   OR")
            print("   python3 -m pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("⏭️  Step 3: Skipping dependency installation (already installed)")
    print()
    
    # Create default configuration
    print("📝 Step 4: Setting up configuration file...")
    create_default_config()
    print()
    
    # Make scripts executable
    print("🔧 Step 5: Making scripts executable...")
    make_scripts_executable()
    print()
    
    # Print usage instructions
    print_usage_instructions()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Setup script for the Automated Followspot System
Installs dependencies for control and/or node stacks
"""

import subprocess
import sys
import os
from pathlib import Path

def install_requirements(requirements_file, stack_name):
    """Install requirements from a requirements.txt file"""
    if not requirements_file.exists():
        print(f"❌ Requirements file not found: {requirements_file}")
        return False
    
    print(f"📦 Installing {stack_name} dependencies...")
    print(f"   Reading from: {requirements_file}")
    
    try:
        # Upgrade pip first
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        
        # Install requirements
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)], check=True)
        
        print(f"✅ {stack_name} dependencies installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing {stack_name} dependencies: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main setup function"""
    print("🎬 Automated Followspot System Setup")
    print("=" * 50)
    
    base_path = Path(__file__).parent
    control_req = base_path / "control" / "requirements.txt"
    node_req = base_path / "node" / "requirements.txt"
    
    # Check which requirements files exist
    control_exists = control_req.exists()
    node_exists = node_req.exists()
    
    if not control_exists and not node_exists:
        print("❌ No requirements files found!")
        print("   Expected files:")
        print(f"   - {control_req}")
        print(f"   - {node_req}")
        return
    
    print("Available installations:")
    options = []
    
    if control_exists:
        print("1. Install Control Stack dependencies")
        options.append(("control", control_req, "Control Stack"))
    
    if node_exists:
        option_num = len(options) + 1
        print(f"{option_num}. Install Node Stack dependencies")
        options.append(("node", node_req, "Node Stack"))
    
    if control_exists and node_exists:
        option_num = len(options) + 1
        print(f"{option_num}. Install Both (Control + Node)")
        options.append(("both", None, "Both Stacks"))
    
    print(f"{len(options) + 1}. Exit")
    
    while True:
        try:
            choice = input(f"\nEnter your choice (1-{len(options) + 1}): ").strip()
            choice_num = int(choice) - 1
            
            if choice_num == len(options):
                print("👋 Setup cancelled")
                return
            elif 0 <= choice_num < len(options):
                stack_type, req_file, stack_name = options[choice_num]
                
                if stack_type == "both":
                    # Install both stacks
                    success = True
                    if control_exists:
                        success &= install_requirements(control_req, "Control Stack")
                    if node_exists and success:
                        success &= install_requirements(node_req, "Node Stack")
                    
                    if success:
                        print("\n🎉 All dependencies installed successfully!")
                        print("You can now run the launcher with: python launcher.py --gui")
                    else:
                        print("\n❌ Some installations failed. Check the error messages above.")
                else:
                    # Install single stack
                    if install_requirements(req_file, stack_name):
                        print(f"\n🎉 {stack_name} setup complete!")
                        print("You can now run the launcher with: python launcher.py --gui")
                    else:
                        print(f"\n❌ {stack_name} setup failed. Check the error messages above.")
                break
            else:
                print("❌ Invalid choice. Please try again.")
                
        except ValueError:
            print("❌ Please enter a valid number.")
        except KeyboardInterrupt:
            print("\n👋 Setup cancelled")
            return

if __name__ == "__main__":
    main()

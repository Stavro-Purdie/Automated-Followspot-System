#!/usr/bin/env python3
"""
Test script for the installation wizard and status GUI
"""

import sys
from pathlib import Path

# Add parent directory to path to access launcher.py
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_status_gui():
    """Test the status GUI"""
    print("Testing Status GUI...")
    try:
        from launcher import launch_gui_status
        print("✅ Status GUI function imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import status GUI: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing status GUI: {e}")
        return False

def test_installer_wizard():
    """Test the installer wizard"""
    print("Testing Installer Wizard...")
    try:
        from installer_wizard import InstallationWizard
        print("✅ Installation wizard imported successfully")
        
        # Try to create wizard instance (don't run it)
        wizard = InstallationWizard()
        print("✅ Installation wizard instance created successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import installer wizard: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing installer wizard: {e}")
        return False

def test_launcher_integration():
    """Test launcher integration"""
    print("Testing Launcher Integration...")
    try:
        from launcher import launch_gui_installer
        print("✅ Launcher installer function imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import launcher installer: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing launcher integration: {e}")
        return False

def test_gui_launcher():
    """Test GUI launcher script"""
    print("Testing GUI Launcher Script...")
    try:
        from launcher_gui import LauncherGUI, StatusWindow
        print("✅ GUI launcher classes imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Failed to import GUI launcher: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing GUI launcher: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Testing Automated Followspot System Installation Components")
    print("=" * 60)
    
    tests = [
        test_status_gui,
        test_installer_wizard,
        test_launcher_integration,
        test_gui_launcher
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! The consolidated system is ready to use.")
        print("\nTo use the system:")
        print("• Main launcher: python launcher.py")
        print("• Status GUI: python launcher.py status") 
        print("• Installation Wizard: python installer_scripts/installer_wizard.py")
        print("• Full GUI: python installer_scripts/launcher_gui.py")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

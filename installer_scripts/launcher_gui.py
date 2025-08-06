#!/usr/bin/env python3
"""
GUI Launcher for Automated Followspot System
Provides graphical interface for installation, configuration, and management of Control and Node stacks.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import os
import sys
import subprocess
import threading
import time
import platform
from pathlib import Path
from datetime import datetime, timedelta
import queue
import webbrowser

class LauncherGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Automated Followspot System Launcher")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        # Initialize configuration
        self.config_file = Path(__file__).parent.parent / "config" / "launcher_config.json"
        self.config = self.load_config()
        
        # Terminal output queue for installations
        self.terminal_queue = queue.Queue()
        
        # Setup GUI
        self.setup_styles()
        self.create_widgets()
        self.update_ui_state()
        
        # Start periodic checks
        self.root.after(1000, self.periodic_checks)
    
    def load_config(self):
        """Load launcher configuration"""
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
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
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
                messagebox.showerror("Configuration Error", f"Failed to load config: {e}")
                return default_config
        else:
            # Create config directory if it doesn't exist
            Path(self.config_file).parent.mkdir(exist_ok=True)
            return default_config
    
    def save_config(self):
        """Save launcher configuration"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Failed to save config: {e}")
    
    def setup_styles(self):
        """Setup custom styles for the GUI"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Define custom colors
        self.colors = {
            'primary': '#2E86AB',
            'secondary': '#A23B72',
            'success': '#F18F01',
            'warning': '#C73E1D',
            'background': '#F5F5F5',
            'text': '#333333'
        }
        
        # Configure styles
        self.style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        self.style.configure('Subtitle.TLabel', font=('Arial', 12, 'bold'))
        self.style.configure('Status.TLabel', font=('Arial', 10))
        self.style.configure('Primary.TButton', font=('Arial', 10, 'bold'))
    
    def create_widgets(self):
        """Create the main GUI widgets"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Automated Followspot System", style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # System status frame
        self.create_status_frame(main_frame)
        
        # Installation options frame
        self.create_installation_frame(main_frame)
        
        # Control options frame (shown when control stack is installed)
        self.create_control_frame(main_frame)
        
        # Node options frame (shown when node stack is installed)
        self.create_node_frame(main_frame)
        
        # General options frame
        self.create_general_frame(main_frame)
        
        # Terminal output frame
        self.create_terminal_frame(main_frame)
    
    def create_status_frame(self, parent):
        """Create system status display"""
        status_frame = ttk.LabelFrame(parent, text="System Status", padding="10")
        status_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Control stack status
        self.control_status_label = ttk.Label(status_frame, text="Control Stack: Not Installed", style='Status.TLabel')
        self.control_status_label.grid(row=0, column=0, sticky=(tk.W), padx=(0, 20))
        
        # Node stack status
        self.node_status_label = ttk.Label(status_frame, text="Node Stack: Not Installed", style='Status.TLabel')
        self.node_status_label.grid(row=0, column=1, sticky=(tk.W), padx=(0, 20))
        
        # Dependencies status
        self.deps_status_label = ttk.Label(status_frame, text="Dependencies: Checking...", style='Status.TLabel')
        self.deps_status_label.grid(row=1, column=0, sticky=(tk.W), padx=(0, 20))
        
        # Last check time
        self.check_time_label = ttk.Label(status_frame, text="Last Check: Never", style='Status.TLabel')
        self.check_time_label.grid(row=1, column=1, sticky=(tk.W))
    
    def create_installation_frame(self, parent):
        """Create installation options (shown when no stacks are installed)"""
        self.install_frame = ttk.LabelFrame(parent, text="Installation Options", padding="10")
        self.install_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Installation buttons
        ttk.Button(self.install_frame, text="Install Control Stack", 
                  command=self.install_control_stack, style='Primary.TButton').grid(row=0, column=0, padx=(0, 10))
        
        ttk.Button(self.install_frame, text="Install Node Stack", 
                  command=self.install_node_stack, style='Primary.TButton').grid(row=0, column=1, padx=(0, 10))
        
        # Info labels
        ttk.Label(self.install_frame, text="Control Stack: Camera management and tracking interface").grid(row=1, column=0, sticky=(tk.W), pady=(5, 0))
        ttk.Label(self.install_frame, text="Node Stack: Camera server for streaming and capture").grid(row=1, column=1, sticky=(tk.W), pady=(5, 0))
    
    def create_control_frame(self, parent):
        """Create control stack options"""
        self.control_frame = ttk.LabelFrame(parent, text="Control Stack", padding="10")
        self.control_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Operation buttons
        ttk.Button(self.control_frame, text="Launch Configuration", 
                  command=self.launch_configuration).grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.control_frame, text="Offline Mode", 
                  command=self.launch_offline_mode).grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.control_frame, text="Live Mode", 
                  command=self.launch_live_mode).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Maintenance options
        ttk.Separator(self.control_frame, orient='horizontal').grid(row=3, column=0, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Button(self.control_frame, text="Repair Installation", 
                  command=self.repair_control).grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.control_frame, text="Uninstall", 
                  command=self.uninstall_control).grid(row=5, column=0, sticky=(tk.W, tk.E))
        
        self.control_frame.columnconfigure(0, weight=1)
    
    def create_node_frame(self, parent):
        """Create node stack options"""
        self.node_frame = ttk.LabelFrame(parent, text="Node Stack", padding="10")
        self.node_frame.grid(row=3, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        # Status and control
        self.node_running_label = ttk.Label(self.node_frame, text="Status: Stopped")
        self.node_running_label.grid(row=0, column=0, sticky=(tk.W), pady=(0, 10))
        
        ttk.Button(self.node_frame, text="Start Node Server", 
                  command=self.start_node_server).grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.node_frame, text="Stop Node Server", 
                  command=self.stop_node_server).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Cron job management
        ttk.Separator(self.node_frame, orient='horizontal').grid(row=3, column=0, sticky=(tk.W, tk.E), pady=10)
        
        self.cron_var = tk.BooleanVar()
        self.cron_checkbox = ttk.Checkbutton(self.node_frame, text="Start at Boot (Cron)", 
                                           variable=self.cron_var, command=self.toggle_cron)
        self.cron_checkbox.grid(row=4, column=0, sticky=(tk.W), pady=(0, 5))
        
        # Maintenance options
        ttk.Button(self.node_frame, text="Diagnostics", 
                  command=self.node_diagnostics).grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.node_frame, text="Repair Installation", 
                  command=self.repair_node).grid(row=6, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.node_frame, text="Reinstall", 
                  command=self.reinstall_node).grid(row=7, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(self.node_frame, text="Uninstall", 
                  command=self.uninstall_node).grid(row=8, column=0, sticky=(tk.W, tk.E))
        
        self.node_frame.columnconfigure(0, weight=1)
    
    def create_general_frame(self, parent):
        """Create general options"""
        general_frame = ttk.LabelFrame(parent, text="General", padding="10")
        general_frame.grid(row=3, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        ttk.Button(general_frame, text="About", 
                  command=self.show_about).grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(general_frame, text="Report Bug", 
                  command=self.report_bug).grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(general_frame, text="Check Updates", 
                  command=self.check_updates).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(general_frame, text="Settings", 
                  command=self.show_settings).grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Separator(general_frame, orient='horizontal').grid(row=4, column=0, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Button(general_frame, text="Exit", 
                  command=self.root.quit).grid(row=5, column=0, sticky=(tk.W, tk.E))
        
        general_frame.columnconfigure(0, weight=1)
    
    def create_terminal_frame(self, parent):
        """Create terminal output display"""
        terminal_frame = ttk.LabelFrame(parent, text="Terminal Output", padding="10")
        terminal_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        
        # Terminal text widget
        self.terminal_text = scrolledtext.ScrolledText(terminal_frame, height=15, width=80, 
                                                       font=('Consolas', 9), bg='black', fg='white')
        self.terminal_text.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Terminal controls
        ttk.Button(terminal_frame, text="Clear", 
                  command=self.clear_terminal).grid(row=1, column=0, sticky=(tk.W), pady=(5, 0))
        
        ttk.Button(terminal_frame, text="Save Log", 
                  command=self.save_terminal_log).grid(row=1, column=1, sticky=(tk.E), pady=(5, 0))
        
        terminal_frame.columnconfigure(0, weight=1)
        terminal_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)
    
    def update_ui_state(self):
        """Update UI state based on current configuration"""
        control_installed = self.config['installations']['control_stack']['installed']
        node_installed = self.config['installations']['node_stack']['installed']
        
        # Update status labels
        if control_installed:
            version = self.config['installations']['control_stack'].get('version', 'Unknown')
            self.control_status_label.config(text=f"Control Stack: Installed (v{version})")
        else:
            self.control_status_label.config(text="Control Stack: Not Installed")
        
        if node_installed:
            version = self.config['installations']['node_stack'].get('version', 'Unknown')
            self.node_status_label.config(text=f"Node Stack: Installed (v{version})")
        else:
            self.node_status_label.config(text="Node Stack: Not Installed")
        
        # Show/hide appropriate frames
        if not control_installed and not node_installed:
            self.install_frame.grid()
            self.control_frame.grid_remove()
            self.node_frame.grid_remove()
        else:
            self.install_frame.grid_remove()
            if control_installed:
                self.control_frame.grid()
            else:
                self.control_frame.grid_remove()
            if node_installed:
                self.node_frame.grid()
                # Update cron checkbox
                self.cron_var.set(self.config['installations']['node_stack'].get('cron_enabled', False))
            else:
                self.node_frame.grid_remove()
        
        # Update dependencies status
        self.check_dependencies_async()
    
    def check_dependencies_async(self):
        """Check dependencies in background thread"""
        def check_deps():
            try:
                # Check control dependencies
                if self.config['installations']['control_stack']['installed']:
                    control_deps = self.check_dependencies('control')
                else:
                    control_deps = True
                
                # Check node dependencies
                if self.config['installations']['node_stack']['installed']:
                    node_deps = self.check_dependencies('node')
                else:
                    node_deps = True
                
                # Update UI
                self.root.after(0, self.update_deps_status, control_deps and node_deps)
                
            except Exception as e:
                self.log_to_terminal(f"Error checking dependencies: {e}")
                self.root.after(0, self.update_deps_status, False)
        
        threading.Thread(target=check_deps, daemon=True).start()
    
    def check_dependencies(self, stack_type):
        """Check if dependencies are installed for given stack"""
        try:
            if stack_type == 'control':
                requirements_file = Path(__file__).parent.parent / "control" / "requirements.txt"
            else:
                requirements_file = Path(__file__).parent.parent / "node" / "requirements.txt"
            
            if not requirements_file.exists():
                return False
            
            # Read requirements
            with open(requirements_file, 'r') as f:
                requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            # Check each requirement
            for requirement in requirements:
                try:
                    # Simple package name extraction (handles basic cases)
                    package_name = requirement.split('>=')[0].split('==')[0].split('[')[0].strip()
                    
                    if package_name == 'opencv-python':
                        import cv2
                    elif package_name == 'pillow':
                        from PIL import Image
                    elif package_name == 'picamera2':
                        # Skip picamera2 on non-Pi systems
                        if not self.is_raspberry_pi():
                            continue
                        import picamera2
                    else:
                        __import__(package_name.replace('-', '_'))
                except ImportError:
                    return False
            
            return True
            
        except Exception as e:
            self.log_to_terminal(f"Error checking {stack_type} dependencies: {e}")
            return False
    
    def is_raspberry_pi(self):
        """Check if running on Raspberry Pi"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
            return 'BCM' in cpuinfo or 'Raspberry Pi' in cpuinfo
        except:
            return False
    
    def update_deps_status(self, deps_ok):
        """Update dependencies status in UI"""
        if deps_ok:
            self.deps_status_label.config(text="Dependencies: OK")
        else:
            self.deps_status_label.config(text="Dependencies: Missing/Issues")
        
        # Update last check time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.check_time_label.config(text=f"Last Check: {now}")
        
        # Update config
        for stack in ['control_stack', 'node_stack']:
            if self.config['installations'][stack]['installed']:
                self.config['installations'][stack]['dependencies_verified'] = deps_ok
                self.config['installations'][stack]['last_dependency_check'] = now
        
        self.save_config()
    
    def periodic_checks(self):
        """Perform periodic system checks"""
        if self.config['settings']['auto_dependency_check']:
            last_check = None
            for stack in ['control_stack', 'node_stack']:
                if self.config['installations'][stack]['installed']:
                    check_date = self.config['installations'][stack].get('last_dependency_check')
                    if check_date:
                        try:
                            last_check_dt = datetime.fromisoformat(check_date.replace('Z', '+00:00'))
                            if last_check is None or last_check_dt < last_check:
                                last_check = last_check_dt
                        except:
                            pass
            
            # Check if we need to run dependency check
            if last_check is None or (datetime.now() - last_check).days >= self.config['settings']['check_interval_days']:
                self.check_dependencies_async()
        
        # Schedule next check
        self.root.after(60000, self.periodic_checks)  # Check every minute
    
    def log_to_terminal(self, message):
        """Add message to terminal output"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.terminal_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.terminal_text.see(tk.END)
        self.root.update_idletasks()
    
    def clear_terminal(self):
        """Clear terminal output"""
        self.terminal_text.delete(1.0, tk.END)
    
    def save_terminal_log(self):
        """Save terminal log to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.terminal_text.get(1.0, tk.END))
                messagebox.showinfo("Success", f"Log saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save log: {e}")
    
    # Installation methods
    def install_control_stack(self):
        """Install control stack with GUI installer"""
        self.run_installer("control")
    
    def install_node_stack(self):
        """Install node stack with GUI installer"""
        self.run_installer("node")
    
    def run_installer(self, stack_type):
        """Run installer for specified stack type"""
        installer_window = InstallerWindow(self, stack_type)
        installer_window.show()
    
    # Control stack methods
    def launch_configuration(self):
        """Launch camera configuration GUI"""
        script_path = Path(__file__).parent.parent / "control" / "camera_config_gui.py"
        self.run_script(script_path, "Camera Configuration")
    
    def launch_offline_mode(self):
        """Launch control stack in offline/demo mode"""
        script_path = Path(__file__).parent.parent / "control" / "main.py"
        self.run_script(script_path, "Offline Mode", ["--demo"])
    
    def launch_live_mode(self):
        """Launch control stack in live mode"""
        # Check if configuration exists
        config_path = Path(__file__).parent.parent / "config" / "camera_config.json"
        if not config_path.exists():
            if messagebox.askyesno("Configuration Missing", 
                                 "No camera configuration found. Would you like to configure cameras first?"):
                self.launch_configuration()
                return
        
        script_path = Path(__file__).parent.parent / "control" / "main.py"
        self.run_script(script_path, "Live Mode")
    
    def repair_control(self):
        """Repair control stack installation"""
        if messagebox.askyesno("Repair Control Stack", 
                             "This will reinstall dependencies and verify the installation. Continue?"):
            self.run_installer("control", repair_mode=True)
    
    def uninstall_control(self):
        """Uninstall control stack"""
        if messagebox.askyesno("Uninstall Control Stack", 
                             "This will remove the control stack installation. Continue?"):
            self.config['installations']['control_stack']['installed'] = False
            self.config['installations']['control_stack']['version'] = None
            self.config['installations']['control_stack']['install_date'] = None
            self.save_config()
            self.update_ui_state()
            self.log_to_terminal("Control stack uninstalled")
    
    # Node stack methods
    def start_node_server(self):
        """Start node server"""
        script_path = Path(__file__).parent.parent / "node" / "server.py"
        self.run_script(script_path, "Node Server", background=True)
    
    def stop_node_server(self):
        """Stop node server"""
        # This would need process management to track and stop the server
        self.log_to_terminal("Stop node server functionality not yet implemented")
    
    def toggle_cron(self):
        """Toggle cron job for node server"""
        enabled = self.cron_var.get()
        self.config['installations']['node_stack']['cron_enabled'] = enabled
        self.save_config()
        
        action = "enabled" if enabled else "disabled"
        self.log_to_terminal(f"Cron job {action} for node server")
        
        # TODO: Implement actual cron job management
    
    def node_diagnostics(self):
        """Run node diagnostics"""
        DiagnosticsWindow(self, "node").show()
    
    def repair_node(self):
        """Repair node stack installation"""
        if messagebox.askyesno("Repair Node Stack", 
                             "This will reinstall dependencies and verify the installation. Continue?"):
            self.run_installer("node", repair_mode=True)
    
    def reinstall_node(self):
        """Reinstall node stack"""
        if messagebox.askyesno("Reinstall Node Stack", 
                             "This will completely reinstall the node stack. Continue?"):
            self.run_installer("node", reinstall_mode=True)
    
    def uninstall_node(self):
        """Uninstall node stack"""
        if messagebox.askyesno("Uninstall Node Stack", 
                             "This will remove the node stack installation. Continue?"):
            self.config['installations']['node_stack']['installed'] = False
            self.config['installations']['node_stack']['version'] = None
            self.config['installations']['node_stack']['install_date'] = None
            self.config['installations']['node_stack']['cron_enabled'] = False
            self.save_config()
            self.update_ui_state()
            self.log_to_terminal("Node stack uninstalled")
    
    # General methods
    def show_about(self):
        """Show about dialog"""
        AboutWindow(self).show()
    
    def report_bug(self):
        """Open bug report URL"""
        url = "https://github.com/Stavro-Purdie/Automated-Followspot-System/issues"
        webbrowser.open(url)
        self.log_to_terminal(f"Opened bug report URL: {url}")
    
    def check_updates(self):
        """Check for system updates"""
        self.log_to_terminal("Checking for updates...")
        # TODO: Implement update checking
        messagebox.showinfo("Updates", "Update checking not yet implemented")
    
    def show_settings(self):
        """Show settings dialog"""
        SettingsWindow(self).show()
    
    def run_script(self, script_path, description, args=None, background=False):
        """Run a Python script"""
        if not script_path.exists():
            messagebox.showerror("Error", f"Script not found: {script_path}")
            return
        
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)
        
        self.log_to_terminal(f"Starting {description}...")
        
        try:
            if background:
                subprocess.Popen(cmd, cwd=script_path.parent)
                self.log_to_terminal(f"{description} started in background")
            else:
                # Run in foreground and capture output
                def run_process():
                    try:
                        process = subprocess.Popen(
                            cmd, 
                            cwd=script_path.parent,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            universal_newlines=True
                        )
                        
                        for line in process.stdout:
                            self.root.after(0, self.log_to_terminal, line.strip())
                        
                        process.wait()
                        self.root.after(0, self.log_to_terminal, f"{description} completed with exit code {process.returncode}")
                        
                    except Exception as e:
                        self.root.after(0, self.log_to_terminal, f"Error running {description}: {e}")
                
                threading.Thread(target=run_process, daemon=True).start()
                
        except Exception as e:
            self.log_to_terminal(f"Error starting {description}: {e}")
    
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()


class InstallerWindow:
    """GUI installer window for control or node stack"""
    
    def __init__(self, parent, stack_type, repair_mode=False, reinstall_mode=False):
        self.parent = parent
        self.stack_type = stack_type
        self.repair_mode = repair_mode
        self.reinstall_mode = reinstall_mode
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"Install {stack_type.title()} Stack")
        self.window.geometry("700x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        
        self.setup_installer_ui()
    
    def setup_installer_ui(self):
        """Setup installer UI"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = f"{'Repair' if self.repair_mode else 'Reinstall' if self.reinstall_mode else 'Install'} {self.stack_type.title()} Stack"
        ttk.Label(main_frame, text=title, font=('Arial', 14, 'bold')).pack(pady=(0, 20))
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Ready to install...")
        self.status_label.pack(pady=(0, 10))
        
        # Terminal output
        self.terminal = scrolledtext.ScrolledText(main_frame, height=20, font=('Consolas', 9))
        self.terminal.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        self.install_button = ttk.Button(button_frame, text="Start Installation", command=self.start_installation)
        self.install_button.pack(side=tk.LEFT)
        
        self.close_button = ttk.Button(button_frame, text="Close", command=self.close_window, state=tk.DISABLED)
        self.close_button.pack(side=tk.RIGHT)
    
    def log(self, message):
        """Log message to installer terminal"""
        self.terminal.insert(tk.END, f"{message}\n")
        self.terminal.see(tk.END)
        self.window.update_idletasks()
    
    def start_installation(self):
        """Start the installation process"""
        self.install_button.config(state=tk.DISABLED)
        self.progress.start()
        
        def install_process():
            try:
                self.window.after(0, lambda: self.status_label.config(text="Installing dependencies..."))
                
                # Install dependencies
                if self.stack_type == "control":
                    requirements_file = Path(__file__).parent.parent / "control" / "requirements.txt"
                else:
                    requirements_file = Path(__file__).parent.parent / "node" / "requirements.txt"
                
                if requirements_file.exists():
                    self.window.after(0, self.log, f"Installing dependencies from {requirements_file}")
                    
                    # Run pip install
                    cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        universal_newlines=True
                    )
                    
                    for line in process.stdout:
                        self.window.after(0, self.log, line.strip())
                    
                    process.wait()
                    
                    if process.returncode == 0:
                        self.window.after(0, self.log, "Dependencies installed successfully")
                    else:
                        self.window.after(0, self.log, f"Dependency installation failed with code {process.returncode}")
                        self.window.after(0, self.installation_failed)
                        return
                
                # Mark as installed
                self.window.after(0, lambda: self.status_label.config(text="Finalizing installation..."))
                
                install_date = datetime.now().isoformat()
                self.parent.config['installations'][f'{self.stack_type}_stack']['installed'] = True
                self.parent.config['installations'][f'{self.stack_type}_stack']['version'] = "1.0.0"
                self.parent.config['installations'][f'{self.stack_type}_stack']['install_date'] = install_date
                self.parent.config['installations'][f'{self.stack_type}_stack']['dependencies_verified'] = True
                self.parent.config['installations'][f'{self.stack_type}_stack']['last_dependency_check'] = install_date
                
                self.parent.save_config()
                
                self.window.after(0, self.installation_completed)
                
            except Exception as e:
                self.window.after(0, self.log, f"Installation error: {e}")
                self.window.after(0, self.installation_failed)
        
        threading.Thread(target=install_process, daemon=True).start()
    
    def installation_completed(self):
        """Handle successful installation completion"""
        self.progress.stop()
        self.status_label.config(text="Installation completed successfully!")
        self.log("Installation completed successfully!")
        self.close_button.config(state=tk.NORMAL)
        
        # Update parent UI
        self.parent.update_ui_state()
    
    def installation_failed(self):
        """Handle installation failure"""
        self.progress.stop()
        self.status_label.config(text="Installation failed!")
        self.close_button.config(state=tk.NORMAL)
        self.install_button.config(state=tk.NORMAL)
    
    def close_window(self):
        """Close installer window"""
        self.window.destroy()
    
    def show(self):
        """Show the installer window"""
        self.window.deiconify()


class StatusWindow:
    """GUI Status window for system status display"""
    
    def __init__(self, parent):
        self.parent = parent
        
        self.window = tk.Toplevel()
        self.window.title("System Status - Automated Followspot System")
        self.window.geometry("800x600")
        self.window.resizable(True, True)
        
        # Center the window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (800 // 2)
        y = (self.window.winfo_screenheight() // 2) - (600 // 2)
        self.window.geometry(f"800x600+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup status window UI"""
        # Main frame
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_frame, text="System Status", font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Create notebook for tabbed interface
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # System Overview Tab
        overview_frame = ttk.Frame(notebook)
        notebook.add(overview_frame, text="System Overview")
        self.create_system_overview_tab(overview_frame)
        
        # Installation Status Tab
        install_frame = ttk.Frame(notebook)
        notebook.add(install_frame, text="Installation Status")
        self.create_installation_status_tab(install_frame)
        
        # Dependencies Tab
        deps_frame = ttk.Frame(notebook)
        notebook.add(deps_frame, text="Dependencies")
        self.create_dependencies_tab(deps_frame)
        
        # System Information Tab
        sysinfo_frame = ttk.Frame(notebook)
        notebook.add(sysinfo_frame, text="System Information")
        self.create_system_info_tab(sysinfo_frame)
        
        # Close button
        close_button = ttk.Button(main_frame, text="Close", command=self.window.destroy)
        close_button.pack()
    
    def create_system_overview_tab(self, parent):
        """Create system overview tab"""
        # Scrollable frame
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Load configuration
        config = self.parent.load_config()
        
        # System Status Section
        status_frame = ttk.LabelFrame(scrollable_frame, text="System Status", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Overall health indicator
        control_installed = config.get("installations", {}).get("control_stack", {}).get("installed", False)
        node_installed = config.get("installations", {}).get("node_stack", {}).get("installed", False)
        
        if control_installed or node_installed:
            status_color = "green"
            status_text = "System Ready"
            status_icon = "✅"
        else:
            status_color = "red"
            status_text = "Not Installed"
            status_icon = "❌"
        
        status_label = ttk.Label(status_frame, text=f"{status_icon} {status_text}", 
                                font=('Arial', 14, 'bold'))
        status_label.pack()
        
        # Installation Summary
        install_frame = ttk.LabelFrame(scrollable_frame, text="Installation Summary", padding=10)
        install_frame.pack(fill=tk.X, pady=(0, 10))
        
        if control_installed:
            ttk.Label(install_frame, text="✅ Control Stack: Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
            install_date = config.get("installations", {}).get("control_stack", {}).get("install_date")
            if install_date:
                ttk.Label(install_frame, text=f"   Installed: {install_date[:10]}", 
                         font=('Arial', 9), foreground="gray").pack(anchor=tk.W)
        else:
            ttk.Label(install_frame, text="❌ Control Stack: Not Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
        
        if node_installed:
            ttk.Label(install_frame, text="✅ Node Stack: Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
            install_date = config.get("installations", {}).get("node_stack", {}).get("install_date")
            if install_date:
                ttk.Label(install_frame, text=f"   Installed: {install_date[:10]}", 
                         font=('Arial', 9), foreground="gray").pack(anchor=tk.W)
        else:
            ttk.Label(install_frame, text="❌ Node Stack: Not Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
        
        # Quick Actions
        actions_frame = ttk.LabelFrame(scrollable_frame, text="Quick Actions", padding=10)
        actions_frame.pack(fill=tk.X, pady=(0, 10))
        
        action_buttons_frame = ttk.Frame(actions_frame)
        action_buttons_frame.pack()
        
        if control_installed:
            ttk.Button(action_buttons_frame, text="Launch Control Stack",
                      command=lambda: self.launch_stack('control')).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(action_buttons_frame, text="Demo Mode",
                      command=lambda: self.launch_demo()).pack(side=tk.LEFT, padx=(0, 10))
        
        if node_installed:
            ttk.Button(action_buttons_frame, text="Launch Node Stack",
                      command=lambda: self.launch_stack('node')).pack(side=tk.LEFT, padx=(0, 10))
        
        if not (control_installed or node_installed):
            ttk.Button(action_buttons_frame, text="Run Installation Wizard",
                      command=self.launch_installer_wizard).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_buttons_frame, text="Check Dependencies",
                  command=self.check_dependencies).pack(side=tk.LEFT)
        
        # Pack scrollable components
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_installation_status_tab(self, parent):
        """Create installation status tab"""
        config = self.parent.load_config()
        
        # Scrollable text widget
        text_widget = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Consolas', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Format installation status
        status_text = "AUTOMATED FOLLOWSPOT SYSTEM - INSTALLATION STATUS\n"
        status_text += "=" * 60 + "\n\n"
        
        # System Info
        system_info = config.get("system_info", {})
        status_text += "System Information:\n"
        status_text += f"  Version: {system_info.get('version', 'Unknown')}\n"
        status_text += f"  Last Updated: {system_info.get('last_updated', 'Unknown')}\n"
        status_text += f"  OS: {system_info.get('os_info', 'Unknown')}\n"
        status_text += f"  Installation Path: {system_info.get('installation_path', 'Unknown')}\n\n"
        
        # Installation Status
        installations = config.get("installations", {})
        
        for stack_name, stack_info in installations.items():
            stack_display = stack_name.replace('_', ' ').title()
            status_text += f"{stack_display}:\n"
            
            if stack_info.get("installed", False):
                status_text += "  Status: ✅ INSTALLED\n"
                status_text += f"  Version: {stack_info.get('version', 'Unknown')}\n"
                status_text += f"  Install Date: {stack_info.get('install_date', 'Unknown')}\n"
                
                if stack_info.get("dependencies_verified", False):
                    status_text += "  Dependencies: ✅ VERIFIED\n"
                else:
                    status_text += "  Dependencies: ❌ NOT VERIFIED\n"
                
                last_check = stack_info.get("last_dependency_check")
                if last_check:
                    status_text += f"  Last Dependency Check: {last_check[:10]}\n"
                
                if stack_name == "node_stack":
                    cron_enabled = stack_info.get("cron_enabled", False)
                    status_text += f"  Auto-start: {'✅ ENABLED' if cron_enabled else '❌ DISABLED'}\n"
            else:
                status_text += "  Status: ❌ NOT INSTALLED\n"
            
            status_text += "\n"
        
        # Settings
        settings = config.get("settings", {})
        status_text += "Settings:\n"
        status_text += f"  Auto Dependency Check: {'Enabled' if settings.get('auto_dependency_check', True) else 'Disabled'}\n"
        status_text += f"  Check Interval: {settings.get('check_interval_days', 7)} days\n"
        status_text += f"  Allow Concurrent Stacks: {'Yes' if settings.get('allow_concurrent_stacks', False) else 'No'}\n"
        status_text += f"  Debug Mode: {'Enabled' if settings.get('debug_mode', False) else 'Disabled'}\n"
        
        text_widget.insert(tk.END, status_text)
        text_widget.config(state=tk.DISABLED)
    
    def create_dependencies_tab(self, parent):
        """Create dependencies tab"""
        deps_frame = ttk.Frame(parent)
        deps_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header
        ttk.Label(deps_frame, text="Python Dependencies", font=('Arial', 12, 'bold')).pack(pady=(0, 10))
        
        # Check button
        check_frame = ttk.Frame(deps_frame)
        check_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(check_frame, text="Check All Dependencies", 
                  command=self.check_all_dependencies).pack(side=tk.LEFT)
        ttk.Button(check_frame, text="Install Missing Dependencies", 
                  command=self.install_missing_dependencies).pack(side=tk.LEFT, padx=(10, 0))
        
        # Dependencies list
        self.deps_text = scrolledtext.ScrolledText(deps_frame, wrap=tk.WORD, font=('Consolas', 9))
        self.deps_text.pack(fill=tk.BOTH, expand=True)
        
        # Load initial dependency status
        self.update_dependencies_display()
    
    def create_system_info_tab(self, parent):
        """Create system information tab"""
        import platform
        import sys
        
        # Scrollable text widget
        text_widget = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Consolas', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Gather system information
        info_text = "SYSTEM INFORMATION\n"
        info_text += "=" * 40 + "\n\n"
        
        info_text += "Python Information:\n"
        info_text += f"  Version: {sys.version}\n"
        info_text += f"  Executable: {sys.executable}\n"
        info_text += f"  Platform: {sys.platform}\n\n"
        
        info_text += "Operating System:\n"
        info_text += f"  System: {platform.system()}\n"
        info_text += f"  Release: {platform.release()}\n"
        info_text += f"  Version: {platform.version()}\n"
        info_text += f"  Machine: {platform.machine()}\n"
        info_text += f"  Processor: {platform.processor()}\n\n"
        
        # Disk space
        try:
            import shutil
            total, used, free = shutil.disk_usage(str(Path(__file__).parent))
            info_text += "Disk Space:\n"
            info_text += f"  Total: {total // (1024**3)} GB\n"
            info_text += f"  Used: {used // (1024**3)} GB\n"
            info_text += f"  Free: {free // (1024**3)} GB\n\n"
        except:
            info_text += "Disk Space: Unable to determine\n\n"
        
        # Project structure
        info_text += "Project Structure:\n"
        try:
            project_root = Path(__file__).parent
            for item in sorted(project_root.iterdir()):
                if item.is_dir():
                    info_text += f"  📁 {item.name}/\n"
                else:
                    info_text += f"  📄 {item.name}\n"
        except:
            info_text += "  Unable to read project structure\n"
        
        text_widget.insert(tk.END, info_text)
        text_widget.config(state=tk.DISABLED)
    
    def launch_installer_wizard(self):
        """Launch the installation wizard"""
        try:
            import subprocess
            import sys
            wizard_script = Path(__file__).parent / "installer_wizard.py"
            
            if wizard_script.exists():
                subprocess.Popen([sys.executable, str(wizard_script)])
                messagebox.showinfo("Installation Wizard", 
                                  "Installation wizard launched successfully!")
            else:
                messagebox.showerror("Error", "Installation wizard not found!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch installation wizard: {e}")
    
    def check_all_dependencies(self):
        """Check all dependencies and update display"""
        self.deps_text.delete(1.0, tk.END)
        self.deps_text.insert(tk.END, "Checking dependencies...\n")
        self.deps_text.update()
        
        # Run dependency check in background
        threading.Thread(target=self._check_dependencies_background, daemon=True).start()
    
    def _check_dependencies_background(self):
        """Background dependency check"""
        try:
            result = self.parent.check_dependencies()
            self.window.after(0, lambda: self.update_dependencies_display(result))
        except Exception as e:
            self.window.after(0, lambda: self.deps_text.insert(tk.END, f"Error checking dependencies: {e}\n"))
    
    def update_dependencies_display(self, check_result=None):
        """Update dependencies display"""
        if check_result is None:
            self.deps_text.delete(1.0, tk.END)
            self.deps_text.insert(tk.END, "Dependencies status will appear here after checking.\n\n")
            self.deps_text.insert(tk.END, "Click 'Check All Dependencies' to scan for installed packages.")
            return
        
        self.deps_text.delete(1.0, tk.END)
        
        # Format the dependency check results
        for stack_type, status in check_result.items():
            if stack_type == "overall_status":
                continue
                
            stack_display = stack_type.replace('_', ' ').title()
            self.deps_text.insert(tk.END, f"{stack_display} Dependencies:\n")
            self.deps_text.insert(tk.END, "=" * (len(stack_display) + 15) + "\n")
            
            if "error" in status:
                self.deps_text.insert(tk.END, f"❌ Error: {status['error']}\n\n")
                continue
            
            if status.get("all_satisfied", False):
                self.deps_text.insert(tk.END, "✅ All dependencies satisfied\n\n")
            else:
                self.deps_text.insert(tk.END, "❌ Some dependencies missing\n\n")
            
            # List all dependencies
            for dep, info in status.get("dependencies", {}).items():
                if info["satisfied"]:
                    self.deps_text.insert(tk.END, f"  ✅ {dep}")
                    if info.get("version"):
                        self.deps_text.insert(tk.END, f" (v{info['version']})")
                    self.deps_text.insert(tk.END, "\n")
                else:
                    self.deps_text.insert(tk.END, f"  ❌ {dep} - NOT INSTALLED\n")
            
            self.deps_text.insert(tk.END, "\n")
    
    def install_missing_dependencies(self):
        """Install missing dependencies"""
        messagebox.showinfo("Install Dependencies", 
                           "This would install missing dependencies.\n\n" +
                           "For now, please use:\n" +
                           "python launcher.py --install [stack_type]")
    
    def launch_stack(self, stack_type):
        """Launch a specific stack"""
        try:
            import subprocess
            import sys
            launcher_script = Path(__file__).parent / "launcher.py"
            subprocess.Popen([sys.executable, str(launcher_script), stack_type])
            messagebox.showinfo("Launch", f"{stack_type.title()} stack launched successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {stack_type} stack: {e}")
    
    def launch_demo(self):
        """Launch demo mode"""
        try:
            import subprocess
            import sys
            launcher_script = Path(__file__).parent / "launcher.py"
            subprocess.Popen([sys.executable, str(launcher_script), "--demo"])
            messagebox.showinfo("Demo", "Demo mode launched successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch demo mode: {e}")
    
    def check_dependencies(self):
        """Check dependencies using parent's method"""
        return self.parent.check_dependencies()
    
    def show(self):
        """Show the status window"""
        self.window.deiconify()


class DiagnosticsWindow:
    """Diagnostics window for system health checks"""
    
    def __init__(self, parent, stack_type):
        self.parent = parent
        self.stack_type = stack_type
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"{stack_type.title()} Stack Diagnostics")
        self.window.geometry("600x400")
        self.window.transient(parent.root)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup diagnostics UI"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text=f"{self.stack_type.title()} Stack Diagnostics", 
                 font=('Arial', 14, 'bold')).pack(pady=(0, 20))
        
        # Results area
        self.results_text = scrolledtext.ScrolledText(main_frame, height=20, font=('Consolas', 9))
        self.results_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Run Diagnostics", command=self.run_diagnostics).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Close", command=self.window.destroy).pack(side=tk.RIGHT)
        
        # Auto-run diagnostics
        self.window.after(500, self.run_diagnostics)
    
    def log(self, message):
        """Log message to diagnostics output"""
        self.results_text.insert(tk.END, f"{message}\n")
        self.results_text.see(tk.END)
        self.window.update_idletasks()
    
    def run_diagnostics(self):
        """Run diagnostic tests"""
        self.results_text.delete(1.0, tk.END)
        self.log(f"Running {self.stack_type} stack diagnostics...\n")
        
        # Check if stack is installed
        if not self.parent.config['installations'][f'{self.stack_type}_stack']['installed']:
            self.log("❌ Stack not installed")
            return
        
        self.log("✅ Stack is installed")
        
        # Check dependencies
        self.log("\nChecking dependencies...")
        if self.parent.check_dependencies(self.stack_type):
            self.log("✅ All dependencies are available")
        else:
            self.log("❌ Some dependencies are missing")
        
        # Check files
        self.log("\nChecking files...")
        if self.stack_type == "control":
            files_to_check = [
                "control/main.py",
                "control/camera_aggregator.py",
                "control/camera_config_gui.py",
                "control/requirements.txt"
            ]
        else:
            files_to_check = [
                "node/server.py",
                "node/requirements.txt"
            ]
        
        base_path = Path(__file__).parent.parent
        for file_path in files_to_check:
            full_path = base_path / file_path
            if full_path.exists():
                self.log(f"✅ {file_path}")
            else:
                self.log(f"❌ {file_path} (missing)")
        
        # Additional checks for node stack
        if self.stack_type == "node":
            self.log("\nChecking system compatibility...")
            if self.parent.is_raspberry_pi():
                self.log("✅ Running on Raspberry Pi")
            else:
                self.log("⚠️  Not running on Raspberry Pi (some features may not work)")
        
        self.log("\nDiagnostics complete.")
    
    def show(self):
        """Show the diagnostics window"""
        self.window.deiconify()


class AboutWindow:
    """About dialog"""
    
    def __init__(self, parent):
        self.parent = parent
        
        self.window = tk.Toplevel(parent.root)
        self.window.title("About")
        self.window.geometry("500x400")
        self.window.transient(parent.root)
        self.window.resizable(False, False)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup about UI"""
        main_frame = ttk.Frame(self.window, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Automated Followspot System", 
                 font=('Arial', 16, 'bold')).pack(pady=(0, 10))
        
        # Version
        version = self.parent.config['system_info']['version']
        ttk.Label(main_frame, text=f"Version {version}", 
                 font=('Arial', 12)).pack(pady=(0, 20))
        
        # Description
        description = """A multi-camera system for tracking IR beacons with automated followspot capabilities.
        
Features:
• Real-time camera streaming via WebRTC
• IR beacon detection and tracking
• Composite video display from multiple cameras
• Demo mode for testing without hardware
• GUI configuration tools
• Node and control stack architecture"""
        
        ttk.Label(main_frame, text=description, justify=tk.LEFT).pack(pady=(0, 20))
        
        # System info
        os_info = self.parent.config['system_info']['os_info']
        ttk.Label(main_frame, text=f"System: {os_info}", 
                 font=('Arial', 9)).pack(pady=(0, 5))
        
        install_path = self.parent.config['system_info']['installation_path']
        ttk.Label(main_frame, text=f"Install Path: {install_path}", 
                 font=('Arial', 9)).pack(pady=(0, 20))
        
        # Close button
        ttk.Button(main_frame, text="Close", command=self.window.destroy).pack()
    
    def show(self):
        """Show the about window"""
        self.window.deiconify()


class SettingsWindow:
    """Settings configuration window"""
    
    def __init__(self, parent):
        self.parent = parent
        
        self.window = tk.Toplevel(parent.root)
        self.window.title("Settings")
        self.window.geometry("400x300")
        self.window.transient(parent.root)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup settings UI"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Settings", font=('Arial', 14, 'bold')).pack(pady=(0, 20))
        
        # Auto dependency check
        self.auto_check_var = tk.BooleanVar(value=self.parent.config['settings']['auto_dependency_check'])
        ttk.Checkbutton(main_frame, text="Automatic dependency checking", 
                       variable=self.auto_check_var).pack(anchor=tk.W, pady=(0, 10))
        
        # Check interval
        ttk.Label(main_frame, text="Dependency check interval (days):").pack(anchor=tk.W)
        self.interval_var = tk.IntVar(value=self.parent.config['settings']['check_interval_days'])
        ttk.Spinbox(main_frame, from_=1, to=30, textvariable=self.interval_var, width=10).pack(anchor=tk.W, pady=(0, 10))
        
        # Debug mode
        self.debug_var = tk.BooleanVar(value=self.parent.config['settings']['debug_mode'])
        ttk.Checkbutton(main_frame, text="Debug mode", 
                       variable=self.debug_var).pack(anchor=tk.W, pady=(0, 20))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="Save", command=self.save_settings).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)
    
    def save_settings(self):
        """Save settings"""
        self.parent.config['settings']['auto_dependency_check'] = self.auto_check_var.get()
        self.parent.config['settings']['check_interval_days'] = self.interval_var.get()
        self.parent.config['settings']['debug_mode'] = self.debug_var.get()
        
        self.parent.save_config()
        self.parent.log_to_terminal("Settings saved")
        self.window.destroy()
    
    def show(self):
        """Show the settings window"""
        self.window.deiconify()


def main():
    """Main entry point"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Automated Followspot System GUI")
    parser.add_argument("--status", action="store_true", help="Show status window only")
    
    args = parser.parse_args()
    
    try:
        if args.status:
            # Launch status window only
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            
            # Create a dummy launcher GUI for config access
            launcher = LauncherGUI()
            
            # Show status window
            status_window = StatusWindow(launcher)
            status_window.show()
            
            root.mainloop()
        else:
            # Launch full GUI
            app = LauncherGUI()
            app.run()
    except Exception as e:
        print(f"Error starting launcher: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

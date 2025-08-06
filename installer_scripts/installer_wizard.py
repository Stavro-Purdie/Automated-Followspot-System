#!/usr/bin/env python3
"""
Step-by-Step Installation Wizard for Automated Followspot System
InstallShield-style wizard with Back/Next navigation
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
import webbrowser

class InstallationWizard:
    """InstallShield-style installation wizard"""
    
    def __init__(self, stack_type=None):
        self.stack_type = stack_type
        self.root = tk.Tk()
        self.root.title("Automated Followspot System - Installation Wizard")
        self.root.geometry("700x500")
        self.root.resizable(False, False)
        
        # Wizard state
        self.current_step = 0
        self.installation_complete = False
        self.installation_successful = False
        self.user_choices = {
            'stack_type': stack_type,
            'install_path': str(Path(__file__).parent.absolute()),
            'create_shortcuts': True,
            'add_to_path': False,
            'auto_start': False
        }
        
        # Setup styles
        self.setup_styles()
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header frame
        self.header_frame = ttk.Frame(self.main_frame)
        self.header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Content frame (will be replaced for each step)
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Navigation frame
        self.nav_frame = ttk.Frame(self.main_frame)
        self.nav_frame.pack(fill=tk.X)
        
        # Setup navigation
        self.setup_navigation()
        
        # Define wizard steps
        self.steps = [
            self.step_welcome,
            self.step_stack_selection,
            self.step_license,
            self.step_installation_options,
            self.step_ready_to_install,
            self.step_installation_progress,
            self.step_completion
        ]
        
        # Start with first step
        self.show_step(0)
    
    def setup_styles(self):
        """Setup custom styles"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Custom styles for wizard
        self.style.configure('Wizard.TLabel', font=('Arial', 10))
        self.style.configure('WizardTitle.TLabel', font=('Arial', 14, 'bold'))
        self.style.configure('WizardSubtitle.TLabel', font=('Arial', 11))
        self.style.configure('WizardButton.TButton', font=('Arial', 10))
    
    def setup_navigation(self):
        """Setup navigation buttons"""
        # Progress indicator
        self.progress_label = ttk.Label(self.nav_frame, text="Step 1 of 7", style='Wizard.TLabel')
        self.progress_label.pack(side=tk.LEFT)
        
        # Buttons
        button_frame = ttk.Frame(self.nav_frame)
        button_frame.pack(side=tk.RIGHT)
        
        self.back_button = ttk.Button(button_frame, text="< Back", 
                                     command=self.go_back, style='WizardButton.TButton')
        self.back_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.next_button = ttk.Button(button_frame, text="Next >", 
                                     command=self.go_next, style='WizardButton.TButton')
        self.next_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.cancel_button = ttk.Button(button_frame, text="Cancel", 
                                       command=self.cancel_installation, style='WizardButton.TButton')
        self.cancel_button.pack(side=tk.LEFT)
    
    def clear_content(self):
        """Clear the content frame"""
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def show_step(self, step_num):
        """Show a specific step"""
        if 0 <= step_num < len(self.steps):
            self.current_step = step_num
            self.update_progress()
            self.clear_content()
            self.steps[step_num]()
            self.update_navigation()
    
    def update_progress(self):
        """Update progress indicator"""
        self.progress_label.config(text=f"Step {self.current_step + 1} of {len(self.steps)}")
    
    def update_navigation(self):
        """Update navigation button states"""
        # Back button
        if self.current_step == 0:
            self.back_button.config(state=tk.DISABLED)
        else:
            self.back_button.config(state=tk.NORMAL)
        
        # Next button
        if self.current_step == len(self.steps) - 1:
            if self.installation_complete:
                self.next_button.config(text="Finish", command=self.finish_installation)
            else:
                self.next_button.config(state=tk.DISABLED)
        elif self.current_step == len(self.steps) - 2:  # Installation step
            self.next_button.config(text="Install", command=self.start_installation)
        else:
            self.next_button.config(text="Next >", command=self.go_next, state=tk.NORMAL)
        
        # Cancel button
        if self.installation_complete:
            self.cancel_button.config(state=tk.DISABLED)
    
    def go_back(self):
        """Go to previous step"""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)
    
    def go_next(self):
        """Go to next step"""
        if self.validate_current_step():
            if self.current_step < len(self.steps) - 1:
                self.show_step(self.current_step + 1)
    
    def validate_current_step(self):
        """Validate current step before proceeding"""
        if self.current_step == 1 and not self.user_choices['stack_type']:
            messagebox.showerror("Selection Required", "Please select a stack type to install.")
            return False
        return True
    
    def cancel_installation(self):
        """Cancel the installation"""
        if messagebox.askyesno("Cancel Installation", 
                              "Are you sure you want to cancel the installation?"):
            self.root.quit()
    
    def finish_installation(self):
        """Finish the installation and close wizard"""
        self.root.quit()
    
    # Wizard Steps
    def step_welcome(self):
        """Welcome step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="Welcome to the Automated Followspot System Setup Wizard",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        # Content
        welcome_text = """This wizard will guide you through the installation of the Automated Followspot System.

The Automated Followspot System is a multi-camera IR beacon tracking solution designed for live performance applications.

Before you begin:
• Ensure you have Python 3.7 or later installed
• Make sure you have an active internet connection for downloading dependencies
• Close any other Python applications that might interfere

Click Next to continue with the installation."""

        text_widget = tk.Text(self.content_frame, wrap=tk.WORD, height=15, width=60,
                             font=('Arial', 10), relief=tk.FLAT, bg=self.root.cget('bg'))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        text_widget.insert(tk.END, welcome_text)
        text_widget.config(state=tk.DISABLED)
    
    def step_stack_selection(self):
        """Stack selection step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="Select Installation Type",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        subtitle_label = ttk.Label(self.header_frame, 
                                  text="Choose which stack you want to install",
                                  style='WizardSubtitle.TLabel')
        subtitle_label.pack()
        
        # Content
        selection_frame = ttk.Frame(self.content_frame)
        selection_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        self.stack_var = tk.StringVar(value=self.user_choices['stack_type'] or "")
        
        # Control Stack option
        control_frame = ttk.LabelFrame(selection_frame, text="Control Stack", padding=15)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Radiobutton(control_frame, text="Install Control Stack", 
                       variable=self.stack_var, value="control",
                       command=self.update_stack_choice).pack(anchor=tk.W)
        
        control_desc = """• Camera management and tracking interface
• Real-time video processing and IR beacon detection
• Multi-camera composite display
• Configuration tools and demo mode
• Suitable for: Main control stations, operator workstations"""
        
        ttk.Label(control_frame, text=control_desc, style='Wizard.TLabel').pack(anchor=tk.W, pady=(5, 0))
        
        # Node Stack option
        node_frame = ttk.LabelFrame(selection_frame, text="Node Stack", padding=15)
        node_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Radiobutton(node_frame, text="Install Node Stack", 
                       variable=self.stack_var, value="node",
                       command=self.update_stack_choice).pack(anchor=tk.W)
        
        node_desc = """• Camera server for video streaming
• WebRTC streaming capabilities
• Raspberry Pi camera support
• Headless operation support
• Suitable for: Camera nodes, Raspberry Pi devices"""
        
        ttk.Label(node_frame, text=node_desc, style='Wizard.TLabel').pack(anchor=tk.W, pady=(5, 0))
        
        # Both option
        both_frame = ttk.LabelFrame(selection_frame, text="Complete Installation", padding=15)
        both_frame.pack(fill=tk.X)
        
        ttk.Radiobutton(both_frame, text="Install Both Stacks", 
                       variable=self.stack_var, value="both",
                       command=self.update_stack_choice).pack(anchor=tk.W)
        
        both_desc = """• Full system installation
• Both control and node capabilities
• Complete development environment
• Suitable for: Single-machine setups, development systems"""
        
        ttk.Label(both_frame, text=both_desc, style='Wizard.TLabel').pack(anchor=tk.W, pady=(5, 0))
    
    def update_stack_choice(self):
        """Update stack choice from radio button"""
        self.user_choices['stack_type'] = self.stack_var.get()
    
    def step_license(self):
        """License agreement step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="License Agreement",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        subtitle_label = ttk.Label(self.header_frame, 
                                  text="Please read the following license agreement",
                                  style='WizardSubtitle.TLabel')
        subtitle_label.pack()
        
        # Content
        license_frame = ttk.Frame(self.content_frame)
        license_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # License text
        license_text = scrolledtext.ScrolledText(license_frame, height=15, width=60,
                                                font=('Consolas', 9))
        license_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Read license from file or use default
        license_content = self.get_license_text()
        license_text.insert(tk.END, license_content)
        license_text.config(state=tk.DISABLED)
        
        # Acceptance checkbox
        self.license_accepted = tk.BooleanVar()
        accept_frame = ttk.Frame(license_frame)
        accept_frame.pack(fill=tk.X)
        
        ttk.Checkbutton(accept_frame, text="I accept the terms of the License Agreement",
                       variable=self.license_accepted,
                       command=self.update_license_acceptance).pack(anchor=tk.W)
        
        # Override next button validation
        self.original_validate = self.validate_current_step
        self.validate_current_step = self.validate_license_step
    
    def get_license_text(self):
        """Get license text"""
        license_file = Path(__file__).parent / "LICENSE"
        if license_file.exists():
            try:
                with open(license_file, 'r') as f:
                    return f.read()
            except:
                pass
        
        return """GNU AFFERO GENERAL PUBLIC LICENSE
Version 3, 19 November 2007

Copyright (C) 2025 Automated Followspot System

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

[This is a summary. The full license text is available in the LICENSE file.]"""
    
    def update_license_acceptance(self):
        """Update license acceptance"""
        if self.license_accepted.get():
            self.next_button.config(state=tk.NORMAL)
        else:
            self.next_button.config(state=tk.DISABLED)
    
    def validate_license_step(self):
        """Validate license acceptance"""
        if not self.license_accepted.get():
            messagebox.showerror("License Agreement", 
                               "You must accept the license agreement to continue.")
            return False
        # Restore original validation for other steps
        self.validate_current_step = self.original_validate
        return True
    
    def step_installation_options(self):
        """Installation options step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="Installation Options",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        subtitle_label = ttk.Label(self.header_frame, 
                                  text="Configure installation settings",
                                  style='WizardSubtitle.TLabel')
        subtitle_label.pack()
        
        # Content
        options_frame = ttk.Frame(self.content_frame)
        options_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Installation path
        path_frame = ttk.LabelFrame(options_frame, text="Installation Directory", padding=10)
        path_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(path_frame, text="Install to:", style='Wizard.TLabel').pack(anchor=tk.W)
        
        path_entry_frame = ttk.Frame(path_frame)
        path_entry_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.path_var = tk.StringVar(value=self.user_choices['install_path'])
        path_entry = ttk.Entry(path_entry_frame, textvariable=self.path_var, width=50)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(path_entry_frame, text="Browse...", 
                  command=self.browse_install_path).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Additional options
        options_label_frame = ttk.LabelFrame(options_frame, text="Additional Options", padding=10)
        options_label_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.shortcuts_var = tk.BooleanVar(value=self.user_choices['create_shortcuts'])
        ttk.Checkbutton(options_label_frame, text="Create desktop shortcuts",
                       variable=self.shortcuts_var).pack(anchor=tk.W, pady=(0, 5))
        
        if self.user_choices['stack_type'] == 'node' or self.user_choices['stack_type'] == 'both':
            self.autostart_var = tk.BooleanVar(value=self.user_choices['auto_start'])
            ttk.Checkbutton(options_label_frame, text="Start node server automatically at boot (Linux/Pi only)",
                           variable=self.autostart_var).pack(anchor=tk.W, pady=(0, 5))
        
        # System requirements
        req_frame = ttk.LabelFrame(options_frame, text="System Requirements", padding=10)
        req_frame.pack(fill=tk.X)
        
        req_text = f"""Installation Type: {self.get_stack_display_name()}
Python Version: {sys.version.split()[0]}
Available Space: {self.get_available_space()}
Internet Connection: Required for dependency download"""
        
        ttk.Label(req_frame, text=req_text, style='Wizard.TLabel').pack(anchor=tk.W)
    
    def browse_install_path(self):
        """Browse for installation path"""
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self.path_var.get())
        if path:
            self.path_var.set(path)
            self.user_choices['install_path'] = path
    
    def get_stack_display_name(self):
        """Get display name for selected stack"""
        stack_map = {
            'control': 'Control Stack',
            'node': 'Node Stack', 
            'both': 'Both Stacks (Complete)'
        }
        return stack_map.get(self.user_choices['stack_type'], 'Unknown')
    
    def get_available_space(self):
        """Get available disk space (simplified)"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.user_choices['install_path'])
            return f"{free // (1024**3)} GB available"
        except:
            return "Unknown"
    
    def step_ready_to_install(self):
        """Ready to install step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="Ready to Install",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        subtitle_label = ttk.Label(self.header_frame, 
                                  text="Review your installation settings",
                                  style='WizardSubtitle.TLabel')
        subtitle_label.pack()
        
        # Content
        summary_frame = ttk.Frame(self.content_frame)
        summary_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        summary_text = f"""The wizard is ready to begin installation.

Installation Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Installation Type: {self.get_stack_display_name()}
Installation Directory: {self.user_choices['install_path']}
Create Shortcuts: {'Yes' if self.user_choices.get('create_shortcuts', False) else 'No'}
"""
        
        if self.user_choices['stack_type'] in ['node', 'both']:
            summary_text += f"Auto-start Node: {'Yes' if self.user_choices.get('auto_start', False) else 'No'}\n"
        
        summary_text += f"""
Components to Install:
"""
        
        if self.user_choices['stack_type'] in ['control', 'both']:
            summary_text += """• Control Stack
  - Camera management interface
  - Real-time video processing
  - Configuration tools
  - Demo mode capabilities
"""
        
        if self.user_choices['stack_type'] in ['node', 'both']:
            summary_text += """• Node Stack
  - Camera server
  - WebRTC streaming
  - Raspberry Pi support
  - Headless operation
"""
        
        summary_text += """
Dependencies will be automatically downloaded and installed.

Click Install to begin the installation process."""
        
        text_widget = tk.Text(summary_frame, wrap=tk.WORD, height=15, width=60,
                             font=('Arial', 10), relief=tk.SUNKEN, bg='white')
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, summary_text)
        text_widget.config(state=tk.DISABLED)
    
    def step_installation_progress(self):
        """Installation progress step"""
        # Header
        header_label = ttk.Label(self.header_frame, 
                                text="Installing Automated Followspot System",
                                style='WizardTitle.TLabel')
        header_label.pack()
        
        self.status_label = ttk.Label(self.header_frame, 
                                     text="Preparing installation...",
                                     style='WizardSubtitle.TLabel')
        self.status_label.pack()
        
        # Content
        progress_frame = ttk.Frame(self.content_frame)
        progress_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 15))
        
        # Installation log
        log_label = ttk.Label(progress_frame, text="Installation Log:", style='Wizard.TLabel')
        log_label.pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=15, width=60,
                                                 font=('Consolas', 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Disable navigation during installation
        self.back_button.config(state=tk.DISABLED)
        self.next_button.config(state=tk.DISABLED)
        self.cancel_button.config(state=tk.DISABLED)
    
    def start_installation(self):
        """Start the installation process"""
        # Update user choices from UI
        self.user_choices['install_path'] = self.path_var.get()
        self.user_choices['create_shortcuts'] = self.shortcuts_var.get()
        if hasattr(self, 'autostart_var'):
            self.user_choices['auto_start'] = self.autostart_var.get()
        
        # Go to installation progress step
        self.show_step(len(self.steps) - 2)  # Installation progress step
        
        # Start installation in background thread
        self.progress_bar.start()
        threading.Thread(target=self.run_installation, daemon=True).start()
    
    def run_installation(self):
        """Run the actual installation process"""
        try:
            self.log("Starting installation...")
            self.update_status("Installing dependencies...")
            
            stacks_to_install = []
            if self.user_choices['stack_type'] == 'both':
                stacks_to_install = ['control', 'node']
            else:
                stacks_to_install = [self.user_choices['stack_type']]
            
            success = True
            for stack in stacks_to_install:
                self.log(f"\n=== Installing {stack.title()} Stack ===")
                self.update_status(f"Installing {stack.title()} Stack...")
                
                if not self.install_stack_dependencies(stack):
                    success = False
                    break
            
            if success:
                self.log("\n=== Updating configuration ===")
                self.update_status("Updating configuration...")
                self.update_launcher_config()
                
                if self.user_choices.get('create_shortcuts'):
                    self.log("Creating shortcuts...")
                    self.update_status("Creating shortcuts...")
                    self.create_shortcuts()
                
                if self.user_choices.get('auto_start') and 'node' in stacks_to_install:
                    self.log("Setting up auto-start...")
                    self.update_status("Setting up auto-start...")
                    self.setup_autostart()
                
                self.log("\n✅ Installation completed successfully!")
                self.installation_successful = True
            else:
                self.log("\n❌ Installation failed!")
                self.installation_successful = False
            
            self.installation_complete = True
            self.root.after(0, self.installation_finished)
            
        except Exception as e:
            self.log(f"\n❌ Installation error: {e}")
            self.installation_successful = False
            self.installation_complete = True
            self.root.after(0, self.installation_finished)
    
    def log(self, message):
        """Add message to installation log"""
        self.root.after(0, lambda: self._log_message(message))
    
    def _log_message(self, message):
        """Internal log message method (runs on main thread)"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_status(self, status):
        """Update status label"""
        self.root.after(0, lambda: self.status_label.config(text=status))
    
    def install_stack_dependencies(self, stack_type):
        """Install dependencies for a specific stack"""
        requirements_file = Path(__file__).parent / stack_type / "requirements.txt"
        
        if not requirements_file.exists():
            self.log(f"❌ Requirements file not found: {requirements_file}")
            return False
        
        self.log(f"📦 Installing {stack_type} dependencies from {requirements_file}")
        
        try:
            # Upgrade pip first
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
            self.log(f"Running: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )
            
            if process.stdout:
                for line in process.stdout:
                    self.log(line.strip())
            
            process.wait()
            
            if process.returncode != 0:
                self.log(f"❌ Failed to upgrade pip (exit code: {process.returncode})")
                return False
            
            # Install requirements
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
            self.log(f"Running: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True
            )
            
            if process.stdout:
                for line in process.stdout:
                    self.log(line.strip())
            
            process.wait()
            
            if process.returncode == 0:
                self.log(f"✅ {stack_type.title()} dependencies installed successfully")
                return True
            else:
                self.log(f"❌ Failed to install {stack_type} dependencies (exit code: {process.returncode})")
                return False
                
        except Exception as e:
            self.log(f"❌ Error installing {stack_type} dependencies: {e}")
            return False
    
    def update_launcher_config(self):
        """Update launcher configuration"""
        try:
            config_file = Path(__file__).parent.parent / "config" / "launcher_config.json"
            
            # Load existing config or create new
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
            else:
                config = {
                    "system_info": {},
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
            
            # Update system info
            import platform
            config["system_info"] = {
                "version": "1.0.0",
                "last_updated": datetime.now().isoformat(),
                "os_info": platform.platform(),
                "installation_path": self.user_choices['install_path']
            }
            
            # Update installation status
            install_date = datetime.now().isoformat()
            stacks_to_update = []
            
            if self.user_choices['stack_type'] == 'both':
                stacks_to_update = ['control_stack', 'node_stack']
            else:
                stacks_to_update = [f"{self.user_choices['stack_type']}_stack"]
            
            for stack in stacks_to_update:
                config["installations"][stack] = {
                    "installed": True,
                    "version": "1.0.0",
                    "install_date": install_date,
                    "dependencies_verified": True,
                    "last_dependency_check": install_date
                }
                
                if stack == "node_stack":
                    config["installations"][stack]["cron_enabled"] = self.user_choices.get('auto_start', False)
            
            # Save config
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.log("✅ Configuration updated successfully")
            
        except Exception as e:
            self.log(f"⚠️  Warning: Could not update configuration: {e}")
    
    def create_shortcuts(self):
        """Create desktop shortcuts"""
        try:
            # This is a simplified implementation
            # In a real application, you'd create proper OS-specific shortcuts
            self.log("✅ Shortcuts would be created here (simplified for demo)")
        except Exception as e:
            self.log(f"⚠️  Warning: Could not create shortcuts: {e}")
    
    def setup_autostart(self):
        """Setup auto-start for node server"""
        try:
            # This is a simplified implementation
            # In a real application, you'd set up actual cron jobs or system services
            self.log("✅ Auto-start would be configured here (simplified for demo)")
        except Exception as e:
            self.log(f"⚠️  Warning: Could not setup auto-start: {e}")
    
    def installation_finished(self):
        """Called when installation is complete"""
        self.progress_bar.stop()
        
        if self.installation_successful:
            self.update_status("Installation completed successfully!")
        else:
            self.update_status("Installation failed!")
        
        # Enable navigation to completion step
        self.next_button.config(state=tk.NORMAL, text="Next >")
        self.cancel_button.config(state=tk.NORMAL)
        
        # Move to completion step
        self.show_step(len(self.steps) - 1)
    
    def step_completion(self):
        """Completion step"""
        # Header
        if self.installation_successful:
            header_label = ttk.Label(self.header_frame, 
                                    text="Installation Complete",
                                    style='WizardTitle.TLabel')
            subtitle_text = "The Automated Followspot System has been successfully installed"
        else:
            header_label = ttk.Label(self.header_frame, 
                                    text="Installation Failed",
                                    style='WizardTitle.TLabel')
            subtitle_text = "The installation encountered errors"
        
        header_label.pack()
        
        subtitle_label = ttk.Label(self.header_frame, 
                                  text=subtitle_text,
                                  style='WizardSubtitle.TLabel')
        subtitle_label.pack()
        
        # Content
        completion_frame = ttk.Frame(self.content_frame)
        completion_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        if self.installation_successful:
            completion_text = f"""✅ Installation completed successfully!

Installed Components:
{self.get_installed_components_text()}

What's Next:
• Launch the application using: python launcher.py
• Configure cameras: python launcher.py --configure  
• Try demo mode: python launcher.py --demo
• Read the documentation: README.md

The Automated Followspot System is now ready to use!"""

            # Add launch button
            button_frame = ttk.Frame(completion_frame)
            button_frame.pack(fill=tk.X, pady=(0, 10))
            
            ttk.Button(button_frame, text="Launch Application Now", 
                      command=self.launch_application,
                      style='WizardButton.TButton').pack(side=tk.LEFT)
            
            ttk.Button(button_frame, text="Open Documentation", 
                      command=self.open_documentation,
                      style='WizardButton.TButton').pack(side=tk.LEFT, padx=(10, 0))
        else:
            completion_text = """❌ Installation failed!

Please check the installation log above for error details.

Troubleshooting:
• Ensure you have a stable internet connection
• Check that you have sufficient permissions
• Verify Python 3.7+ is installed
• Try running the installer as administrator (Windows) or with sudo (Linux/Mac)

For help, visit: https://github.com/Stavro-Purdie/Automated-Followspot-System/issues"""
        
        text_widget = tk.Text(completion_frame, wrap=tk.WORD, height=12, width=60,
                             font=('Arial', 10), relief=tk.FLAT, bg=self.root.cget('bg'))
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert(tk.END, completion_text)
        text_widget.config(state=tk.DISABLED)
    
    def get_installed_components_text(self):
        """Get text describing installed components"""
        components = []
        
        if self.user_choices['stack_type'] in ['control', 'both']:
            components.append("• Control Stack (Camera management and tracking)")
        
        if self.user_choices['stack_type'] in ['node', 'both']:
            components.append("• Node Stack (Camera server and streaming)")
        
        return "\n".join(components)
    
    def launch_application(self):
        """Launch the main application"""
        try:
            launcher_script = Path(__file__).parent / "launcher.py"
            subprocess.Popen([sys.executable, str(launcher_script)])
            self.log("🚀 Launching main application...")
        except Exception as e:
            messagebox.showerror("Launch Error", f"Could not launch application: {e}")
    
    def open_documentation(self):
        """Open documentation"""
        try:
            readme_file = Path(__file__).parent / "README.md"
            if readme_file.exists():
                # Try to open with default application
                import platform
                if platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', str(readme_file)])
                elif platform.system() == 'Windows':
                    subprocess.run(['start', str(readme_file)], shell=True)
                else:  # Linux
                    subprocess.run(['xdg-open', str(readme_file)])
            else:
                webbrowser.open("https://github.com/Stavro-Purdie/Automated-Followspot-System")
        except Exception as e:
            webbrowser.open("https://github.com/Stavro-Purdie/Automated-Followspot-System")
    
    def run(self):
        """Run the installation wizard"""
        # Center the window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.root.winfo_screenheight() // 2) - (500 // 2)
        self.root.geometry(f"700x500+{x}+{y}")
        
        self.root.mainloop()


def main():
    """Main entry point for installation wizard"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Automated Followspot System Installation Wizard")
    parser.add_argument("stack_type", nargs='?', choices=['control', 'node', 'both'],
                       help="Stack type to install")
    
    args = parser.parse_args()
    
    wizard = InstallationWizard(args.stack_type)
    wizard.run()


if __name__ == "__main__":
    main()

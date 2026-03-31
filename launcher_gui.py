#!/usr/bin/env python3
"""
GUI Launcher for Automated Followspot System
This launcher wraps every maintenance task—installing updates, opening the
control suite, logs, into one semi-approachable window.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
import json
import os
import sys
import subprocess
import threading
import time
import platform
from pathlib import Path
from datetime import datetime
import queue
import webbrowser
import shutil
from urllib.parse import urlparse, urlsplit, urlunsplit
from typing import Callable, Dict, Optional, List, Tuple, Any
import urllib.request

from update_manager import UpdateManager, UpdateError, CommitInfo
from node import setup_utils


def ensure_window_fits_content(
    window: tk.Toplevel | tk.Tk,
    *,
    min_width: int = 800,
    min_height: int = 600,
    padding: int = 48,
    center: bool = True,
) -> None:
    """Resize a window so its content fits comfortably without manual resizing."""

    try:
        window.update_idletasks()
    except Exception:
        return

    requested_width = window.winfo_reqwidth() + padding
    requested_height = window.winfo_reqheight() + padding

    width = max(min_width, requested_width)
    height = max(min_height, requested_height)

    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    width = min(width, max(320, screen_width - 80))
    height = min(height, max(240, screen_height - 80))

    if center:
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        geometry = f"{int(width)}x{int(height)}+{int(x)}+{int(y)}"
    else:
        geometry = f"{int(width)}x{int(height)}"

    window.geometry(geometry)
    window.minsize(int(width), int(height))


def set_native_theme(style: ttk.Style) -> None:
    """Set ttk theme to match the operating system.
    
    Args:
        style: ttk.Style instance to configure
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        theme = "aqua"
    elif system == "Windows":
        theme = "vista"  # or 'win10' if available
    else:  # Linux and others
        theme = "clam"
    
    try:
        style.theme_use(theme)
    except tk.TclError:
        # Fall back if theme not available
        try:
            style.theme_use('default')
        except:
            pass


def get_system_appearance() -> str:
    """Detect system appearance (light/dark mode).
    
    Returns:
        'dark' if in dark mode, 'light' otherwise
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0 or "Dark" in result.stdout:
                return "dark"
        except:
            pass
        return "light"
    elif system == "Windows":
        # Windows 10/11 dark mode detection
        try:
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(
                registry,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        except:
            pass
        return "light"
    else:  # Linux
        # Check common environment variables
        theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in theme:
            return "dark"
        return "light"


def get_adaptive_colors() -> Dict[str, str]:
    """Get color scheme that adapts to system appearance.
    
    Returns:
        Dictionary of color names to hex values
    """
    appearance = get_system_appearance()
    
    if appearance == "dark":
        return {
            "bg_primary": "#1e1e1e",      # Dark background
            "bg_secondary": "#2d2d2d",    # Slightly lighter
            "fg_primary": "#e0e0e0",      # Light text
            "fg_secondary": "#b0b0b0",    # Medium text
            "accent_green": "#4ec94e",    # Softer green for dark mode
            "accent_orange": "#ff9500",   # Softer orange
            "accent_red": "#ff5555",      # Softer red
            "border": "#3d3d3d",          # Dark borders
        }
    else:
        return {
            "bg_primary": "#ffffff",      # Light background
            "bg_secondary": "#f5f5f5",    # Slightly darker
            "fg_primary": "#1a1a1a",      # Dark text
            "fg_secondary": "#666666",    # Medium text
            "accent_green": "#00cc00",    # Bright green
            "accent_orange": "#ff9900",   # Bright orange
            "accent_red": "#ff3333",      # Bright red
            "border": "#cccccc",          # Light borders
        }


class LauncherGUI:
    """High-level coordinator for the launcher window and its helper dialogs."""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Automated Followspot System Launcher")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        self.root.configure(bg="SystemButtonFace")
        
        # Use native OS theme
        style = ttk.Style()
        set_native_theme(style)
        
        self.project_root = Path(__file__).resolve().parent
        self.update_check_in_progress = False
        self.update_manager = UpdateManager(
            "Stavro-Purdie", "Automated-Followspot-System", self.project_root
        )
        
        # Initialize configuration
        self.config_file = "launcher_config.json"
        self.config = self.load_config()

        # Terminal output queue for installations
        self.terminal_queue = queue.Queue()
        
        # Animation state for progress indicators
        self.spinner_index = 0
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        
        # Setup GUI
        self.setup_styles()
        self.create_widgets()
        self.build_common_menubar(self.root)
        self.update_ui_state()
        ensure_window_fits_content(self.root, min_width=920, min_height=720, padding=60, center=True)
        self.root.after(2000, lambda: self.check_updates(auto_triggered=True))
        
        # Start periodic checks and animations
        self.root.after(1000, self.periodic_checks)
        self.root.after(100, self.animate_spinners)
    
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
                },
                "front_node_stack": {
                    "installed": False,
                    "version": None,
                    "install_date": None,
                    "dependencies_verified": False,
                    "last_dependency_check": None
                }
            },
            "settings": {
                "auto_dependency_check": True,
                "check_interval_days": 7,
                "allow_concurrent_stacks": False,
                "debug_mode": False
            },
            "update_settings": {
                "release_channel": "stable",
                "auto_check": True,
                "check_interval_hours": 12,
                "auto_update_nodes": True,
                "branches": {
                    "main": {
                        "last_remote": None,
                        "last_prompted": None,
                        "last_applied": None,
                        "last_node_applied": None,
                        "last_checked": None
                    },
                    "testing": {
                        "last_remote": None,
                        "last_prompted": None,
                        "last_applied": None,
                        "last_node_applied": None,
                        "last_checked": None
                    }
                }
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
                        if key == "update_settings":
                            branch_defaults = default_config["update_settings"].get("branches", {})
                            branches = config[key].setdefault("branches", {})
                            for branch_name, state_defaults in branch_defaults.items():
                                branch_state = branches.setdefault(branch_name, {})
                                for state_key, state_value in state_defaults.items():
                                    branch_state.setdefault(state_key, state_value)
                return config
            except Exception as e:
                messagebox.showerror("Configuration Error", f"Failed to load config: {e}")
                return default_config
        else:
            return default_config
    
    def save_config(self):
        """Save launcher configuration"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Failed to save config: {e}")
    
    def setup_styles(self):
        """Setup styles using native OS theme"""
        self.style = ttk.Style()
        # Use native OS theme - aqua on macOS, vista/win10 on Windows, clam on Linux
        # The theme_use will automatically select the system-appropriate theme
        
        # Configure typography with improved hierarchy (OS-native)
        self.style.configure('Title.TLabel', font=('System', 16, 'bold'))
        self.style.configure('Subtitle.TLabel', font=('System', 12, 'bold'))
        self.style.configure('Status.TLabel', font=('System', 10))
        self.style.configure('Primary.TButton', font=('System', 10, 'bold'), padding=8)
        
        # Status indicator colors (subtle, OS-friendly)
        self.style.configure('Success.TLabel', font=('System', 10), foreground='#27ae60')
        self.style.configure('Warning.TLabel', font=('System', 10), foreground='#f39c12')
        self.style.configure('Error.TLabel', font=('System', 10), foreground='#e74c3c')
    
    def create_widgets(self):
        """Create the main GUI widgets"""
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        for col in range(3):
            main_frame.columnconfigure(col, weight=1)

        title_label = ttk.Label(main_frame, text="Automated Followspot System", style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        self.create_status_frame(main_frame)
        self.create_installation_frame(main_frame)
        self.create_control_frame(main_frame)
        self.create_node_frame(main_frame)
        self.create_general_frame(main_frame)
        self.create_terminal_frame(main_frame)

    def build_common_menubar(
        self,
        window,
        *,
        save_command: Optional[Callable[[], None]] = None,
        close_command: Optional[Callable[[], None]] = None,
    ) -> tk.Menu:
        """Attach and return a standard menubar for launcher-related windows."""

        menubar = tk.Menu(window)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings…", command=self.show_settings)
        file_menu.add_command(
            label="Check for Updates",
            command=lambda: self.check_updates(auto_triggered=False),
        )
        if save_command:
            file_menu.add_separator()
            file_menu.add_command(label="Save", command=save_command)

        if close_command is None:
            if window is self.root:
                close_action: Callable[[], None] = self.root.quit
            else:
                close_action = window.destroy  # type: ignore[assignment]
        else:
            close_action = close_command

        file_menu.add_separator()
        file_menu.add_command(
            label="Exit" if window is self.root else "Close",
            command=close_action,
        )
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Roof Array Configuration",
            command=self.launch_configuration,
        )
        tools_menu.add_command(
            label="ReID Configuration",
            command=self.launch_reid_configurator,
        )
        tools_menu.add_command(
            label="Identity Configurator",
            command=self.launch_identity_configurator,
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Beacon Configuration & Monitor",
            command=self.launch_beacon_config,
        )
        tools_menu.add_command(
            label="Beacon Live Monitor",
            command=self.launch_beacon_monitor,
        )
        tools_menu.add_command(
            label="Flash Beacon (Xiao ESP32-C6)",
            command=self.launch_beacon_flasher,
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Connection Status",
            command=self.node_diagnostics,
        )
        tools_menu.add_command(
            label="Open Settings",
            command=self.show_settings,
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="System Status Dashboard",
            command=self.show_status_window,
        )
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Report Issue", command=self.report_bug)
        menubar.add_cascade(label="Help", menu=help_menu)

        window.config(menu=menubar)
        return menubar
    
    def create_status_frame(self, parent):
        """Create system status display with visual indicators"""
        status_frame = ttk.LabelFrame(parent, text="System Status", padding="10")
        status_frame.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 10))

        self.control_status_label = ttk.Label(
            status_frame,
            text="● Control Stack: Not Installed",
            style='Status.TLabel',
        )
        self.control_status_label.grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.node_status_label = ttk.Label(
            status_frame,
            text="● Node Stack: Not Installed",
            style='Status.TLabel',
        )
        self.node_status_label.grid(row=0, column=1, sticky="w", padx=(0, 20))

        self.front_node_status_label = ttk.Label(
            status_frame,
            text="● Front Node (ReID): Not Installed",
            style='Status.TLabel',
        )
        self.front_node_status_label.grid(row=0, column=2, sticky="w", padx=(0, 20))

        self.deps_status_label = ttk.Label(
            status_frame,
            text="⟳ Dependencies: Checking...",
            style='Status.TLabel',
        )
        self.deps_status_label.grid(row=1, column=0, sticky="w", padx=(0, 20))

        self.check_time_label = ttk.Label(status_frame, text="Last Check: Never", style='Status.TLabel')
        self.check_time_label.grid(row=1, column=1, sticky="w")
    
    def create_installation_frame(self, parent):
        """Create installation options (shown when no stacks are installed)"""
        self.install_frame = ttk.LabelFrame(parent, text="Installation Options", padding="10")
        self.install_frame.grid(row=2, column=0, columnspan=3, sticky="we", pady=(0, 10))

        self.install_frame.columnconfigure(0, weight=1)
        self.install_frame.columnconfigure(1, weight=1)
        self.install_frame.columnconfigure(2, weight=1)

        ttk.Button(
            self.install_frame,
            text="Install Control Stack",
            command=self.install_control_stack,
            style='Primary.TButton',
        ).grid(row=0, column=0, padx=(0, 10), sticky="ew")

        ttk.Button(
            self.install_frame,
            text="Install Node Stack",
            command=self.install_node_stack,
            style='Primary.TButton',
        ).grid(row=0, column=1, padx=(0, 10), sticky="ew")

        ttk.Button(
            self.install_frame,
            text="Install Front Node (ReID)",
            command=self.install_front_node_stack,
            style='Primary.TButton',
        ).grid(row=0, column=2, padx=(0, 10), sticky="ew")

        ttk.Label(
            self.install_frame,
            text="Control Stack: Roof array fusion UI and operators' console",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(
            self.install_frame,
            text="Node Stack: Roof camera streaming server",
        ).grid(row=1, column=1, sticky="w", pady=(5, 0))
        ttk.Label(
            self.install_frame,
            text="Front Node: ReID camera streaming server",
        ).grid(row=1, column=2, sticky="w", pady=(5, 0))
    
    def create_control_frame(self, parent):
        """Create control stack options"""
        self.control_frame = ttk.LabelFrame(parent, text="Control Stack", padding="10")
        self.control_frame.grid(row=3, column=0, sticky="nsew", padx=(0, 5))

        ttk.Button(
            self.control_frame,
            text="Roof Array Configuration (IR Beacon Tracking)",
            command=self.launch_configuration,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.control_frame,
            text="Front Array Configuration (ReID Tracking)",
            command=self.launch_reid_configurator,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.control_frame,
            text="Offline Mode",
            command=self.launch_offline_mode,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.control_frame,
            text="Live Mode",
            command=self.launch_live_mode,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 5))

        ttk.Separator(self.control_frame, orient='horizontal').grid(row=4, column=0, sticky="ew", pady=10)

        ttk.Button(
            self.control_frame,
            text="Repair Installation",
            command=self.repair_control,
        ).grid(row=5, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.control_frame,
            text="Uninstall",
            command=self.uninstall_control,
        ).grid(row=6, column=0, sticky="ew")

        self.control_frame.columnconfigure(0, weight=1)
    
    def create_node_frame(self, parent):
        """Create node stack options"""
        self.node_frame = ttk.LabelFrame(parent, text="Camera Servers", padding="10")
        self.node_frame.grid(row=3, column=1, sticky="nsew", padx=(5, 0))
        self.node_frame.columnconfigure(0, weight=1)

        self.roof_frame = ttk.LabelFrame(self.node_frame, text="Roof Node (IR)", padding="10")
        self.roof_frame.grid(row=0, column=0, sticky="ew")
        self.roof_frame.columnconfigure(0, weight=1)

        self.node_running_label = ttk.Label(self.roof_frame, text="Status: Stopped")
        self.node_running_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        ttk.Button(
            self.roof_frame,
            text="Start Node Server",
            command=self.start_node_server,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.roof_frame,
            text="Stop Node Server",
            command=self.stop_node_server,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 5))

        ttk.Separator(self.roof_frame, orient='horizontal').grid(row=3, column=0, sticky="ew", pady=10)

        self.cron_var = tk.BooleanVar()
        self.cron_checkbox = ttk.Checkbutton(
            self.roof_frame,
            text="Start at Boot (Cron)",
            variable=self.cron_var,
            command=self.toggle_cron,
        )
        self.cron_checkbox.grid(row=4, column=0, sticky="w", pady=(0, 5))

        ttk.Button(
            self.roof_frame,
            text="Connection Status",
            command=self.node_diagnostics,
        ).grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        ttk.Button(self.roof_frame, text="Repair Installation", command=self.repair_node).grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        ttk.Button(self.roof_frame, text="Reinstall", command=self.reinstall_node).grid(
            row=7,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        ttk.Button(self.roof_frame, text="Uninstall", command=self.uninstall_node).grid(row=8, column=0, sticky="ew")

        self.front_node_frame = ttk.LabelFrame(self.node_frame, text="Front Node (ReID)", padding="10")
        self.front_node_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.front_node_frame.columnconfigure(0, weight=1)

        self.front_node_status_label = ttk.Label(self.front_node_frame, text="Status: Stopped")
        self.front_node_status_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        ttk.Button(
            self.front_node_frame,
            text="Start Front Node",
            command=self.start_front_node_stack,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.front_node_frame,
            text="Stop Front Node",
            command=self.stop_front_node_stack,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.front_node_frame,
            text="View Front Node Log",
            command=lambda: self.show_log("front_node"),
        ).grid(row=3, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.front_node_frame,
            text="Reinstall Front Node",
            command=lambda: self.run_installer("front_node", reinstall_mode=True),
        ).grid(row=4, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.front_node_frame,
            text="Uninstall Front Node",
            command=self.uninstall_front_node,
        ).grid(row=5, column=0, sticky="ew")

        # Hide frames until stacks are detected as installed
        self.node_frame.grid_remove()
        self.front_node_frame.grid_remove()
    
    def create_general_frame(self, parent):
        """Create general tools and quick links."""
        general_frame = ttk.LabelFrame(parent, text="Tools", padding="10")
        general_frame.grid(row=3, column=2, sticky="nsew", padx=(5, 0))
        general_frame.columnconfigure(0, weight=1)

        identity_frame = ttk.LabelFrame(general_frame, text="Identity Gallery", padding="8")
        identity_frame.grid(row=0, column=0, sticky="ew")
        identity_frame.columnconfigure(0, weight=1)

        ttk.Label(
            identity_frame,
            text="Manage performers and photos in the dedicated configurator.",
            wraplength=260,
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            identity_frame,
            text="Open Identity Configurator",
            command=self.launch_identity_configurator,
            style='Primary.TButton',
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        tools_frame = ttk.LabelFrame(general_frame, text="General Tools", padding="8")
        tools_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tools_frame.columnconfigure(0, weight=1)

        ttk.Button(tools_frame, text="About", command=self.show_about).grid(
            row=0, column=0, sticky="ew", pady=(0, 5)
        )
        ttk.Button(tools_frame, text="Report Bug", command=self.report_bug).grid(
            row=1, column=0, sticky="ew", pady=(0, 5)
        )
        ttk.Button(tools_frame, text="Check Updates", command=self.check_updates).grid(
            row=2, column=0, sticky="ew", pady=(0, 5)
        )
        ttk.Button(tools_frame, text="Settings", command=self.show_settings).grid(
            row=3, column=0, sticky="ew", pady=(0, 5)
        )
        ttk.Button(
            tools_frame,
            text="Flash Beacon (Xiao ESP32-C6)",
            command=self.launch_beacon_flasher,
        ).grid(row=4, column=0, sticky="ew", pady=(0, 5))

        ttk.Separator(tools_frame, orient='horizontal').grid(row=5, column=0, sticky="ew", pady=10)

        ttk.Button(tools_frame, text="Exit", command=self.root.quit).grid(row=6, column=0, sticky="ew")
    
    def create_terminal_frame(self, parent):
        """Create terminal output display"""
        terminal_frame = ttk.LabelFrame(parent, text="Terminal Output", padding="10")
        terminal_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(10, 0))

        self.terminal_text = scrolledtext.ScrolledText(
            terminal_frame,
            height=15,
            width=80,
            font=('Consolas', 9),
            bg='black',
            fg='white',
        )
        self.terminal_text.grid(row=0, column=0, columnspan=2, sticky="nsew")

        ttk.Button(terminal_frame, text="Clear", command=self.clear_terminal).grid(
            row=1, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Button(terminal_frame, text="Save Log", command=self.save_terminal_log).grid(
            row=1, column=1, sticky="e", pady=(5, 0)
        )

        terminal_frame.columnconfigure(0, weight=1)
        terminal_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)
    
    def update_ui_state(self):
        """Update UI state based on current configuration"""
        installations = self.config.get('installations', {})
        control_installed = installations.get('control_stack', {}).get('installed', False)
        node_installed = installations.get('node_stack', {}).get('installed', False)
        front_node_installed = installations.get('front_node_stack', {}).get('installed', False)
        
        # Update status labels
        if control_installed:
            version = self.config['installations']['control_stack'].get('version', 'Unknown')
            self.control_status_label.config(text=f"Control Stack: Installed (v{version})")
        else:
            self.control_status_label.config(text="Control Stack: Not Installed")
        
        if node_installed:
            version = installations.get('node_stack', {}).get('version', 'Unknown')
            self.node_status_label.config(text=f"Node Stack: Installed (v{version})")
        else:
            self.node_status_label.config(text="Node Stack: Not Installed")

        if front_node_installed:
            version = installations.get('front_node_stack', {}).get('version', 'Unknown')
            self.front_node_status_label.config(text=f"Front Node (ReID): Installed (v{version})")
        else:
            self.front_node_status_label.config(text="Front Node (ReID): Not Installed")
        
        # Show/hide appropriate frames
        if not control_installed and not node_installed and not front_node_installed:
            self.install_frame.grid()
            self.control_frame.grid_remove()
            self.node_frame.grid_remove()
            self.front_node_frame.grid_remove()
        else:
            self.install_frame.grid_remove()
            if control_installed:
                self.control_frame.grid()
            else:
                self.control_frame.grid_remove()
            if node_installed or front_node_installed:
                self.node_frame.grid()
            else:
                self.node_frame.grid_remove()

            if node_installed:
                self.roof_frame.grid()
                self.cron_var.set(installations.get('node_stack', {}).get('cron_enabled', False))
                self.node_running_label.config(text="Status: Ready")
            else:
                self.roof_frame.grid_remove()
                self.node_running_label.config(text="Status: Not Installed")

            if front_node_installed:
                self.front_node_frame.grid()
                self.front_node_status_label.config(text="Status: Ready")
            else:
                self.front_node_frame.grid_remove()
                self.front_node_status_label.config(text="Status: Not Installed")
        
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

                # Check front node dependencies
                if self.config['installations'].get('front_node_stack', {}).get('installed'):
                    front_deps = self.check_dependencies('front_node')
                else:
                    front_deps = True
                
                # Update UI
                self.root.after(0, self.update_deps_status, control_deps and node_deps and front_deps)
                
            except Exception as e:
                self.log_to_terminal(f"Error checking dependencies: {e}")
                self.root.after(0, self.update_deps_status, False)
        
        threading.Thread(target=check_deps, daemon=True).start()
    
    def check_dependencies(self, stack_type):
        """Check if dependencies are installed for given stack"""
        try:
            base_path = Path(__file__).parent
            if stack_type == 'control':
                requirements_file = base_path / "control" / "requirements.txt"
            elif stack_type == 'front_node':
                # Front node currently shares dependencies with node stack
                requirements_file = base_path / "node" / "requirements.txt"
            else:
                requirements_file = base_path / "node" / "requirements.txt"
            
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
                        import picamera2  # type: ignore[import]
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
        for stack in ['control_stack', 'node_stack', 'front_node_stack']:
            stack_info = self.config['installations'].get(stack)
            if stack_info and stack_info.get('installed'):
                stack_info['dependencies_verified'] = deps_ok
                stack_info['last_dependency_check'] = now
        
        self.save_config()
    
    def periodic_checks(self):
        """Perform periodic system checks"""
        if self.config['settings']['auto_dependency_check']:
            last_check = None
            for stack in ['control_stack', 'node_stack', 'front_node_stack']:
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

        update_settings = self.config.get("update_settings", {})
        if update_settings.get("auto_check", True) and not self.update_check_in_progress:
            branch = self.update_manager.channel_to_branch(
                update_settings.get("release_channel", "stable")
            )
            branch_state = self._get_branch_state(branch)
            last_checked = self._parse_iso_datetime(branch_state.get("last_checked"))
            interval_hours = max(1, int(update_settings.get("check_interval_hours", 12)))
            if (
                last_checked is None
                or (datetime.now() - last_checked).total_seconds() >= interval_hours * 3600
            ):
                self.check_updates(auto_triggered=True)
        
        # Schedule next check
        self.root.after(60000, self.periodic_checks)  # Check every minute
    
    def animate_spinners(self):
        """Animate progress spinners for visual feedback during operations"""
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        self.root.after(100, self.animate_spinners)
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

    def show_log(self, log_type: str):
        """Display a saved log file in a simple viewer"""
        logs_dir = Path(__file__).parent / "logs"
        log_file = logs_dir / f"{log_type}.log"
        display_name = log_type.replace('_', ' ').title()

        if not log_file.exists():
            messagebox.showinfo("Log Viewer", f"No log file found for {display_name}.")
            return

        viewer = tk.Toplevel(self.root)
        viewer.title(f"{display_name} Log")
        viewer.geometry("700x500")
        self.build_common_menubar(viewer)

        text_widget = scrolledtext.ScrolledText(viewer, wrap=tk.WORD, font=('Consolas', 10))
        text_widget.pack(fill=tk.BOTH, expand=True)
        try:
            text_widget.insert(tk.END, log_file.read_text(encoding="utf-8"))
        except Exception as exc:
            text_widget.insert(tk.END, f"Failed to read log file: {exc}")
        text_widget.config(state=tk.DISABLED)
        ensure_window_fits_content(viewer, min_width=760, min_height=540, padding=48, center=True)
    
    # Installation methods
    def install_control_stack(self):
        """Install control stack with GUI installer"""
        self.run_installer("control")
    
    def install_node_stack(self):
        """Install node stack with GUI installer"""
        self.run_installer("node")

    def install_front_node_stack(self):
        """Install front node stack with GUI installer"""
        self.run_installer("front_node")
    
    def run_installer(self, stack_type, repair_mode=False, reinstall_mode=False):
        """Run installer for specified stack type"""
        installer_window = InstallerWindow(
            self,
            stack_type,
            repair_mode=repair_mode,
            reinstall_mode=reinstall_mode,
        )
        installer_window.show()
    
    # Control stack methods
    def launch_configuration(self):
        """Launch camera configuration GUI"""
        script_path = Path(__file__).parent / "control" / "camera_config_gui.py"
        self.run_script(script_path, "Camera Configuration")
    
    def launch_reid_configurator(self):
        """Launch ReID camera configurator"""
        script_path = Path(__file__).parent / "control" / "reid_configurator.py"
        self.run_script(script_path, "ReID Camera Configurator")
    
    def launch_identity_configurator(self):
        """Launch standalone identity configurator"""
        script_path = Path(__file__).parent / "control" / "identity_configurator.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Identity configurator script not found")
            return
        self.run_script(script_path, "Identity Configurator")
    
    def launch_beacon_config(self):
        """Launch beacon configuration and monitoring tool"""
        script_path = Path(__file__).parent / "control" / "beacon_config_gui.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Beacon config tool not found")
            return
        self.run_script(script_path, "Beacon Configuration & Monitor")

    def launch_beacon_monitor(self):
        """Launch beacon live monitoring dashboard"""
        script_path = Path(__file__).parent / "control" / "beacon_monitor_gui.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Beacon monitor tool not found")
            return
        self.run_script(script_path, "Beacon Live Monitor")

    def launch_beacon_flasher(self):
        """Run the Xiao ESP32-C6 beacon flashing helper."""
        script_path = Path(__file__).parent / "tools" / "beacon_flash.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Beacon flasher script not found")
            return

        ssid = simpledialog.askstring("Beacon Wi-Fi", "Wi-Fi SSID:", parent=self.root)
        if not ssid:
            return
        password = simpledialog.askstring("Beacon Wi-Fi", "Wi-Fi Password:", show="*", parent=self.root)
        if password is None:
            return
        port = simpledialog.askstring(
            "Serial Port",
            "Serial port (e.g., /dev/tty.usbmodemXYZ or COM5):",
            parent=self.root,
        )
        if not port:
            return

        args = ["--ssid", ssid, "--password", password, "--port", port]
        self.run_script(script_path, "Beacon Flasher", args=args)

    def launch_offline_mode(self):
        """Launch control stack in offline/demo mode"""
        script_path = Path(__file__).parent / "control" / "main.py"
        self.run_script(script_path, "Offline Mode", ["--demo"])
    
    def launch_live_mode(self):
        """Launch control stack in live mode"""
        configs_dir = Path(__file__).parent / "config"
        roof_config = configs_dir / "roof_array_config.json"
        front_config = configs_dir / "front_array_config.json"

        if not roof_config.exists():
            if messagebox.askyesno(
                "Roof Configuration Missing",
                "No roof array configuration found. Configure now?",
            ):
                self.launch_configuration()
            return

        if not front_config.exists():
            if messagebox.askyesno(
                "Front Configuration Missing",
                "No front array configuration found. Configure now?",
            ):
                self.launch_reid_configurator()
            return

        script_path = Path(__file__).parent / "control" / "main.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Live control script not found")
            return

        self.log_to_terminal("Opening connection status window before live launch...")
        def start_live_mode() -> None:
            self.run_script(
                script_path,
                "Live Mode",
                args=["--no-dialog", "--config", str(roof_config)],
            )

        self.connection_status_window = ConnectionStatusWindow(
            launcher=self,
            roof_config_path=str(roof_config),
            front_config_path=str(front_config),
            launch_callback=start_live_mode,
        )
    
    def show_connection_status_monitor(self) -> None:
        """Open the connection status window in monitor mode (non-blocking)."""
        configs_dir = Path(__file__).parent / "config"
        roof_config = configs_dir / "roof_array_config.json"
        front_config = configs_dir / "front_array_config.json"

        if not roof_config.exists():
            if messagebox.askyesno(
                "Roof Configuration Missing",
                "No roof array configuration found. Configure now?",
            ):
                self.launch_configuration()
            return

        existing = getattr(self, "connection_status_window", None)
        window_obj = getattr(existing, "window", None)
        if window_obj is not None:
            try:
                if window_obj.winfo_exists():
                    window_obj.lift()
                    return
            except Exception:
                pass

        self.connection_status_window = ConnectionStatusWindow(
            launcher=self,
            roof_config_path=str(roof_config),
            front_config_path=str(front_config),
            launch_callback=None,
            modal=False,
            allow_launch=False,
        )

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
        script_path = Path(__file__).parent / "node" / "server.py"
        self.run_script(script_path, "Node Server", background=True)
    
    def stop_node_server(self):
        """Stop node server"""
        # This would need process management to track and stop the server
        self.log_to_terminal("Stop node server functionality not yet implemented")
    
    def start_front_node_stack(self):
        """Start front (ReID) node server"""
        script_path = Path(__file__).parent / "node" / "server.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Front node server script not found")
            return

        port = 8000
        config_path = Path(__file__).parent / "config" / "front_array_config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            server_url = cfg.get("camera", {}).get("front_camera", {}).get("server_url")
            if server_url:
                parsed = urlparse(server_url)
                if parsed.port:
                    port = parsed.port
        except Exception as exc:
            self.log_to_terminal(f"Using default front node port ({port}) due to config error: {exc}")

        self.front_node_status_label.config(text=f"Status: Starting on port {port}...")
        self.run_script(
            script_path,
            "Front Node Server",
            args=["--port", str(port)],
            background=True,
        )
        self.front_node_status_label.config(text=f"Status: Running on port {port}")

    def stop_front_node_stack(self):
        """Stop front node server"""
        self.log_to_terminal("Stop front node server functionality not yet implemented")
        self.front_node_status_label.config(text="Status: Stop requested")

    def toggle_cron(self):
        """Toggle cron job for node server"""
        enabled = self.cron_var.get()
        self.config['installations']['node_stack']['cron_enabled'] = enabled
        self.save_config()
        
        action = "enabled" if enabled else "disabled"
        self.log_to_terminal(f"Cron job {action} for node server")
        
        # TODO: Implement actual cron job management
    
    def node_diagnostics(self):
        """Open the connection status window without blocking other tools."""
        self.show_connection_status_monitor()
    
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

    def uninstall_front_node(self):
        """Uninstall front node stack"""
        if messagebox.askyesno(
            "Uninstall Front Node",
            "This will remove the front node installation metadata. Continue?",
        ):
            front_cfg = self.config['installations'].setdefault('front_node_stack', {})
            front_cfg['installed'] = False
            front_cfg['version'] = None
            front_cfg['install_date'] = None
            front_cfg['dependencies_verified'] = False
            front_cfg['last_dependency_check'] = None
            self.save_config()
            self.update_ui_state()
            self.front_node_status_label.config(text="Status: Not Installed")
            self.log_to_terminal("Front node stack uninstalled")
    
    # General methods
    def show_about(self):
        """Show about dialog"""
        AboutWindow(self).show()
    
    def show_status_window(self):
        """Open the system status dashboard."""
        StatusWindow(self).show()

    def report_bug(self):
        """Open bug report URL"""
        url = "https://github.com/Stavro-Purdie/Automated-Followspot-System/issues"
        webbrowser.open(url)
        self.log_to_terminal(f"Opened bug report URL: {url}")
    
    def check_updates(self, auto_triggered: bool = False):
        """Check for updates on the configured release channel."""
        if self.update_check_in_progress:
            return

        update_settings = self.config.setdefault("update_settings", {})
        channel = update_settings.get("release_channel", "stable")
        branch = self.update_manager.channel_to_branch(channel)
        branch_state = self._get_branch_state(branch)
        fallback_commit = branch_state.get("last_applied")

        self.update_check_in_progress = True
        self.log_to_terminal(f"Checking for {channel} updates (branch: {branch})...")

        def worker():
            try:
                result = self.update_manager.check_for_update(
                    branch, last_known_commit=fallback_commit
                )
                result["branch"] = branch
            except UpdateError as exc:
                result = {"error": str(exc), "branch": branch}
            except Exception as exc:  # pragma: no cover - defensive
                result = {"error": str(exc), "branch": branch}
            self.root.after(
                0, lambda: self._handle_update_check(result, auto_triggered)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_check(self, result, auto_triggered: bool) -> None:
        self.update_check_in_progress = False

        if result.get("error"):
            error_text = str(result["error"])
            branch = result.get("branch", "")
            if "Release branch" in error_text:
                self._handle_missing_release_branch(branch, error_text, auto_triggered)
                return

            message = f"Update check failed: {error_text}"
            self.log_to_terminal(message)
            if not auto_triggered:
                messagebox.showerror("Update Check Failed", message)
            return

        branch: str = result.get("branch", "")  # type: ignore[assignment]
        latest = result.get("latest")
        branch_state = self._get_branch_state(branch)
        branch_state["last_checked"] = datetime.now().isoformat()
        if isinstance(latest, CommitInfo):
            branch_state["last_remote"] = latest.sha
        self.save_config()

        if not result.get("update_available"):
            self.log_to_terminal("No updates available.")
            if not auto_triggered:
                messagebox.showinfo("Updates", "You are already on the latest version.")
            return

        latest_sha = latest.sha if isinstance(latest, CommitInfo) else ""

        if (
            auto_triggered
            and latest_sha
            and branch_state.get("last_prompted") == latest_sha
            and branch_state.get("last_applied") != latest_sha
        ):
            # Already prompted for this commit during automatic checks
            return

        update_settings = self.config.setdefault("update_settings", {})
        if (
            latest_sha
            and self.config["installations"]["node_stack"].get("installed")
            and update_settings.get("auto_update_nodes", True)
            and branch_state.get("last_node_applied") != latest_sha
        ):
            self._apply_node_update(branch, latest_sha)

        commit_summary = latest_sha[:7] if latest_sha else "unknown"
        commit_date = latest.timestamp if isinstance(latest, CommitInfo) else "unknown"
        prompt_text = (
            f"A new update is available on branch '{branch}'.\n\n"
            f"Latest commit: {commit_summary}\n"
            f"Date: {commit_date}\n\n"
            "Would you like to download and apply it now?"
        )
        apply_update = messagebox.askyesno("Update Available", prompt_text)
        if apply_update and latest_sha:
            self._apply_control_update(branch, latest_sha)
        else:
            branch_state["last_prompted"] = latest_sha
            self.save_config()

    def _apply_control_update(self, branch: str, commit_sha: str) -> None:
        self.log_to_terminal(
            f"Applying control update from {branch} ({commit_sha[:7]})..."
        )

        def worker():
            try:
                info = self.update_manager.apply_update(
                    branch,
                    preserve={"config", "identity_gallery", "logs", "updates", "backups"},
                )
                self.root.after(
                    0,
                    lambda: self._on_control_update_success(branch, commit_sha, info),
                )
            except UpdateError as exc:
                self.root.after(
                    0, lambda: self._on_control_update_failure(str(exc))
                )
            except Exception as exc:  # pragma: no cover - defensive
                self.root.after(
                    0, lambda: self._on_control_update_failure(str(exc))
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_control_update_success(
        self, branch: str, commit_sha: str, info: Dict[str, object]
    ) -> None:
        branch_state = self._get_branch_state(branch)
        branch_state["last_applied"] = commit_sha
        branch_state["last_prompted"] = commit_sha
        self.config.setdefault("system_info", {})["last_updated"] = datetime.now().isoformat()
        self.save_config()

        backup_path = info.get("backup_path", "unknown")
        self.log_to_terminal(
            f"Control update applied successfully (commit {commit_sha[:7]}). Backup: {backup_path}"
        )
        messagebox.showinfo(
            "Update Complete",
            "The control stack has been updated successfully.\n"
            f"Backup created at: {backup_path}",
        )
        self.update_ui_state()

    def _handle_missing_release_branch(
        self, branch: str, error_text: str, auto_triggered: bool
    ) -> None:
        update_cfg = self.config.setdefault("update_settings", {})
        current_channel = update_cfg.get("release_channel", "stable")

        note = (
            "Beta release channel is unavailable; reverting to Stable and retrying."
            if current_channel != "stable"
            else f"Update check failed: {error_text}"
        )

        if current_channel != "stable":
            update_cfg["release_channel"] = "stable"
            self.save_config()
            self.log_to_terminal(
                f"{error_text} Switching back to stable channel and retrying."
            )
            if not auto_triggered:
                messagebox.showinfo(
                    "Update Channel",
                    "Beta updates are unavailable right now. Switched to the Stable channel and will retry.",
                )
            # Retry the update check on the new channel
            self.root.after(500, lambda: self.check_updates(auto_triggered=auto_triggered))
        else:
            self.log_to_terminal(note)
            if not auto_triggered:
                messagebox.showerror("Update Check Failed", note)

    def _on_control_update_failure(self, error_message: str) -> None:
        self.log_to_terminal(f"Control update failed: {error_message}")
        messagebox.showerror("Update Failed", f"Control update failed:\n{error_message}")

    def _apply_node_update(self, branch: str, commit_sha: str) -> None:
        self.log_to_terminal(
            f"Auto-updating node stack from {branch} ({commit_sha[:7]})..."
        )

        def worker():
            try:
                info = self.update_manager.apply_update(
                    branch,
                    components=["node"],
                    preserve={"config", "identity_gallery", "logs", "updates", "backups"},
                )
                self.root.after(
                    0,
                    lambda: self._on_node_update_result(
                        branch, commit_sha, info, error=None
                    ),
                )
            except UpdateError as exc:
                self.root.after(
                    0,
                    lambda: self._on_node_update_result(
                        branch, commit_sha, None, error=str(exc)
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive
                self.root.after(
                    0,
                    lambda: self._on_node_update_result(
                        branch, commit_sha, None, error=str(exc)
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_node_update_result(
        self,
        branch: str,
        commit_sha: str,
        info: Optional[Dict[str, object]],
        error: Optional[str],
    ) -> None:
        if error:
            self.log_to_terminal(f"Node auto-update failed: {error}")
            return

        branch_state = self._get_branch_state(branch)
        branch_state["last_node_applied"] = commit_sha
        self.save_config()

        backup_path = info.get("backup_path") if info else "unknown"
        self.log_to_terminal(
            f"Node stack updated automatically to commit {commit_sha[:7]}. Backup: {backup_path}"
        )

    def _get_branch_state(self, branch: str) -> Dict[str, Optional[str]]:
        update_cfg = self.config.setdefault("update_settings", {})
        branches = update_cfg.setdefault("branches", {})
        state = branches.setdefault(
            branch,
            {
                "last_remote": None,
                "last_prompted": None,
                "last_applied": None,
                "last_node_applied": None,
                "last_checked": None,
            },
        )
        return state

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    
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
                        
                        if process.stdout:
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


class HoverTooltip:
    """Simple tooltip helper that tracks the mouse and shows contextual text."""

    def __init__(self, parent: tk.Toplevel | tk.Tk) -> None:
        self.parent = parent
        self.tipwindow: Optional[tk.Toplevel] = None
        self.current_text: Optional[str] = None

    def show(self, text: str, x: int, y: int) -> None:
        clean_text = (text or "").strip()
        if not clean_text:
            self.hide()
            return

        if len(clean_text) > 280:
            clean_text = clean_text[:277] + "…"

        if self.tipwindow and self.current_text == clean_text:
            self.tipwindow.wm_geometry(f"+{x}+{y}")
            return

        self.hide()

        self.tipwindow = tk.Toplevel(self.parent)
        self.tipwindow.wm_overrideredirect(True)
        try:
            self.tipwindow.wm_attributes("-topmost", True)
        except Exception:
            pass
        self.tipwindow.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(
            self.tipwindow,
            text=clean_text,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            padding=(8, 4),
            justify=tk.LEFT,
            wraplength=360,
        )
        label.pack()
        self.current_text = clean_text

    def hide(self) -> None:
        if self.tipwindow is not None:
            self.tipwindow.destroy()
            self.tipwindow = None
        self.current_text = None


class ConnectionStatusWindow:
    """Modal window that checks camera connectivity before launching live mode."""

    def __init__(
        self,
        launcher: "LauncherGUI",
        roof_config_path: str,
        front_config_path: str,
        launch_callback: Optional[Callable[[], None]] = None,
        *,
        modal: bool = True,
        allow_launch: bool = True,
    ) -> None:
        self.launcher = launcher
        self.roof_config_path = Path(roof_config_path)
        self.front_config_path = Path(front_config_path)
        self.launch_callback = launch_callback
        self.modal = modal
        self.allow_launch = allow_launch

        self.window = tk.Toplevel(self.launcher.root)
        self.window.title("Camera Connection Status")
        self.window.geometry("1000x700")
        self.window.transient(self.launcher.root)
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.override_var = tk.BooleanVar(value=False)
        self.summary_var = tk.StringVar(value="Checking camera connections…")
        self.refresh_interval = 3.0
        self.refresh_event = threading.Event()
        self.status_queue = queue.Queue()
        self.running = True
        self.flash_state = False
        self.tile_width = 180
        self.tile_height = 135
        self.offline_rects: set[int] = set()
        self.tooltip = HoverTooltip(self.window)
        self.start_button: Optional[ttk.Button] = None
        self.override_check: Optional[ttk.Checkbutton] = None

        self.roof_entries: List[Dict[str, Any]] = []
        self.front_entry: Optional[Dict[str, Any]] = None
        self.cameras: List[Dict[str, Any]] = self._load_cameras()

        if not self.cameras:
            messagebox.showinfo(
                "No Cameras Configured",
                "No enabled cameras were found. Live mode will launch without checks.",
            )
            self._cleanup()
            self.window.destroy()
            if self.launch_callback:
                self.launch_callback()
            return

        self._build_ui()
        ensure_window_fits_content(
            self.window,
            min_width=1024 if self.allow_launch else 900,
            min_height=720,
            padding=72,
            center=True,
        )

        if self.modal:
            try:
                self.window.grab_set()
            except Exception:
                pass

        self.worker_thread = threading.Thread(target=self._poll_status_loop, daemon=True)
        self.worker_thread.start()
        self.window.after(150, self._process_queue)
        self.window.after(500, self._toggle_flash)

    def _load_cameras(self) -> List[Dict[str, Any]]:
        cameras: List[Dict[str, Any]] = []
        self.roof_grid_cols = 1
        try:
            with self.roof_config_path.open("r", encoding="utf-8") as handle:
                roof_cfg = json.load(handle)
            grid_cfg = roof_cfg.get("grid_config", {}) if isinstance(roof_cfg, dict) else {}
            per_row = max(1, int(grid_cfg.get("cameras_per_row", 1)))
            auto_arrange = bool(grid_cfg.get("auto_arrange", False))
            assigned_index = 0
            max_col = 0
            max_row = 0

            camera_list = roof_cfg.get("cameras", []) if isinstance(roof_cfg, dict) else []
            for idx, camera in enumerate(camera_list):
                if not isinstance(camera, dict) or not camera.get("enabled", True):
                    continue

                if auto_arrange:
                    col = assigned_index % per_row
                    row = assigned_index // per_row
                else:
                    position = camera.get("position")
                    if not isinstance(position, (list, tuple)) or len(position) != 2:
                        col = assigned_index % per_row
                        row = assigned_index // per_row
                    else:
                        try:
                            col = int(position[0])
                            row = int(position[1])
                        except Exception:
                            col = assigned_index % per_row
                            row = assigned_index // per_row

                max_col = max(max_col, col)
                max_row = max(max_row, row)
                entry_id = str(camera.get("camera_id", f"cam_{idx + 1}"))
                label = str(camera.get("display_name") or entry_id)
                url = str(camera.get("server_url", ""))
                entry = {
                    "id": entry_id,
                    "label": label,
                    "type": "Roof",
                    "url": url,
                    "position": (int(col), int(row)),
                    "status": "checking",
                    "detail": "",
                    "requires_connection": True,
                }
                cameras.append(entry)
                self.roof_entries.append(entry)
                assigned_index += 1

            # Update grid geometry to reflect actual layout
            if self.roof_entries:
                self.roof_grid_cols = max(per_row, max_col + 1)
            else:
                self.roof_grid_cols = per_row
        except Exception as exc:
            messagebox.showerror("Configuration Error", f"Unable to load roof configuration:\n{exc}")
            return []

        if self.roof_entries:
            self.roof_rows = max(entry["position"][1] for entry in self.roof_entries) + 1
        else:
            self.roof_rows = 0

        try:
            with self.front_config_path.open("r", encoding="utf-8") as handle:
                front_cfg = json.load(handle)
            front_cam = (
                front_cfg.get("camera", {}).get("front_camera", {})
                if isinstance(front_cfg, dict)
                else {}
            )
            if front_cam:
                entry_id = str(front_cam.get("camera_id", "front"))
                label = str(front_cam.get("display_name") or "Front ReID")
                url = str(front_cam.get("server_url", ""))
                entry = {
                    "id": entry_id,
                    "label": label,
                    "type": "Front",
                    "url": url,
                    "position": None,
                    "status": "checking",
                    "detail": "",
                    "requires_connection": True,
                }
                self.front_entry = entry
                cameras.append(entry)
        except Exception as exc:
            messagebox.showwarning(
                "Configuration Warning",
                f"Unable to load front camera configuration:\n{exc}",
            )

        return cameras

    def _build_ui(self) -> None:
        header = ttk.Frame(self.window, padding="10")
        header.pack(fill=tk.X)
        ttk.Label(header, text="Camera Connection Status", style="Title.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Label(header, textvariable=self.summary_var).pack(side=tk.RIGHT)

        content = ttk.Frame(self.window, padding="10")
        content.pack(fill=tk.BOTH, expand=True)

        status_frame = ttk.LabelFrame(content, text="Per-Camera Status", padding="10")
        status_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = ("camera", "type", "url", "status")
        self.tree = ttk.Treeview(status_frame, columns=columns, show="headings", height=12)
        for col, label in zip(columns, ["Camera", "Type", "URL", "Status"]):
            self.tree.heading(col, text=label)
            stretch = tk.YES if col != "type" else tk.NO
            width = 220 if col == "url" else 140 if col == "status" else 120
            self.tree.column(col, width=width, stretch=stretch)
        tree_scroll = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", self._on_tree_leave)

        visual_frame = ttk.LabelFrame(content, text="Composite View", padding="10")
        visual_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        cols = max(1, self.roof_grid_cols if self.roof_rows else 1)
        canvas_width = cols * self.tile_width
        canvas_height = max(self.roof_rows * self.tile_height, self.tile_height)
        if self.front_entry:
            canvas_height += self.tile_height + 40

        self.canvas = tk.Canvas(
            visual_frame,
            width=canvas_width,
            height=canvas_height,
            background="#111111",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Leave>", self._on_canvas_leave)

        for entry in self.roof_entries:
            col, row = entry.get("position", (0, 0))
            col = max(0, min(cols - 1, int(col)))
            row = max(0, int(row))
            x1 = col * self.tile_width
            y1 = row * self.tile_height
            x2 = x1 + self.tile_width
            y2 = y1 + self.tile_height
            rect = self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#3a3a3a",
                outline="#0099ff",
                width=2,
            )
            text = self.canvas.create_text(
                x1 + self.tile_width / 2,
                y1 + self.tile_height / 2,
                text=f"{entry['label']}\n⏳ Checking…",
                fill="#00ccff",
                font=("Arial", 11, "bold"),
            )
            entry["canvas_rect"] = int(rect)
            entry["canvas_text"] = int(text)
            for handle in (entry["canvas_rect"], entry["canvas_text"]):
                self.canvas.tag_bind(handle, "<Enter>", lambda e, ent=entry: self._on_canvas_hover(ent, e))
                self.canvas.tag_bind(handle, "<Leave>", self._on_canvas_leave)
                self.canvas.tag_bind(handle, "<Motion>", lambda e, ent=entry: self._on_canvas_hover(ent, e))

        if self.front_entry:
            base_y = self.roof_rows * self.tile_height + 40
            rect = self.canvas.create_rectangle(
                0,
                base_y,
                canvas_width,
                base_y + self.tile_height,
                fill="#2a2a2a",
                outline="#0099ff",
                width=2,
            )
            text = self.canvas.create_text(
                canvas_width / 2,
                base_y + self.tile_height / 2,
                text="Front ReID\n⏳ Checking…",
                fill="#00ccff",
                font=("Arial", 11, "bold"),
            )
            self.front_entry["canvas_rect"] = int(rect)
            self.front_entry["canvas_text"] = int(text)
            for handle in (self.front_entry["canvas_rect"], self.front_entry["canvas_text"]):
                self.canvas.tag_bind(handle, "<Enter>", lambda e, ent=self.front_entry: self._on_canvas_hover(ent, e))
                self.canvas.tag_bind(handle, "<Leave>", self._on_canvas_leave)
                self.canvas.tag_bind(handle, "<Motion>", lambda e, ent=self.front_entry: self._on_canvas_hover(ent, e))

        for entry in self.cameras:
            label = str(entry.get("label", ""))
            entry["label"] = label
            entry["type"] = str(entry.get("type", ""))
            entry["url"] = str(entry.get("url", ""))
            entry_id = str(entry.get("id", label))
            entry["id"] = entry_id
            tree_id = self.tree.insert(
                "",
                tk.END,
                iid=entry_id,
                values=(label, entry["type"], entry["url"], "Checking…"),
            )
            entry["tree_item"] = entry_id

        button_row = ttk.Frame(self.window, padding="10")
        button_row.pack(fill=tk.X)

        if self.allow_launch:
            self.override_check = ttk.Checkbutton(
                button_row,
                text="Override offline cameras",
                variable=self.override_var,
                command=self._update_start_button_state,
            )
            self.override_check.pack(side=tk.LEFT)
            ttk.Button(
                button_row,
                text="Refresh Now",
                command=self._trigger_manual_refresh,
            ).pack(side=tk.LEFT, padx=(10, 0))
        else:
            self.override_check = None
            ttk.Button(
                button_row,
                text="Refresh Now",
                command=self._trigger_manual_refresh,
            ).pack(side=tk.LEFT)

        cancel_label = "Cancel" if self.allow_launch else "Close"
        ttk.Button(button_row, text=cancel_label, command=self._on_cancel).pack(side=tk.RIGHT)

        if self.allow_launch:
            self.start_button = ttk.Button(
                button_row,
                text="Start Live Mode",
                command=self._on_start,
                state=tk.DISABLED,
            )
            self.start_button.pack(side=tk.RIGHT, padx=(0, 10))
        else:
            self.start_button = None

        self._update_summary()
        self._update_start_button_state()

    def _poll_status_loop(self) -> None:
        while self.running:
            results = []
            for entry in self.cameras:
                if not self.running:
                    break
                status, detail = self._check_camera(entry)
                results.append((entry["id"], status, detail))
            if results and self.running:
                self.status_queue.put(("status", results))
            if not self.running:
                break
            self.refresh_event.wait(self.refresh_interval)
            self.refresh_event.clear()

    def _process_queue(self) -> None:
        try:
            while True:
                msg_type, payload = self.status_queue.get_nowait()
                if msg_type == "status":
                    for cam_id, status, detail in payload:  # type: ignore[assignment]
                        self._apply_status(cam_id, status, detail)
        except queue.Empty:
            pass
        if self.running:
            self.window.after(150, self._process_queue)

    def _toggle_flash(self) -> None:
        if not self.running:
            return
        self.flash_state = not self.flash_state
        # More dramatic error state with alternating bright red and dark red
        if self.flash_state:
            color = "#ff2020"  # Bright alert red
            outline = "#ffff00"  # Yellow border for extra contrast
            width = 4  # Thicker border
        else:
            color = "#800000"  # Dark maroon
            outline = "#ff6666"  # Lighter red-pink border
            width = 2
        
        for rect_id in list(self.offline_rects):
            self.canvas.itemconfig(rect_id, fill=color, outline=outline, width=width)
        self.window.after(400, self._toggle_flash)

    def _on_tree_motion(self, event: Any) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.tooltip.hide()
            return
        entry = next((c for c in self.cameras if c["id"] == iid), None)
        if not entry:
            self.tooltip.hide()
            return
        detail = str(entry.get("detail", "")).strip()
        if entry.get("status") != "online" and detail:
            self.tooltip.show(detail, event.x_root + 12, event.y_root + 12)
        else:
            self.tooltip.hide()

    def _on_tree_leave(self, _event: Any) -> None:
        self.tooltip.hide()

    def _on_canvas_hover(self, entry: Dict[str, Any], event: Any) -> None:
        detail = str(entry.get("detail", "")).strip()
        if entry.get("status") != "online" and detail:
            self.tooltip.show(detail, event.x_root + 12, event.y_root + 12)
        else:
            self.tooltip.hide()

    def _on_canvas_leave(self, _event: Any) -> None:
        self.tooltip.hide()

    def _apply_status(self, cam_id: str, status: str, detail: str) -> None:
        entry = next((c for c in self.cameras if c["id"] == cam_id), None)
        if not entry:
            return
        entry["status"] = status
        entry["detail"] = detail or ""

        display = status.capitalize()

        label = str(entry.get("label", ""))
        entry_type = str(entry.get("type", ""))
        url = str(entry.get("url", ""))
        tree_id = entry.get("tree_item")
        if isinstance(tree_id, str):
            self.tree.item(tree_id, values=(label, entry_type, url, display))

        text_id = entry.get("canvas_text")
        if isinstance(text_id, int):
            lines = [label, status.upper()]
            # Add error indicator symbol for offline cameras
            if status != "online":
                lines[1] = f"❌ {lines[1]}"
            self.canvas.itemconfig(text_id, text="\n".join(lines))
            # Make offline text more prominent with red color
            if status == "online":
                text_color = "#00ff00"  # Bright green for online
            else:
                text_color = "#ffff00"  # Bright yellow for errors (for visibility over red)

        rect_handle = entry.get("canvas_rect")
        if isinstance(rect_handle, int):
            if status == "online":
                self.canvas.itemconfig(rect_handle, fill="#1b5e20", outline="#0f3d14", width=2)
                self.offline_rects.discard(rect_handle)
            else:
                self.offline_rects.add(rect_handle)
                # Initial state: bright red
                color = "#ff2020" if self.flash_state else "#800000"
                outline = "#ffff00" if self.flash_state else "#ff6666"
                width = 4 if self.flash_state else 2
                self.canvas.itemconfig(rect_handle, fill=color, outline=outline, width=width)

        self._update_summary()
        self._update_start_button_state()

    def _check_camera(self, entry: Dict[str, object]) -> Tuple[str, str]:
        raw_url = str(entry.get("url") or "")
        if not raw_url:
            return "offline", "No URL configured"

        parsed = urlsplit(raw_url)
        if not parsed.scheme:
            parsed = urlsplit(f"http://{raw_url}")

        if parsed.scheme not in ("http", "https"):
            return "offline", f"Unsupported protocol: {parsed.scheme}"

        normalized = self._normalize_url(parsed)
        if not normalized:
            return "offline", "Invalid URL"

        request = urllib.request.Request(normalized, method="GET")
        start = time.time()
        try:
            with urllib.request.urlopen(request, timeout=3.0) as response:
                latency_ms = (time.time() - start) * 1000.0
                if 200 <= response.status < 500:
                    return "online", f"{latency_ms:.0f} ms"
                return "offline", f"HTTP {response.status}"
        except Exception as exc:
            message = str(exc).split("\n")[0]
            if len(message) > 40:
                message = message[:40] + "…"
            return "offline", message

    @staticmethod
    def _normalize_url(parsed) -> Optional[str]:
        if not parsed.netloc:
            return None
        path = parsed.path or "/"
        if path.endswith("/offer"):
            path = path[: -len("/offer")] or "/"
        return urlunsplit((parsed.scheme, parsed.netloc, path or "/", "", ""))

    def _trigger_manual_refresh(self) -> None:
        self.refresh_event.set()

    def _update_summary(self) -> None:
        total = len(self.cameras)
        online = sum(1 for entry in self.cameras if entry.get("status") == "online")
        self.summary_var.set(f"{online}/{total} cameras online")

    def _update_start_button_state(self) -> None:
        if not self.allow_launch or self.start_button is None:
            return
        all_online = all(
            entry.get("status") == "online"
            for entry in self.cameras
            if entry.get("requires_connection", True)
        )
        if all_online or self.override_var.get():
            self.start_button.config(state=tk.NORMAL)
        else:
            self.start_button.config(state=tk.DISABLED)

    def _cleanup(self) -> None:
        self.running = False
        self.refresh_event.set()
        self.tooltip.hide()
        try:
            self.window.grab_release()
        except Exception:
            pass
        try:
            if getattr(self.launcher, "connection_status_window", None) is self:
                setattr(self.launcher, "connection_status_window", None)
        except Exception:
            pass

    def _on_cancel(self) -> None:
        self._cleanup()
        self.window.destroy()

    def _on_start(self) -> None:
        if not self.allow_launch:
            self._cleanup()
            self.window.destroy()
            return

        offline = [entry for entry in self.cameras if entry.get("status") != "online"]
        if offline and not self.override_var.get():
            messagebox.showwarning(
                "Connections Pending", "Some cameras are still offline. Enable override to continue."
            )
            return

        if offline and self.override_var.get():
            names = ", ".join(str(entry.get("label", "")) for entry in offline)
            proceed = messagebox.askyesno(
                "Override Offline Cameras",
                f"The following cameras are offline: {names}\nLaunch live mode anyway?",
            )
            if not proceed:
                return

        self.launcher.log_to_terminal("Launching live mode…")
        self._cleanup()
        self.window.destroy()
        if self.launch_callback:
            self.launch_callback()

class InstallerWindow:
    """GUI installer window for control or node stack"""
    
    def __init__(self, parent, stack_type, repair_mode=False, reinstall_mode=False):
        self.parent = parent
        self.stack_type = stack_type
        self.repair_mode = repair_mode
        self.reinstall_mode = reinstall_mode
        self.stack_display = stack_type.replace('_', ' ').title()
        self.node_setup_data = None  # type: Optional[Dict[str, Any]]
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"Install {self.stack_display} Stack")
        self.window.geometry("700x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        menubar = self.parent.build_common_menubar(
            self.window,
            close_command=self.close_window,
        )
        actions_menu = tk.Menu(menubar, tearoff=0)
        actions_menu.add_command(label="Start Installation", command=self.start_installation)
        menubar.add_cascade(label="Actions", menu=actions_menu)
        
        self.setup_installer_ui()
        ensure_window_fits_content(self.window, min_width=780, min_height=560, padding=64, center=True)
    
    def setup_installer_ui(self):
        """Setup installer UI"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        action = "Repair" if self.repair_mode else "Reinstall" if self.reinstall_mode else "Install"
        title = f"{action} {self.stack_display} Stack"
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
        if self.stack_type in {"node", "front_node"} and self.node_setup_data is None:
            stack_key = f"{self.stack_type}_stack"
            defaults = self.parent.config.get("installations", {}).get(stack_key, {}).get("node_setup", {})
            dialog = NodeSetupDialog(self.parent.root, self.stack_type, defaults)
            data = dialog.show()
            if data is None:
                self.install_button.config(state=tk.NORMAL)
                return
            self.node_setup_data = data

        self.install_button.config(state=tk.DISABLED)
        self.progress.start()
        
        def install_process():
            try:
                stack_key = f"{self.stack_type}_stack"
                self.window.after(0, lambda: self.status_label.config(text="Installing dependencies..."))
                
                # Install dependencies
                if self.stack_type == "control":
                    requirements_file = Path(__file__).parent / "control" / "requirements.txt"
                elif self.stack_type == "front_node":
                    requirements_file = Path(__file__).parent / "node" / "requirements.txt"
                else:
                    requirements_file = Path(__file__).parent / "node" / "requirements.txt"
                
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
                    
                    if process.stdout:
                        for line in process.stdout:
                            self.window.after(0, self.log, line.strip())
                    
                    process.wait()
                    
                    if process.returncode == 0:
                        self.window.after(0, self.log, "Dependencies installed successfully")
                    else:
                        self.window.after(0, self.log, f"Dependency installation failed with code {process.returncode}")
                        self.window.after(0, self.installation_failed)
                        return

                # Ensure SSL certificates are available for update checks
                self.window.after(0, self.log, "Ensuring SSL certificate bundle (certifi) is installed...")
                certifi_cmd = [sys.executable, "-m", "pip", "install", "certifi"]
                certifi_process = subprocess.Popen(
                    certifi_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    universal_newlines=True,
                )

                if certifi_process.stdout:
                    for line in certifi_process.stdout:
                        self.window.after(0, self.log, line.strip())

                certifi_process.wait()

                if certifi_process.returncode == 0:
                    self.window.after(0, self.log, "Certificate bundle verified.")
                else:
                    self.window.after(0, self.log, "Warning: Unable to install certifi automatically. SSL-secured features may fail.")
                
                # Mark as installed
                self.window.after(0, lambda: self.status_label.config(text="Finalizing installation..."))
                
                install_date = datetime.now().isoformat()
                install_entry = self.parent.config.setdefault('installations', {}).setdefault(stack_key, {})
                install_entry['installed'] = True
                install_entry['version'] = "1.0.0"
                install_entry['install_date'] = install_date
                install_entry['dependencies_verified'] = True
                install_entry['last_dependency_check'] = install_date

                if self.stack_type in {"node", "front_node"} and self.node_setup_data:
                    setup_data = dict(self.node_setup_data)
                    profile = "front_truss" if self.stack_type == "front_node" else "roof_array"
                    setup_data["profile"] = profile
                    setup_data["configured_at"] = install_date
                    setup_summary = setup_utils.finalize_node_setup(
                        stack_slug="front-node" if self.stack_type == "front_node" else "node",
                        project_root=Path(__file__).parent,
                        python_exec=sys.executable,
                        setup=setup_data,
                    )
                    install_entry['node_setup'] = setup_data
                    install_entry['autostart'] = setup_summary
                    service_info = setup_summary.get("service", {})
                    if service_info.get("enabled"):
                        self.window.after(0, self.log, f"Autostart enabled ({service_info.get('service_name')})")
                    elif service_info.get("enable_error"):
                        self.window.after(0, self.log, f"Autostart enable error: {service_info['enable_error']}")
                    hostname_info = setup_summary.get("hostname", {})
                    if hostname_info.get("requested") and not hostname_info.get("applied"):
                        message = hostname_info.get("message") or "Hostname change requires sudo"
                        self.window.after(0, self.log, f"Hostname update not applied: {message}")
                    notes = setup_summary.get("static_ip_notes", {}).get("notes_file")
                    if notes:
                        self.window.after(0, self.log, f"Static IP guidance saved to {notes}")
                
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


class NodeSetupDialog:
    """Modal dialog to gather node network and hardware settings."""

    def __init__(self, parent: tk.Tk, stack_type: str, defaults: Optional[Dict[str, Any]] = None):
        self.parent = parent
        self.stack_type = stack_type
        self.defaults = defaults or {}
        self.result: Optional[Dict[str, Any]] = None

        self.window = tk.Toplevel(parent)
        self.window.title("Node Setup Configuration")
        self.window.transient(parent)
        self.window.grab_set()

        profile_defaults = {
            "node": {"camera_device": "imx219", "port": 8080},
            "front_node": {"camera_device": "imx477", "port": 8000},
        }
        prof = profile_defaults.get(stack_type, {"camera_device": "", "port": 8080})

        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Static IP (leave blank to skip)").grid(row=0, column=0, sticky="w")
        self.static_ip_var = tk.StringVar(value=self.defaults.get("static_ip", ""))
        ttk.Entry(frame, textvariable=self.static_ip_var, width=30).grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, text="Hostname (leave blank to skip)").grid(row=1, column=0, sticky="w")
        self.hostname_var = tk.StringVar(value=self.defaults.get("hostname", ""))
        ttk.Entry(frame, textvariable=self.hostname_var, width=30).grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Camera Device").grid(row=2, column=0, sticky="w")
        default_camera = self.defaults.get("camera_device") or prof.get("camera_device", "")
        self.camera_var = tk.StringVar(value=default_camera)
        ttk.Entry(frame, textvariable=self.camera_var, width=30).grid(row=2, column=1, sticky="ew")

        ttk.Label(frame, text="Network Interface").grid(row=3, column=0, sticky="w")
        self.interface_var = tk.StringVar(value=self.defaults.get("interface", "eth0"))
        ttk.Entry(frame, textvariable=self.interface_var, width=20).grid(row=3, column=1, sticky="ew")

        ttk.Label(frame, text="Default Gateway").grid(row=4, column=0, sticky="w")
        self.gateway_var = tk.StringVar(value=self.defaults.get("gateway", ""))
        ttk.Entry(frame, textvariable=self.gateway_var, width=30).grid(row=4, column=1, sticky="ew")

        ttk.Label(frame, text="DNS Servers (space separated)").grid(row=5, column=0, sticky="w")
        self.dns_var = tk.StringVar(value=self.defaults.get("dns", ""))
        ttk.Entry(frame, textvariable=self.dns_var, width=30).grid(row=5, column=1, sticky="ew")

        ttk.Label(frame, text="Service Port").grid(row=6, column=0, sticky="w")
        port_default = self.defaults.get("port") or prof.get("port", 8080)
        try:
            self.port_default = int(port_default)
        except (TypeError, ValueError):
            self.port_default = 8080
        self.port_var = tk.StringVar(value=str(self.port_default))
        ttk.Entry(frame, textvariable=self.port_var, width=10).grid(row=6, column=1, sticky="w")

        frame.columnconfigure(1, weight=1)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=7, column=0, columnspan=2, pady=(20, 0), sticky="e")

        ttk.Button(button_frame, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="Save", command=self.on_save).pack(side=tk.RIGHT)

        ensure_window_fits_content(self.window, min_width=500, min_height=320, padding=40, center=True)

    def on_save(self):
        port_text = self.port_var.get().strip()
        try:
            port_value = int(port_text) if port_text else self.port_default
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid numeric port.")
            return

        self.result = {
            "static_ip": self.static_ip_var.get().strip() or None,
            "hostname": self.hostname_var.get().strip() or None,
            "camera_device": self.camera_var.get().strip() or None,
            "interface": self.interface_var.get().strip() or "eth0",
            "gateway": self.gateway_var.get().strip() or None,
            "dns": self.dns_var.get().strip() or None,
            "port": port_value,
        }
        self.window.destroy()

    def on_cancel(self):
        self.result = None
        self.window.destroy()

    def show(self) -> Optional[Dict[str, Any]]:
        self.window.wait_window()
        return self.result


class StatusWindow:
    """GUI Status window for system status display"""
    
    def __init__(self, parent):
        self.parent = parent
        
        self.window = tk.Toplevel()
        self.window.title("System Status - Automated Followspot System")
        self.window.resizable(True, True)
        self.parent.build_common_menubar(self.window)
        
        self.setup_ui()
        ensure_window_fits_content(self.window, min_width=920, min_height=720, padding=64, center=True)
    
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
        installations = config.get("installations", {})
        control_installed = installations.get("control_stack", {}).get("installed", False)
        node_installed = installations.get("node_stack", {}).get("installed", False)
        front_installed = installations.get("front_node_stack", {}).get("installed", False)
        
        if control_installed or node_installed or front_installed:
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
            install_date = installations.get("control_stack", {}).get("install_date")
            if install_date:
                ttk.Label(install_frame, text=f"   Installed: {install_date[:10]}", 
                         font=('Arial', 9), foreground="gray").pack(anchor=tk.W)
        else:
            ttk.Label(install_frame, text="❌ Control Stack: Not Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
        
        if node_installed:
            ttk.Label(install_frame, text="✅ Node Stack: Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
            install_date = installations.get("node_stack", {}).get("install_date")
            if install_date:
                ttk.Label(install_frame, text=f"   Installed: {install_date[:10]}", 
                         font=('Arial', 9), foreground="gray").pack(anchor=tk.W)
        else:
            ttk.Label(install_frame, text="❌ Node Stack: Not Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)

        if front_installed:
            ttk.Label(install_frame, text="✅ Front Node (ReID): Installed", 
                     font=('Arial', 10)).pack(anchor=tk.W)
            install_date = installations.get("front_node_stack", {}).get("install_date")
            if install_date:
                ttk.Label(install_frame, text=f"   Installed: {install_date[:10]}", 
                         font=('Arial', 9), foreground="gray").pack(anchor=tk.W)
        else:
            ttk.Label(install_frame, text="❌ Front Node (ReID): Not Installed", 
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
        if front_installed:
            ttk.Button(
                action_buttons_frame,
                text="Front Node Log",
                command=lambda: self.parent.show_log("front_node"),
            ).pack(side=tk.LEFT, padx=(0, 10))
        
        if not (control_installed or node_installed or front_installed):
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
            display_name = stack_type.replace('_', ' ').title()
            messagebox.showinfo("Launch", f"{display_name} stack launched successfully!")
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
        self.stack_display = stack_type.replace('_', ' ').title()
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"{self.stack_display} Stack Diagnostics")
        self.window.geometry("600x400")
        self.window.transient(parent.root)
        menubar = self.parent.build_common_menubar(
            self.window,
            close_command=self.window.destroy,
        )
        diagnostics_menu = tk.Menu(menubar, tearoff=0)
        diagnostics_menu.add_command(label="Run Diagnostics", command=self.run_diagnostics)
        menubar.add_cascade(label="Diagnostics", menu=diagnostics_menu)
        
        self.setup_ui()
        ensure_window_fits_content(self.window, min_width=780, min_height=560, padding=64, center=True)
    
    def setup_ui(self):
        """Setup diagnostics UI"""
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(
            main_frame,
            text=f"{self.stack_display} Stack Diagnostics",
            font=('Arial', 14, 'bold'),
        ).pack(pady=(0, 20))
        
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
        self.log(f"Running {self.stack_display} stack diagnostics...\n")
        
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
        
        base_path = Path(__file__).parent
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
        self.parent.build_common_menubar(self.window)
        
        self.setup_ui()
        ensure_window_fits_content(self.window, min_width=560, min_height=460, padding=48, center=True)
    
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
        self.window.geometry("760x860")
        self.window.minsize(720, 820)
        self.parent.build_common_menubar(
            self.window,
            save_command=self.save_settings,
            close_command=self.window.destroy,
        )
        self.window.transient(parent.root)
        self.project_root = Path(__file__).resolve().parent
        self.reid_config_path = self.project_root / "config" / "reid_config.json"
        self.reid_config = self.load_reid_config()
        self.coreml_unit_choices = [
            ("Automatic (CPU + GPU + ANE)", "ALL"),
            ("Neural Engine (ANE)", "CPU_AND_NE"),
            ("GPU (Metal)", "CPU_AND_GPU"),
            ("CPU Only", "CPU_ONLY"),
        ]
        self.channel_options = [
            ("Stable (Main Branch)", "stable"),
            ("Beta (Testing Branch)", "beta"),
        ]
        
        self.setup_ui()
        ensure_window_fits_content(self.window, min_width=820, min_height=880, padding=72, center=True)
    
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

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=(10, 15))

        accel_frame = ttk.LabelFrame(main_frame, text="ReID Acceleration (Apple Silicon)", padding="12")
        accel_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        accel_frame.columnconfigure(1, weight=1)

        optimization_cfg = self.reid_config.setdefault("optimization", {})

        self.coreml_enabled_var = tk.BooleanVar(value=bool(optimization_cfg.get("coreml_reid_enabled", False)))
        ttk.Checkbutton(
            accel_frame,
            text="Enable Core ML ReID (Neural Engine)",
            variable=self.coreml_enabled_var
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(accel_frame, text="Core ML model (.mlpackage):").grid(row=1, column=0, sticky="w")
        self.coreml_path_var = tk.StringVar(value=str(optimization_cfg.get("coreml_model_path", "")))
        path_entry = ttk.Entry(accel_frame, textvariable=self.coreml_path_var, width=40)
        path_entry.grid(row=2, column=0, columnspan=2, sticky="we", pady=(0, 5))
        ttk.Button(accel_frame, text="Browse", command=self.browse_coreml_model).grid(row=3, column=0, sticky="w")

        ttk.Label(accel_frame, text="Accelerator preference:").grid(row=4, column=0, sticky="w", pady=(10, 0))
        current_unit_value = str(optimization_cfg.get("coreml_compute_unit", "ALL"))
        default_unit_label = self._unit_value_to_label(current_unit_value)
        self.coreml_unit_var = tk.StringVar(value=default_unit_label)
        ttk.Combobox(
            accel_frame,
            textvariable=self.coreml_unit_var,
            values=[label for label, _ in self.coreml_unit_choices],
            state="readonly"
        ).grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 10))

        self.skip_torch_var = tk.BooleanVar(value=bool(optimization_cfg.get("coreml_skip_torch", True)))
        ttk.Checkbutton(
            accel_frame,
            text="Skip Torch ReID when Core ML is enabled",
            variable=self.skip_torch_var
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.half_precision_var = tk.BooleanVar(value=bool(optimization_cfg.get("use_half_precision", False)))
        ttk.Checkbutton(
            accel_frame,
            text="Use half precision (FP16) on CUDA GPUs",
            variable=self.half_precision_var
        ).grid(row=7, column=0, columnspan=2, sticky="w")

        ttk.Label(
            accel_frame,
            text="Core ML acceleration requires a converted ReID model. Choose whether to favour\nNeural Engine, GPU, CPU, or let Core ML use everything available.",
            wraplength=420,
            foreground="#555555"
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=(10, 15))

        update_cfg = self.parent.config.setdefault("update_settings", {})
        updates_frame = ttk.LabelFrame(main_frame, text="Update Settings", padding="12")
        updates_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        updates_frame.columnconfigure(1, weight=1)

        self.release_channel_var = tk.StringVar(
            value=self._channel_value_to_display(update_cfg.get("release_channel", "stable"))
        )
        ttk.Label(updates_frame, text="Release channel:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            updates_frame,
            textvariable=self.release_channel_var,
            values=[label for label, _ in self.channel_options],
            state="readonly",
        ).grid(row=0, column=1, sticky="we", pady=(0, 5))

        self.update_auto_check_var = tk.BooleanVar(value=update_cfg.get("auto_check", True))
        ttk.Checkbutton(
            updates_frame,
            text="Automatically check for updates",
            variable=self.update_auto_check_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 5))

        ttk.Label(updates_frame, text="Update check interval (hours):").grid(row=2, column=0, sticky="w")
        self.update_interval_var = tk.IntVar(value=int(update_cfg.get("check_interval_hours", 12)))
        ttk.Spinbox(
            updates_frame,
            from_=1,
            to=168,
            textvariable=self.update_interval_var,
            width=10,
        ).grid(row=2, column=1, sticky="w")

        self.auto_update_nodes_var = tk.BooleanVar(value=update_cfg.get("auto_update_nodes", True))
        ttk.Checkbutton(
            updates_frame,
            text="Automatically update node stacks when new builds are detected",
            variable=self.auto_update_nodes_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        
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

        update_cfg = self.parent.config.setdefault("update_settings", {})
        update_cfg["release_channel"] = self._channel_display_to_value(self.release_channel_var.get())
        update_cfg["auto_check"] = self.update_auto_check_var.get()
        update_cfg["check_interval_hours"] = max(1, int(self.update_interval_var.get()))
        update_cfg["auto_update_nodes"] = self.auto_update_nodes_var.get()

        optimization_cfg = self.reid_config.setdefault("optimization", {})
        coreml_enabled = self.coreml_enabled_var.get()
        coreml_path = self.coreml_path_var.get().strip()

        if coreml_enabled and not coreml_path:
            messagebox.showerror(
                "Settings",
                "Please specify a Core ML model path (.mlpackage) or disable Core ML ReID."
            )
            return

        if coreml_path:
            path_obj = Path(coreml_path)
            if not path_obj.is_absolute():
                # allow relative paths as-is
                normalized_path = str(path_obj)
            else:
                try:
                    normalized_path = str(path_obj.relative_to(self.project_root))
                except ValueError:
                    normalized_path = str(path_obj)
            optimization_cfg["coreml_model_path"] = normalized_path
        else:
            optimization_cfg["coreml_model_path"] = ""

        optimization_cfg["coreml_reid_enabled"] = coreml_enabled
        optimization_cfg["coreml_compute_unit"] = self._unit_label_to_value(self.coreml_unit_var.get())
        optimization_cfg["coreml_skip_torch"] = self.skip_torch_var.get()
        optimization_cfg["use_half_precision"] = self.half_precision_var.get()
        
        if not self.save_reid_config():
            return

        self.parent.save_config()
        self.parent.log_to_terminal("Settings saved")
        self.window.destroy()
    
    def show(self):
        """Show the settings window"""
        self.window.deiconify()

    def _unit_label_to_value(self, label: str) -> str:
        for display, value in self.coreml_unit_choices:
            if display == label:
                return value
        return self.coreml_unit_choices[0][1]

    def _unit_value_to_label(self, value: str) -> str:
        normalized = (value or "ALL").upper()
        for display, stored_value in self.coreml_unit_choices:
            if stored_value == normalized:
                return display
        return self.coreml_unit_choices[0][0]

    def _channel_display_to_value(self, label: str) -> str:
        for display, value in self.channel_options:
            if display == label:
                return value
        return "stable"

    def _channel_value_to_display(self, value: str) -> str:
        normalized = (value or "stable").lower()
        for display, stored in self.channel_options:
            if stored == normalized:
                return display
        return self.channel_options[0][0]

    def load_reid_config(self) -> dict:
        try:
            with open(self.reid_config_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            messagebox.showwarning(
                "ReID Configuration Missing",
                f"Could not find reid_config.json at {self.reid_config_path}. Default settings will be used."
            )
            return {}
        except json.JSONDecodeError as exc:
            messagebox.showerror(
                "ReID Configuration Error",
                f"Failed to parse reid_config.json: {exc}"
            )
            return {}
        except Exception as exc:
            messagebox.showerror(
                "ReID Configuration Error",
                f"Unexpected error loading reid_config.json: {exc}"
            )
            return {}

    def save_reid_config(self) -> bool:
        try:
            with open(self.reid_config_path, "w", encoding="utf-8") as handle:
                json.dump(self.reid_config, handle, indent=2)
            return True
        except Exception as exc:
            messagebox.showerror(
                "Settings",
                f"Failed to save ReID configuration: {exc}"
            )
            return False

    def browse_coreml_model(self):
        file_path = filedialog.askopenfilename(
            title="Select Core ML model",
            filetypes=[("Core ML Packages", "*.mlpackage"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        path_obj = Path(file_path)
        try:
            relative_path = path_obj.relative_to(self.project_root)
            self.coreml_path_var.set(str(relative_path))
        except ValueError:
            self.coreml_path_var.set(str(path_obj))


def main():
    """Main entry point"""
    try:
        app = LauncherGUI()
        app.run()
    except Exception as e:
        print(f"Error starting launcher: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

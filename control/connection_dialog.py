#!/usr/bin/env python3

# Connection Dialog for Multi-Camera IR Beacon Tracker
# Allows users to choose between live mode, demo mode, and configuration program.

import tkinter as tk
from tkinter import ttk, messagebox
import os
import logging
import subprocess
import sys
import webbrowser
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONTROL_DIR.parent

logger = logging.getLogger("connection_dialog")

class ConnectionDialog:
    """Dialog for selecting application mode"""
    
    def __init__(self, config_file="../config/roof_array_config.json"):
        self.config_file = config_file
        self.result = None
        self.root = None
        
    def show(self):
        """Show the connection dialog and return the user's choice"""
        self.root = tk.Tk()
        self.root.title("Multi-Camera IR Beacon Tracker - Mode Selection")
        self.root.geometry("450x350")
        self.root.resizable(False, False)
        
        # Center the window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.root.winfo_screenheight() // 2) - (350 // 2)
        self.root.geometry(f"450x350+{x}+{y}")
        
        self._create_widgets()
        self._build_menubar()
        
        # Make dialog modal
        self.root.transient()
        self.root.grab_set()
        
        # Start the event loop
        self.root.mainloop()
        
        return self.result
    
    def _create_widgets(self):
        """Create and layout the dialog widgets"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Title
        title_label = ttk.Label(main_frame, text="Multi-Camera IR Beacon Tracker", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Subtitle
        subtitle_label = ttk.Label(main_frame, text="Please select the mode you want to run:", 
                                  font=("Arial", 11))
        subtitle_label.grid(row=1, column=0, columnspan=2, pady=(0, 20))
        
        # Mode selection frame
        mode_frame = ttk.LabelFrame(main_frame, text="Application Mode", padding="15")
        mode_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 20))
        
        # Live mode button
        live_frame = ttk.Frame(mode_frame)
        live_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        live_btn = ttk.Button(live_frame, text="Live Mode", 
                             command=self._select_live_mode, width=20)
        live_btn.grid(row=0, column=0, padx=(0, 15))
        
        live_desc = ttk.Label(live_frame, text="Connect to real cameras", 
                             font=("Arial", 9), foreground="gray")
        live_desc.grid(row=0, column=1, sticky=tk.W)
        
        # Check if config file exists for live mode
        if not os.path.exists(self.config_file):
            live_btn.config(state="disabled")
            live_desc.config(text="(Configuration required)", foreground="red")
        
        # Demo mode button
        demo_frame = ttk.Frame(mode_frame)
        demo_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        
        demo_btn = ttk.Button(demo_frame, text="Demo Mode", 
                             command=self._select_demo_mode, width=20)
        demo_btn.grid(row=0, column=0, padx=(0, 15))
        
        demo_desc = ttk.Label(demo_frame, text="Run with simulated cameras", 
                             font=("Arial", 9), foreground="gray")
        demo_desc.grid(row=0, column=1, sticky=tk.W)
        
        # Configuration button
        config_frame = ttk.Frame(mode_frame)
        config_frame.grid(row=2, column=0, sticky="ew")
        
        config_btn = ttk.Button(config_frame, text="Configuration", 
                               command=self._select_config_mode, width=20)
        config_btn.grid(row=0, column=0, padx=(0, 15))
        
        config_desc = ttk.Label(config_frame, text="Set up camera connections", 
                               font=("Arial", 9), foreground="gray")
        config_desc.grid(row=0, column=1, sticky=tk.W)
        
        # Status frame
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        # Configuration file status
        if os.path.exists(self.config_file):
            status_text = f"✓ Configuration file found: {self.config_file}"
            status_color = "green"
        else:
            status_text = f"⚠ Configuration file not found: {self.config_file}"
            status_color = "orange"
        
        status_label = ttk.Label(status_frame, text=status_text, 
                               font=("Arial", 9), foreground=status_color)
        status_label.grid(row=0, column=0, sticky=tk.W)
        
        # Exit button
        exit_btn = ttk.Button(main_frame, text="Exit", command=self._exit)
        exit_btn.grid(row=4, column=0, columnspan=2, pady=(20, 0))
        
        # Configure grid weights
        if self.root:
            self.root.columnconfigure(0, weight=1)
            self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        mode_frame.columnconfigure(0, weight=1)
        live_frame.columnconfigure(1, weight=1)
        demo_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(1, weight=1)
        status_frame.columnconfigure(0, weight=1)
    
    def _build_menubar(self) -> None:
        if not self.root:
            return

        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Launcher", command=self._open_launcher)
        file_menu.add_command(label="Check for Updates", command=self._launch_launcher_updates)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self._exit)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Roof Array Configuration",
            command=lambda: self._launch_script("camera_config_gui.py", "Camera Configuration"),
        )
        tools_menu.add_command(
            label="ReID Configuration",
            command=lambda: self._launch_script("reid_configurator.py", "ReID Configuration"),
        )
        tools_menu.add_command(
            label="Identity Configurator",
            command=lambda: self._launch_script("identity_configurator.py", "Identity Configurator"),
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="Diagnostics", command=self._open_launcher_diagnostics)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Project README", command=self._open_readme)
        help_menu.add_command(label="Report Issue", command=self._open_issue_tracker)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _launcher_path(self) -> Path:
        return PROJECT_ROOT / "launcher_gui.py"

    def _launch_script(self, relative_script: str, description: str) -> None:
        script_path = CONTROL_DIR / relative_script
        if not script_path.exists():
            messagebox.showerror("Missing Tool", f"{description} not found at:\n{script_path}")
            return

        try:
            subprocess.Popen([sys.executable, str(script_path)])
        except Exception as exc:
            messagebox.showerror("Launch Failed", f"Could not open {description}:\n{exc}")

    def _open_launcher(self) -> None:
        launcher = self._launcher_path()
        if not launcher.exists():
            messagebox.showerror("Launcher Missing", "The main launcher could not be located.")
            return
        try:
            subprocess.Popen([sys.executable, str(launcher)])
        except Exception as exc:
            messagebox.showerror("Launcher Error", f"Failed to open launcher:\n{exc}")

    def _launch_launcher_updates(self) -> None:
        self._open_launcher()

    def _open_launcher_diagnostics(self) -> None:
        self._open_launcher()

    def _open_readme(self) -> None:
        webbrowser.open_new_tab("https://github.com/Stavro-Purdie/Automated-Followspot-System")

    def _open_issue_tracker(self) -> None:
        webbrowser.open_new_tab(
            "https://github.com/Stavro-Purdie/Automated-Followspot-System/issues/new/choose"
        )

    def _select_live_mode(self):
        """Select live mode"""
        if not os.path.exists(self.config_file):
            messagebox.showerror("Configuration Required", 
                               f"Configuration file '{self.config_file}' not found.\n"
                               "Please run Configuration mode first to set up cameras.")
            return
        
        self.result = {"mode": "live", "config": self.config_file}
        if self.root:
            self.root.destroy()
    
    def _select_demo_mode(self):
        """Select demo mode"""
        self.result = {"mode": "demo", "config": self.config_file}
        if self.root:
            self.root.destroy()
    
    def _select_config_mode(self):
        """Select configuration mode"""
        self.result = {"mode": "config", "config": self.config_file}
        if self.root:
            self.root.destroy()
    
    def _exit(self):
        """Exit the application"""
        self.result = None
        if self.root:
            self.root.destroy()


def show_connection_dialog(config_file="../config/roof_array_config.json"):
    """
    Show the connection dialog and return the user's choice.
    
    Args:
        config_file (str): Path to the configuration file
        
    Returns:
        dict or None: Dictionary with 'mode' and 'config' keys, or None if cancelled
    """
    dialog = ConnectionDialog(config_file)
    return dialog.show()


if __name__ == "__main__":
    # Test the dialog
    result = show_connection_dialog()
    if result:
        print(f"Selected mode: {result['mode']}")
        print(f"Config file: {result['config']}")
    else:
        print("Dialog cancelled")

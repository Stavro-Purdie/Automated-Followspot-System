#!/usr/bin/env python3
"""
GUI Launcher for Automated Followspot System
Provides graphical interface for installation, configuration, and management of Control and Node stacks.
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
from datetime import datetime, timedelta
import queue
import webbrowser
import shutil
import uuid
from urllib.parse import urlparse

class LauncherGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Automated Followspot System Launcher")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        # Initialize configuration
        self.config_file = "launcher_config.json"
        self.config = self.load_config()

        # Identity gallery storage
        self.identity_root = Path(__file__).parent / "identity_gallery"
        self.identity_root.mkdir(exist_ok=True)
        self.identity_manifest_path = self.identity_root / "manifest.json"
        self.identity_data = self.load_identity_manifest()
        self.identity_order = []
        self.identity_listbox = None
        self.identity_details_var = None
        self.identity_status_var = None
        
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
            return default_config
    
    def load_identity_manifest(self):
        """Load identity manifest from disk or return empty structure."""
        manifest = {"identities": []}
        if self.identity_manifest_path.exists():
            try:
                with open(self.identity_manifest_path, "r", encoding="utf-8") as manifest_file:
                    data = json.load(manifest_file)
                if isinstance(data, dict):
                    identities = data.get("identities", [])
                    if isinstance(identities, list):
                        for identity in identities:
                            identity.setdefault("images", [])
                            identity.setdefault("created_at", datetime.now().isoformat())
                            identity.setdefault("updated_at", identity["created_at"])
                        manifest["identities"] = identities
            except Exception as exc:
                print(f"Warning: failed to load identity manifest: {exc}")
        return manifest

    def save_identity_manifest(self):
        """Persist identity manifest to disk."""
        try:
            with open(self.identity_manifest_path, "w", encoding="utf-8") as manifest_file:
                json.dump(self.identity_data, manifest_file, indent=2)
        except Exception as exc:
            if hasattr(self, "terminal_text"):
                self.log_to_terminal(f"Failed to save identity manifest: {exc}")
            messagebox.showerror("Save Error", f"Unable to save identity manifest:\n{exc}")

    def refresh_identity_list(self, selected_id=None):
        """Refresh identity list UI."""
        if self.identity_listbox is None or self.identity_details_var is None:
            return

        selected_id = selected_id or self.get_selected_identity_id()
        identities = self.identity_data.get("identities", [])
        identities = sorted(identities, key=lambda item: item.get("name", "").lower())
        self.identity_order = [identity["id"] for identity in identities]

        self.identity_listbox.delete(0, tk.END)
        for identity in identities:
            image_count = len(identity.get("images", []))
            display_name = identity.get("name", "Unnamed Identity")
            self.identity_listbox.insert(tk.END, f"{display_name} ({image_count})")

        if self.identity_order:
            if selected_id and selected_id in self.identity_order:
                self.select_identity(selected_id)
            else:
                self.identity_listbox.selection_set(0)
                self.identity_listbox.event_generate("<<ListboxSelect>>")
        else:
            self.identity_details_var.set("No identities imported yet. Add one to begin.")
            if self.identity_status_var is not None:
                self.identity_status_var.set("Add a new identity to begin.")

    def get_selected_identity_id(self):
        if self.identity_listbox is None:
            return None
        selection = self.identity_listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        if 0 <= index < len(self.identity_order):
            return self.identity_order[index]
        return None

    def select_identity(self, identity_id: str):
        if self.identity_listbox is None:
            return
        for idx, current_id in enumerate(self.identity_order):
            if current_id == identity_id:
                self.identity_listbox.selection_clear(0, tk.END)
                self.identity_listbox.selection_set(idx)
                self.identity_listbox.event_generate("<<ListboxSelect>>")
                break

    def get_selected_identity(self):
        identity_id = self.get_selected_identity_id()
        if identity_id is None:
            return None
        for identity in self.identity_data.get("identities", []):
            if identity.get("id") == identity_id:
                return identity
        return None

    def prompt_new_identity(self):
        name = simpledialog.askstring("New Identity", "Enter performer or identity name:", parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showinfo("Name Required", "Please enter a non-empty name for the identity.")
            return

        new_id = uuid.uuid4().hex[:8]
        existing_ids = {identity.get("id") for identity in self.identity_data.get("identities", [])}
        while new_id in existing_ids:
            new_id = uuid.uuid4().hex[:8]

        timestamp = datetime.now().isoformat()
        identity_entry = {
            "id": new_id,
            "name": name,
            "images": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }

        self.identity_data.setdefault("identities", []).append(identity_entry)
        (self.identity_root / new_id).mkdir(exist_ok=True)
        self.save_identity_manifest()
        self.refresh_identity_list(selected_id=new_id)
        if self.identity_status_var is not None:
            self.identity_status_var.set(f'Added identity "{name}".')
        if hasattr(self, "terminal_text"):
            self.log_to_terminal(f'Identity created: {name} ({new_id})')

    def import_identity_images(self):
        identity = self.get_selected_identity()
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity before importing photos.")
            return

        filepaths = filedialog.askopenfilenames(
            parent=self.root,
            title="Select photos",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not filepaths:
            return

        allowed = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        dest_dir = self.identity_root / identity["id"]
        dest_dir.mkdir(exist_ok=True)

        added = 0
        skipped = []
        for filepath in filepaths:
            src_path = Path(filepath)
            ext = src_path.suffix.lower()
            if ext not in allowed:
                skipped.append(f"Unsupported format: {src_path.name}")
                continue

            dest_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = dest_dir / dest_name
            try:
                shutil.copy2(src_path, dest_path)
                rel_path = str(dest_path.relative_to(self.identity_root))
                if rel_path not in identity.setdefault("images", []):
                    identity["images"].append(rel_path)
                added += 1
            except Exception as exc:
                skipped.append(f"{src_path.name}: {exc}")

        identity["updated_at"] = datetime.now().isoformat()
        self.save_identity_manifest()
        self.refresh_identity_list(selected_id=identity["id"])

        if added:
            message = f"Imported {added} image{'s' if added != 1 else ''}."
        else:
            message = "No new images were imported."

        if skipped:
            message += f" Skipped {len(skipped)} file{'s' if len(skipped) != 1 else ''}."
            messagebox.showwarning("Some files skipped", "\n".join(skipped))

        if self.identity_status_var is not None:
            self.identity_status_var.set(message)
        if hasattr(self, "terminal_text"):
            self.log_to_terminal(f"Identity {identity['name']} updated: {message}")

    def remove_identity(self):
        identity = self.get_selected_identity()
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity to remove.")
            return

        if not messagebox.askyesno(
            "Remove Identity",
            f"Delete identity '{identity['name']}' and all associated images?",
            parent=self.root,
        ):
            return

        folder = self.identity_root / identity["id"]
        try:
            if folder.exists():
                shutil.rmtree(folder)
        except Exception as exc:
            messagebox.showerror("Remove Failed", f"Could not delete identity folder:\n{exc}")
            return

        self.identity_data["identities"] = [i for i in self.identity_data.get("identities", []) if i.get("id") != identity["id"]]
        self.save_identity_manifest()
        self.refresh_identity_list()
        name = identity.get("name", "Unnamed")
        if self.identity_status_var is not None:
            self.identity_status_var.set(f'Removed identity "{name}".')
        if hasattr(self, "terminal_text"):
            self.log_to_terminal(f"Identity removed: {name} ({identity['id']})")

    def open_identity_folder(self):
        identity = self.get_selected_identity()
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity to open its folder.")
            return

        folder = self.identity_root / identity["id"]
        folder.mkdir(exist_ok=True)

        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(folder)], check=False)
            elif os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(folder)], check=False)
        except Exception as exc:
            messagebox.showerror("Open Folder Failed", f"Unable to open folder:\n{exc}")

    def update_identity_details(self, *_):
        if self.identity_details_var is None:
            return
        identity = self.get_selected_identity()
        if identity is None:
            self.identity_details_var.set("Select an identity to view details.")
            return

        image_count = len(identity.get("images", []))
        created = identity.get("created_at", "Unknown")
        updated = identity.get("updated_at", created)
        folder_name = (self.identity_root / identity["id"]).name
        details = (
            f"Name: {identity.get('name', 'Unnamed')}\n"
            f"Folder: {folder_name}\n"
            f"Images: {image_count}\n"
            f"Last Updated: {updated}"
        )
        self.identity_details_var.set(details)

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
    
    def create_status_frame(self, parent):
        """Create system status display"""
        status_frame = ttk.LabelFrame(parent, text="System Status", padding="10")
        status_frame.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 10))

        self.control_status_label = ttk.Label(
            status_frame,
            text="Control Stack: Not Installed",
            style='Status.TLabel',
        )
        self.control_status_label.grid(row=0, column=0, sticky="w", padx=(0, 20))

        self.node_status_label = ttk.Label(
            status_frame,
            text="Node Stack: Not Installed",
            style='Status.TLabel',
        )
        self.node_status_label.grid(row=0, column=1, sticky="w", padx=(0, 20))

        self.front_node_status_label = ttk.Label(
            status_frame,
            text="Front Node (ReID): Not Installed",
            style='Status.TLabel',
        )
        self.front_node_status_label.grid(row=0, column=2, sticky="w", padx=(0, 20))

        self.deps_status_label = ttk.Label(
            status_frame,
            text="Dependencies: Checking...",
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

        ttk.Button(self.roof_frame, text="Diagnostics", command=self.node_diagnostics).grid(
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
        """Create general options and identity gallery management"""
        general_frame = ttk.LabelFrame(parent, text="Identity & Tools", padding="10")
        general_frame.grid(row=3, column=2, sticky="nsew", padx=(5, 0))
        general_frame.columnconfigure(0, weight=1)
        general_frame.rowconfigure(0, weight=3)
        general_frame.rowconfigure(1, weight=1)

        identity_frame = ttk.LabelFrame(general_frame, text="Identity Gallery", padding="8")
        identity_frame.grid(row=0, column=0, sticky="nsew")
        identity_frame.columnconfigure(0, weight=1)
        identity_frame.rowconfigure(0, weight=1)

        self.identity_listbox = tk.Listbox(identity_frame, height=8, exportselection=False)
        self.identity_listbox.grid(row=0, column=0, sticky="nsew")
        identity_scroll = ttk.Scrollbar(identity_frame, orient=tk.VERTICAL, command=self.identity_listbox.yview)
        identity_scroll.grid(row=0, column=1, sticky="ns")
        self.identity_listbox.configure(yscrollcommand=identity_scroll.set)
        self.identity_listbox.bind("<<ListboxSelect>>", self.update_identity_details)

        self.identity_details_var = tk.StringVar(value="No identities imported yet.")
        ttk.Label(
            identity_frame,
            textvariable=self.identity_details_var,
            wraplength=240,
            justify="left",
            style='Status.TLabel'
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        button_frame = ttk.Frame(identity_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        for col in range(4):
            button_frame.columnconfigure(col, weight=1)

        ttk.Button(button_frame, text="New", command=self.prompt_new_identity).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Import Photos", command=self.import_identity_images).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Open Folder", command=self.open_identity_folder).grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Remove", command=self.remove_identity).grid(row=0, column=3, padx=2, pady=2, sticky="ew")

        self.identity_status_var = tk.StringVar(value="Add a new identity to begin.")
        ttk.Label(
            identity_frame,
            textvariable=self.identity_status_var,
            wraplength=240,
            justify="left",
            style='Status.TLabel'
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

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

        ttk.Separator(tools_frame, orient='horizontal').grid(row=4, column=0, sticky="ew", pady=10)

        ttk.Button(tools_frame, text="Exit", command=self.root.quit).grid(row=5, column=0, sticky="ew")

        self.refresh_identity_list()
    
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

        text_widget = scrolledtext.ScrolledText(viewer, wrap=tk.WORD, font=('Consolas', 10))
        text_widget.pack(fill=tk.BOTH, expand=True)
        try:
            text_widget.insert(tk.END, log_file.read_text(encoding="utf-8"))
        except Exception as exc:
            text_widget.insert(tk.END, f"Failed to read log file: {exc}")
        text_widget.config(state=tk.DISABLED)
    
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

        script_path = Path(__file__).parent / "control" / "fused_main.py"
        if not script_path.exists():
            messagebox.showerror("Error", "Fused controller script not found")
            return

        self.log_to_terminal("Launching fused live mode (IR + ReID)...")
        self.run_script(script_path, "Fused Live Mode")
    
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


class InstallerWindow:
    """GUI installer window for control or node stack"""
    
    def __init__(self, parent, stack_type, repair_mode=False, reinstall_mode=False):
        self.parent = parent
        self.stack_type = stack_type
        self.repair_mode = repair_mode
        self.reinstall_mode = reinstall_mode
        self.stack_display = stack_type.replace('_', ' ').title()
        
        self.window = tk.Toplevel(parent.root)
        self.window.title(f"Install {self.stack_display} Stack")
        self.window.geometry("700x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        
        self.setup_installer_ui()
    
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
        self.install_button.config(state=tk.DISABLED)
        self.progress.start()
        
        def install_process():
            try:
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
        
        self.setup_ui()
    
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
    try:
        app = LauncherGUI()
        app.run()
    except Exception as e:
        print(f"Error starting launcher: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

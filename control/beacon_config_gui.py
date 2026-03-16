#!/usr/bin/env python3
"""
Beacon Configuration & Monitoring Tool
Network-accessible interface for configuring and monitoring IR beacon hardware.
Allows real-time control of battery monitoring, fan speed, voltage/amperage tracking,
and LED duty cycle settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import logging
import threading
import time
import platform
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import sys

logger = logging.getLogger("beacon_config_gui")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from launcher_gui import ensure_window_fits_content, set_native_theme, get_adaptive_colors, get_system_appearance
except Exception:
    def ensure_window_fits_content(window, *, min_width=800, min_height=600, padding=48, center=True):
        """Fallback window sizing helper"""
        try:
            window.update_idletasks()
        except:
            return
        width = max(min_width, window.winfo_reqwidth() + padding)
        height = max(min_height, window.winfo_reqheight() + padding)
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
        """Set ttk theme to match the operating system."""
        system = platform.system()
        if system == "Darwin":
            theme = "aqua"
        elif system == "Windows":
            theme = "vista"
        else:
            theme = "clam"
        try:
            style.theme_use(theme)
        except tk.TclError:
            try:
                style.theme_use('default')
            except:
                pass
    
    def get_system_appearance() -> str:
        """Fallback: detect system appearance"""
        import subprocess
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True, text=True, timeout=1
                )
                return "dark" if result.returncode == 0 or "Dark" in result.stdout else "light"
            except:
                return "light"
        return "light"
    
    def get_adaptive_colors() -> dict:
        """Fallback: get adaptive colors"""
        appearance = get_system_appearance()
        if appearance == "dark":
            return {
                "bg_primary": "#1e1e1e",
                "bg_secondary": "#2d2d2d",
                "fg_primary": "#e0e0e0",
                "fg_secondary": "#b0b0b0",
                "accent_green": "#4ec94e",
                "accent_orange": "#ff9500",
                "accent_red": "#ff5555",
                "border": "#3d3d3d",
            }
        else:
            return {
                "bg_primary": "#ffffff",
                "bg_secondary": "#f5f5f5",
                "fg_primary": "#1a1a1a",
                "fg_secondary": "#666666",
                "accent_green": "#00cc00",
                "accent_orange": "#ff9900",
                "accent_red": "#ff3333",
                "border": "#cccccc",
            }

@dataclass
class BeaconSettings:
    """Beacon configuration parameters"""
    beacon_id: str
    ip_address: str
    port: int = 5000
    battery_enabled: bool = True
    battery_low_threshold: float = 20.0  # Percentage
    fan_enabled: bool = True
    fan_speed_pwm: int = 100  # 0-255
    led_duty_cycle: int = 100  # 0-100 percent
    voltage_nominal: float = 12.0
    amperage_limit: float = 5.0
    poll_interval: float = 1.0  # Seconds between polls

@dataclass
class BeaconStatus:
    """Real-time beacon status from device"""
    beacon_id: str
    online: bool = False
    battery_percent: Optional[float] = None
    battery_voltage: Optional[float] = None
    current_amperage: Optional[float] = None
    fan_speed_rpm: Optional[int] = None
    led_brightness: Optional[int] = None
    temperature_c: Optional[float] = None
    uptime_seconds: Optional[int] = None
    last_update: Optional[float] = None
    status_message: str = "Offline"

class BeaconConfigGUI:
    """Beacon configuration and monitoring interface"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Beacon Configuration & Monitor")
        self.root.geometry("1100x750")
        self.root.configure(bg="SystemButtonFace")
        
        # Use native OS theme
        style = ttk.Style()
        set_native_theme(style)
        
        self.beacons: Dict[str, BeaconSettings] = {}
        self.beacon_status: Dict[str, BeaconStatus] = {}
        self.config_file = PROJECT_ROOT / "config" / "beacons_config.json"
        self.monitoring_active = False
        self.update_thread: Optional[threading.Thread] = None
        
        # Load existing configuration
        self.load_config()
        
        # Setup GUI
        self.setup_styles()
        self.create_menu()
        self.create_widgets()
        ensure_window_fits_content(self.root, min_width=1100, min_height=750, padding=60, center=True)
        
        # Start monitoring
        self.start_monitoring()
    
    def load_config(self):
        """Load beacon configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    for beacon_id, config in data.get('beacons', {}).items():
                        self.beacons[beacon_id] = BeaconSettings(**config)
                        self.beacon_status[beacon_id] = BeaconStatus(beacon_id=beacon_id)
                logger.info(f"Loaded {len(self.beacons)} beacons from config")
            except Exception as e:
                logger.error(f"Error loading beacon config: {e}")
        
        if not self.beacons:
            self._create_default_beacons()
    
    def _create_default_beacons(self):
        """Create default beacon configurations for demo"""
        defaults = [
            BeaconSettings(beacon_id="Beacon-1", ip_address="192.168.1.50"),
            BeaconSettings(beacon_id="Beacon-2", ip_address="192.168.1.51"),
        ]
        for beacon in defaults:
            self.beacons[beacon.beacon_id] = beacon
            self.beacon_status[beacon.beacon_id] = BeaconStatus(beacon_id=beacon.beacon_id)
    
    def save_config(self):
        """Save beacon configuration to file"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'beacons': {
                    beacon_id: asdict(settings)
                    for beacon_id, settings in self.beacons.items()
                }
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved beacon config to {self.config_file}")
            messagebox.showinfo("Success", "Beacon configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}")
    
    def setup_styles(self):
        """Setup modern GUI styles"""
        style = ttk.Style()
        style.configure('Title.TLabel', font=('Arial', 14, 'bold'), foreground='#1a1a1a')
        style.configure('Subtitle.TLabel', font=('Arial', 11, 'bold'), foreground='#2c3e50')
        style.configure('Status.TLabel', font=('Arial', 9), foreground='#34495e')
        style.configure('Success.TLabel', font=('Arial', 9), foreground='#27ae60')
        style.configure('Warning.TLabel', font=('Arial', 9), foreground='#f39c12')
        style.configure('Error.TLabel', font=('Arial', 9), foreground='#e74c3c')
    
    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Configuration", command=self.save_config)
        file_menu.add_command(label="Load Configuration", command=self.load_config_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        menubar.add_cascade(label="File", menu=file_menu)
        
        beacon_menu = tk.Menu(menubar, tearoff=0)
        beacon_menu.add_command(label="Add Beacon", command=self.add_beacon_dialog)
        beacon_menu.add_command(label="Remove Selected Beacon", command=self.remove_beacon)
        beacon_menu.add_separator()
        beacon_menu.add_command(label="Test Connection", command=self.test_connection)
        menubar.add_cascade(label="Beacons", menu=beacon_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def create_widgets(self):
        """Create main GUI layout"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title = ttk.Label(main_frame, text="Beacon Configuration & Monitoring", style='Title.TLabel')
        title.grid(row=0, column=0, sticky="w", pady=(0, 15))
        
        # Control panel
        self.create_control_panel(main_frame)
        
        # Status display
        self.create_status_panel(main_frame)
        
        # Monitor panel
        self.create_monitor_panel(main_frame)
    
    def create_control_panel(self, parent):
        """Create beacon selection and configuration controls"""
        control_frame = ttk.LabelFrame(parent, text="Beacon Control", padding="10")
        control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Beacon selector
        ttk.Label(control_frame, text="Select Beacon:").grid(row=0, column=0, sticky="w")
        
        self.beacon_var = tk.StringVar()
        beacon_list = list(self.beacons.keys())
        if beacon_list:
            self.beacon_var.set(beacon_list[0])
        
        beacon_combo = ttk.Combobox(
            control_frame,
            textvariable=self.beacon_var,
            values=beacon_list,
            state="readonly",
            width=20
        )
        beacon_combo.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        beacon_combo.bind("<<ComboboxSelected>>", self.on_beacon_selected)
        
        # Action buttons
        ttk.Button(control_frame, text="Add Beacon", command=self.add_beacon_dialog).grid(row=0, column=2, padx=2)
        ttk.Button(control_frame, text="Remove", command=self.remove_beacon).grid(row=0, column=3, padx=2)
        ttk.Button(control_frame, text="Refresh", command=self.refresh_status).grid(row=0, column=4, padx=2)
        
        control_frame.columnconfigure(1, weight=1)
    
    def create_status_panel(self, parent):
        """Create real-time status display"""
        status_frame = ttk.LabelFrame(parent, text="Beacon Status", padding="10")
        status_frame.grid(row=2, column=0, sticky="nsew")
        
        # Status grid
        row = 0
        self.status_labels = {}
        
        status_items = [
            ("Connection Status", "connection"),
            ("Battery Level", "battery"),
            ("Battery Voltage", "voltage"),
            ("Current Draw", "amperage"),
            ("Fan Speed (RPM)", "fan"),
            ("LED Brightness", "led"),
            ("Temperature", "temperature"),
            ("Uptime", "uptime"),
        ]
        
        for label_text, key in status_items:
            ttk.Label(status_frame, text=f"{label_text}:", font=('Arial', 9, 'bold')).grid(row=row, column=0, sticky="w", pady=5)
            value_label = ttk.Label(status_frame, text="--", style='Status.TLabel')
            value_label.grid(row=row, column=1, sticky="w", padx=(20, 0), pady=5)
            self.status_labels[key] = value_label
            row += 1
        
        status_frame.columnconfigure(1, weight=1)
    
    def create_monitor_panel(self, parent):
        """Create configuration controls for selected beacon"""
        monitor_frame = ttk.LabelFrame(parent, text="Configuration", padding="10")
        monitor_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        
        row = 0
        
        # Fan speed control
        ttk.Label(monitor_frame, text="Fan Speed (PWM 0-255):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_speed_var = tk.IntVar(value=100)
        fan_scale = ttk.Scale(monitor_frame, from_=0, to=255, orient=tk.HORIZONTAL, variable=self.fan_speed_var)
        fan_scale.grid(row=row, column=1, sticky="ew", padx=(10, 5))
        self.fan_speed_label = ttk.Label(monitor_frame, text="100", width=4)
        self.fan_speed_label.grid(row=row, column=2)
        self.fan_speed_var.trace('w', lambda *args: self.fan_speed_label.config(text=str(self.fan_speed_var.get())))
        row += 1
        
        # LED duty cycle control
        ttk.Label(monitor_frame, text="LED Duty Cycle (0-100%):").grid(row=row, column=0, sticky="w", pady=5)
        self.led_duty_var = tk.IntVar(value=100)
        led_scale = ttk.Scale(monitor_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.led_duty_var)
        led_scale.grid(row=row, column=1, sticky="ew", padx=(10, 5))
        self.led_duty_label = ttk.Label(monitor_frame, text="100%", width=4)
        self.led_duty_label.grid(row=row, column=2)
        self.led_duty_var.trace('w', lambda *args: self.led_duty_label.config(text=f"{self.led_duty_var.get()}%"))
        row += 1
        
        # Battery threshold
        ttk.Label(monitor_frame, text="Battery Low Threshold (%):").grid(row=row, column=0, sticky="w", pady=5)
        self.battery_threshold_var = tk.IntVar(value=20)
        battery_spin = ttk.Spinbox(monitor_frame, from_=1, to=50, textvariable=self.battery_threshold_var, width=10)
        battery_spin.grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        # Amperage limit
        ttk.Label(monitor_frame, text="Amperage Limit (A):").grid(row=row, column=0, sticky="w", pady=5)
        self.amperage_limit_var = tk.DoubleVar(value=5.0)
        amperage_spin = ttk.Spinbox(monitor_frame, from_=0.1, to=20.0, increment=0.1, textvariable=self.amperage_limit_var, width=10)
        amperage_spin.grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        # Apply button
        ttk.Button(monitor_frame, text="Apply Settings", command=self.apply_settings).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        
        monitor_frame.columnconfigure(1, weight=1)
    
    def on_beacon_selected(self, event=None):
        """Handle beacon selection change"""
        beacon_id = self.beacon_var.get()
        if beacon_id in self.beacons:
            beacon = self.beacons[beacon_id]
            self.fan_speed_var.set(beacon.fan_speed_pwm)
            self.led_duty_var.set(beacon.led_duty_cycle)
            self.battery_threshold_var.set(int(beacon.battery_low_threshold))
            self.amperage_limit_var.set(beacon.amperage_limit)
            self.refresh_status()
    
    def refresh_status(self):
        """Refresh beacon status display"""
        beacon_id = self.beacon_var.get()
        if beacon_id not in self.beacon_status:
            return
        
        status = self.beacon_status[beacon_id]
        
        # Update status labels
        connection_text = "✓ Online" if status.online else "✗ Offline"
        connection_style = "Success.TLabel" if status.online else "Error.TLabel"
        self.status_labels["connection"].config(text=connection_text, style=connection_style)
        
        battery_text = f"{status.battery_percent:.1f}%" if status.battery_percent is not None else "--"
        self.status_labels["battery"].config(text=battery_text)
        
        voltage_text = f"{status.battery_voltage:.2f}V" if status.battery_voltage is not None else "--"
        self.status_labels["voltage"].config(text=voltage_text)
        
        amperage_text = f"{status.current_amperage:.2f}A" if status.current_amperage is not None else "--"
        self.status_labels["amperage"].config(text=amperage_text)
        
        fan_text = f"{status.fan_speed_rpm} RPM" if status.fan_speed_rpm is not None else "--"
        self.status_labels["fan"].config(text=fan_text)
        
        led_text = f"{status.led_brightness}%" if status.led_brightness is not None else "--"
        self.status_labels["led"].config(text=led_text)
        
        temp_text = f"{status.temperature_c:.1f}°C" if status.temperature_c is not None else "--"
        self.status_labels["temperature"].config(text=temp_text)
        
        uptime_text = f"{status.uptime_seconds}s" if status.uptime_seconds is not None else "--"
        self.status_labels["uptime"].config(text=uptime_text)
    
    def apply_settings(self):
        """Apply settings to selected beacon"""
        beacon_id = self.beacon_var.get()
        if beacon_id not in self.beacons:
            messagebox.showwarning("Warning", "Please select a valid beacon")
            return
        
        beacon = self.beacons[beacon_id]
        beacon.fan_speed_pwm = self.fan_speed_var.get()
        beacon.led_duty_cycle = self.led_duty_var.get()
        beacon.battery_low_threshold = float(self.battery_threshold_var.get())
        beacon.amperage_limit = self.amperage_limit_var.get()
        
        logger.info(f"Applied settings to {beacon_id}")
        messagebox.showinfo("Success", f"Settings applied to {beacon_id}")
    
    def add_beacon_dialog(self):
        """Show dialog to add a new beacon"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Beacon")
        dialog.geometry("400x200")
        
        ttk.Label(dialog, text="Beacon ID:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        beacon_id_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=beacon_id_var, width=30).grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(dialog, text="IP Address:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ip_var = tk.StringVar(value="192.168.1.")
        ttk.Entry(dialog, textvariable=ip_var, width=30).grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(dialog, text="Port:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        port_var = tk.StringVar(value="5000")
        ttk.Entry(dialog, textvariable=port_var, width=30).grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        def save_beacon():
            beacon_id = beacon_id_var.get().strip()
            ip = ip_var.get().strip()
            try:
                port = int(port_var.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid port number")
                return
            
            if not beacon_id or not ip:
                messagebox.showwarning("Warning", "Beacon ID and IP address are required")
                return
            
            new_beacon = BeaconSettings(beacon_id=beacon_id, ip_address=ip, port=port)
            self.beacons[beacon_id] = new_beacon
            self.beacon_status[beacon_id] = BeaconStatus(beacon_id=beacon_id)
            
            dialog.destroy()
            self.refresh_beacon_list()
        
        ttk.Button(dialog, text="Add", command=save_beacon).grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=20)
        dialog.columnconfigure(1, weight=1)
        ensure_window_fits_content(dialog, min_width=400, min_height=200, center=True)
    
    def remove_beacon(self):
        """Remove selected beacon"""
        beacon_id = self.beacon_var.get()
        if not beacon_id:
            messagebox.showwarning("Warning", "Please select a beacon to remove")
            return
        
        if messagebox.askyesno("Confirm", f"Remove beacon '{beacon_id}'?"):
            del self.beacons[beacon_id]
            del self.beacon_status[beacon_id]
            self.refresh_beacon_list()
    
    def refresh_beacon_list(self):
        """Refresh beacon list in UI"""
        beacon_list = list(self.beacons.keys())
        self.beacon_var.set(beacon_list[0] if beacon_list else "")
    
    def load_config_dialog(self):
        """Load configuration from file"""
        file_path = filedialog.askopenfilename(
            initialdir=str(self.config_file.parent),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.config_file = Path(file_path)
            self.load_config()
            self.refresh_beacon_list()
    
    def test_connection(self):
        """Test connection to selected beacon"""
        beacon_id = self.beacon_var.get()
        if beacon_id not in self.beacons:
            messagebox.showwarning("Warning", "Please select a beacon")
            return
        
        beacon = self.beacons[beacon_id]
        # Simulate connection test
        self.beacon_status[beacon_id].online = True
        self.beacon_status[beacon_id].battery_percent = 85.5
        self.beacon_status[beacon_id].battery_voltage = 12.1
        self.beacon_status[beacon_id].current_amperage = 2.3
        self.beacon_status[beacon_id].fan_speed_rpm = 1200
        self.beacon_status[beacon_id].led_brightness = 100
        self.beacon_status[beacon_id].temperature_c = 35.2
        self.beacon_status[beacon_id].uptime_seconds = 7200
        
        self.refresh_status()
        messagebox.showinfo("Success", f"Connected to {beacon_id}")
    
    def start_monitoring(self):
        """Start background monitoring"""
        self.monitoring_active = True
        self.update_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.update_thread.start()
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            # Simulate beacon polling
            for beacon_id in self.beacons:
                status = self.beacon_status[beacon_id]
                status.last_update = time.time()
            time.sleep(1.0)
    
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About Beacon Configuration Tool",
            "Beacon Configuration & Monitoring Tool v1.0\n\n"
            "Network-accessible interface for managing IR beacon hardware.\n"
            "Control fan speed, LED duty cycles, and monitor battery/power status."
        )
    
    def on_closing(self):
        """Handle window closing"""
        self.monitoring_active = False
        if self.update_thread:
            self.update_thread.join(timeout=1.0)
        self.root.destroy()
    
    def run(self):
        """Start the GUI main loop"""
        self.root.mainloop()

def main():
    """Entry point for beacon config GUI"""
    app = BeaconConfigGUI()
    app.run()

if __name__ == "__main__":
    main()

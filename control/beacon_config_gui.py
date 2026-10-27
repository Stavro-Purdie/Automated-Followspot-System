#!/usr/bin/env python3
"""
Beacon Configurator - Modern tabbed interface with live monitor cards.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import json
import logging
import threading
import time
import platform
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import sys

# Ensure project root is on sys.path
_proj = Path(__file__).resolve().parent.parent
if str(_proj) not in sys.path:
    sys.path.insert(0, str(_proj))

from control.beacon_network import discover_beacons, fetch_status, push_config, push_name

logger = logging.getLogger("beacon_config_gui")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from launcher_gui import ensure_window_fits_content, set_native_theme, get_adaptive_colors, get_system_appearance
except Exception:
    def ensure_window_fits_content(window, *, min_width=800, min_height=600, padding=48, center=True):
        try:
            window.update_idletasks()
        except Exception:
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
            except Exception:
                pass
    
    def get_system_appearance() -> str:
        import subprocess
        if platform.system() == "Darwin":
            try:
                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True, text=True, timeout=1
                )
                return "dark" if result.returncode == 0 or "Dark" in result.stdout else "light"
            except Exception:
                return "light"
        return "light"
    
    def get_adaptive_colors() -> dict:
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
    display_name: str = "Beacon"
    battery_enabled: bool = True
    battery_low_threshold: float = 20.0
    fan_enabled: bool = True
    fan_auto: bool = True
    fan_speed_pwm: int = 100
    fan_temp_start: float = 40.0
    fan_temp_full: float = 55.0
    fan_min_pwm: int = 80
    fan_max_pwm: int = 255
    led_duty_cycle: int = 100
    voltage_nominal: float = 12.0
    amperage_limit: float = 5.0
    poll_interval: float = 1.0


@dataclass
class BeaconStatus:
    """Real-time beacon status from device"""
    beacon_id: str
    display_name: Optional[str] = None
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


class BeaconCard:
    """Visual beacon status card for live monitor tab - uses native ttk.Progressbar for MacOS-style meters"""
    
    def __init__(self, parent: tk.Frame, beacon_id: str, beacon: BeaconSettings, status: BeaconStatus, colors: dict, on_click_callback=None):
        self.beacon_id = beacon_id
        self.beacon = beacon
        self.status = status
        self.colors = colors
        self.on_click_callback = on_click_callback
        
        # Use flat frame without raised border (no weird highlight)
        self.frame = tk.Frame(parent, bg=colors["bg_secondary"], bd=0, highlightthickness=0)
        self.frame.bind("<Button-1>", self._on_click)
        
        # Header
        header = tk.Frame(self.frame, bg=colors["bg_secondary"], height=40)
        header.pack(fill=tk.X, padx=1, pady=1)
        header.pack_propagate(False)
        
        # Status LED
        self.status_led = tk.Canvas(header, width=14, height=14, bg=colors["bg_secondary"], highlightthickness=0)
        self.status_led.pack(side=tk.LEFT, padx=10, pady=13)
        
        # Beacon ID and name
        id_frame = tk.Frame(header, bg=colors["bg_secondary"])
        id_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.id_label = tk.Label(
            id_frame,
            text=beacon_id,
            bg=colors["bg_secondary"],
            fg="#ffffff",
            font=("System", 13, "bold"),
            anchor="w"
        )
        self.id_label.pack(fill=tk.X)
        self.id_label.bind("<Button-1>", self._on_click)
        
        self.name_label = tk.Label(
            id_frame,
            text=status.display_name or beacon.display_name,
            bg=colors["bg_secondary"],
            fg="#cccccc",
            font=("System", 9),
            anchor="w"
        )
        self.name_label.pack(fill=tk.X)
        self.name_label.bind("<Button-1>", self._on_click)
        
        # Status text
        self.status_text = tk.Label(
            header,
            text="ONLINE" if status.online else "OFFLINE",
            bg=colors["bg_secondary"],
            fg=colors["accent_green"] if status.online else colors["accent_red"],
            font=("System", 10, "bold")
        )
        self.status_text.pack(side=tk.RIGHT, padx=10)
        self.status_text.bind("<Button-1>", self._on_click)
        
        # Content area
        content = tk.Frame(self.frame, bg=colors["bg_secondary"])
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        
        # IP address
        ip_text = f"{beacon.ip_address}:{beacon.port}"
        self.ip_label = tk.Label(content, text=ip_text, bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 8))
        self.ip_label.pack(anchor=tk.W)
        self.ip_label.bind("<Button-1>", self._on_click)
        
        # Battery - macOS-style progressbar
        self.battery_bar = self._create_metric_bar(content, "Battery", status.battery_percent, 0, 100)
        self._update_metric_bar(self.battery_bar, status.battery_percent, self._battery_color(status.battery_percent))
        
        # Voltage
        self.voltage_label = tk.Label(content, text="", bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 8))
        self.voltage_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Current
        self.current_label = tk.Label(content, text="", bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 8))
        self.current_label.pack(anchor=tk.W)
        
        # Temperature - macOS-style progressbar
        self.temp_bar = self._create_metric_bar(content, "Temp", status.temperature_c, 20, 60)
        self._update_metric_bar(self.temp_bar, status.temperature_c, self._temperature_color(status.temperature_c))
        
        # Fan - macOS-style progressbar
        self.fan_bar = self._create_metric_bar(content, "Fan", status.fan_speed_rpm, 0, 3000)
        self._update_metric_bar(self.fan_bar, status.fan_speed_rpm, colors["accent_orange"])
        
        # LED - macOS-style progressbar
        self.led_bar = self._create_metric_bar(content, "LED", status.led_brightness, 0, 100)
        self._update_metric_bar(self.led_bar, status.led_brightness, colors["accent_green"])
        
        # Uptime
        uptime_str = self._format_uptime(status.uptime_seconds) if status.uptime_seconds else "N/A"
        self.uptime_label = tk.Label(content, text=f"Uptime: {uptime_str}", bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 8))
        self.uptime_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Last update / Time to dead
        self.last_update_label = tk.Label(content, text="Last update: N/A", bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 7))
        self.last_update_label.pack(anchor=tk.W)
        
        self.ttd_label = tk.Label(content, text="Time to dead: N/A", bg=colors["bg_secondary"], fg="#aaaaaa", font=("System", 8, "bold"))
        self.ttd_label.pack(anchor=tk.W, pady=(1, 0))
        
        self._draw_status_led()
        self.update_time_to_dead()
    
    def _on_click(self, event):
        if self.on_click_callback:
            self.on_click_callback(self.beacon_id)
    
    def _create_metric_bar(self, parent, label, value, low, high):
        """Create a metric row with macOS-style progress bar that supports color coding"""
        container = tk.Frame(parent, bg=self.colors["bg_secondary"])
        container.pack(fill=tk.X, pady=3)
        
        # Label - white text
        tk.Label(
            container,
            text=label,
            bg=self.colors["bg_secondary"],
            fg="white",
            font=("System", 8),
            width=8,
            anchor=tk.W,
        ).pack(side=tk.LEFT)
        
        # Progress bar frame with value label
        bar_frame = tk.Frame(container, bg=self.colors["bg_secondary"])
        bar_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        
        # Canvas for macOS-style progress bar with color support
        canvas = tk.Canvas(
            bar_frame,
            width=180,
            height=12,
            bg=self.colors["bg_secondary"],
            highlightthickness=0,
            bd=0
        )
        canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Value label on the right
        value_label = tk.Label(
            bar_frame,
            text=self._format_percent(self._metric_to_percent(value, low, high)),
            bg=self.colors["bg_secondary"],
            fg="white",
            font=("System", 8, "bold"),
            width=6
        )
        value_label.pack(side=tk.LEFT, padx=(6, 0))
        
        # Initialize progress value
        percent = self._metric_to_percent(value, low, high)
        
        return {
            "canvas": canvas,
            "value_label": value_label,
            "low": low,
            "high": high,
        }

    def _update_metric_bar(self, bar, value, color):
        """Update macOS-style progressbar with color"""
        if not bar:
            return
        
        canvas = bar["canvas"]
        value_label = bar["value_label"]
        
        percent = self._metric_to_percent(value, bar["low"], bar["high"])
        
        if percent is None:
            percent = 0
            value_label.config(text="N/A")
        else:
            percent = max(0, min(100, percent))
            value_label.config(text=self._format_percent(percent))
        
        # Redraw the progress bar with the given color
        self._draw_macos_progress(canvas, percent, color)

    def _draw_macos_progress(self, canvas, percent, color):
        """Draw a macOS-style progress bar on canvas with rounded ends"""
        canvas.delete("all")
        width = 180
        height = 12
        padding = 1
        
        # Track background (subtle)
        track_color = "#2a2a2a" if self.colors.get("bg_primary", "").startswith("#1") else "#e0e0e0"
        self._draw_rounded_rect(canvas, padding, padding, width - padding, height - padding, 
                                radius=6, fill=track_color, outline=track_color)
        
        if percent > 0:
            fill_width = max(2, int((width - 2 * padding) * percent / 100))
            # Draw filled portion with rounded left end
            self._draw_rounded_fill(canvas, padding, padding, padding + fill_width, height - padding, 6, color)

    def _draw_rounded_rect(self, canvas, x1, y1, x2, y2, radius, fill, outline):
        """Draw a rounded rectangle on canvas"""
        canvas.create_arc(x1, y1, x1 + 2*radius, y1 + 2*radius, start=90, extent=90, fill=fill, outline=outline)
        canvas.create_arc(x2 - 2*radius, y1, x2, y1 + 2*radius, start=0, extent=90, fill=fill, outline=outline)
        canvas.create_arc(x1, y2 - 2*radius, x1 + 2*radius, y2, start=180, extent=90, fill=fill, outline=outline)
        canvas.create_arc(x2 - 2*radius, y2 - 2*radius, x2, y2, start=270, extent=90, fill=fill, outline=outline)
        canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline=outline)
        canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline=outline)
    
    def _draw_rounded_fill(self, canvas, x1, y1, x2, y2, radius, color):
        """Draw a rectangle with rounded left corners for progress fill"""
        if x2 - x1 <= radius * 2:
            # Too narrow for full rounding, draw as capsule
            canvas.create_oval(x1, y1, x2, y2, fill=color, outline=color)
        else:
            # Left rounded cap
            canvas.create_arc(x1, y1, x1 + 2*radius, y2, start=90, extent=180, fill=color, outline=color)
            # Right square end
            canvas.create_rectangle(x1 + radius, y1, x2, y2, fill=color, outline=color)
            # Middle connector
            canvas.create_rectangle(x1, y1, x1 + radius, y2, fill=color, outline=color)
    
    @staticmethod
    def _metric_to_percent(value: Optional[float], low: float, high: float) -> Optional[float]:
        if value is None:
            return None
        if high <= low:
            return None
        clamped = max(low, min(high, float(value)))
        return ((clamped - low) / (high - low)) * 100.0
    
    def _battery_color(self, battery_percent: Optional[float]) -> str:
        if battery_percent is None:
            return self.colors["accent_orange"]
        if battery_percent < 20:
            return self.colors["accent_red"]
        if battery_percent < 50:
            return self.colors["accent_orange"]
        return self.colors["accent_green"]
    
    def _temperature_color(self, temperature_c: Optional[float]) -> str:
        if temperature_c is None:
            return self.colors["accent_orange"]
        if temperature_c >= 55:
            return self.colors["accent_red"]
        if temperature_c >= 45:
            return "#e6c200"
        return self.colors["accent_green"]
    
    @staticmethod
    def _format_percent(percent: Optional[float]) -> str:
        if percent is None:
            return "N/A"
        return f"{percent:.0f}%"
    
    def _draw_status_led(self):
        color = "#00ff00" if self.status.online else "#ff4444"
        self.status_led.delete("all")
        self.status_led.create_oval(2, 2, 12, 12, fill=color, outline=color)
        if self.status.online:
            self.status_led.create_oval(4, 4, 10, 10, fill="#ffffff", outline=color)
    
    @staticmethod
    def _format_uptime(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds//60}m"
        elif seconds < 86400:
            return f"{seconds//3600}h"
        else:
            return f"{seconds//86400}d"
    
    def update_from_status(self, status: BeaconStatus):
        self.status = status
        
        # Update header
        self.name_label.config(text=status.display_name or self.beacon.display_name)
        
        is_online = status.online
        self.status_text.config(text="ONLINE" if is_online else "OFFLINE",
                                fg=self.colors["accent_green"] if is_online else self.colors["accent_red"])
        
        # Update metric bars
        self._update_metric_bar(self.battery_bar, status.battery_percent, self._battery_color(status.battery_percent))
        self._update_metric_bar(self.temp_bar, status.temperature_c, self._temperature_color(status.temperature_c))
        self._update_metric_bar(self.fan_bar, status.fan_speed_rpm, self.colors["accent_orange"])
        self._update_metric_bar(self.led_bar, status.led_brightness, self.colors["accent_green"])
        
        # Update labels
        self.voltage_label.config(text=f"Voltage: {status.battery_voltage:.1f}V" if status.battery_voltage else "Voltage: --")
        self.current_label.config(text=f"Current: {status.current_amperage:.2f}A" if status.current_amperage else "Current: --")
        
        uptime_str = self._format_uptime(status.uptime_seconds) if status.uptime_seconds else "N/A"
        self.uptime_label.config(text=f"Uptime: {uptime_str}")
        
        self._draw_status_led()
        self.update_time_to_dead()
    
    def update_time_to_dead(self):
        if self.status.last_update is None:
            self.last_update_label.config(text="Last update: N/A")
            self.ttd_label.config(text="Time to dead: N/A", fg=self.colors["accent_red"])
            return
        
        age = time.time() - self.status.last_update
        if age < 60:
            age_str = f"{age:.1f}s ago"
        else:
            age_str = f"{age/60:.1f}m ago"
        self.last_update_label.config(text=f"Last update: {age_str}")
        
        remaining = max(0.0, 2.0 - age)
        if remaining <= 0.25:
            ttd_color = self.colors["accent_red"]
        elif remaining <= 0.75:
            ttd_color = self.colors["accent_orange"]
        else:
            ttd_color = self.colors["accent_green"]
        
        cadence = 1.0
        self.ttd_label.config(text=f"Time to dead: {remaining:.2f}s (cadence ~{cadence:.2f}s)", fg=ttd_color)


class BeaconConfigGUI:
    """Beacon configuration and monitoring interface with tabbed layout"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Beacon Configurator & Live Monitor")
        self.root.geometry("1200x800")
        self.root.configure(bg="SystemButtonFace")
        
        # Use native OS theme
        style = ttk.Style()
        set_native_theme(style)
        
        self.beacons: Dict[str, BeaconSettings] = {}
        self.beacon_status: Dict[str, BeaconStatus] = {}
        self.discovery_config: Dict[str, Any] = {}
        self.config_file = PROJECT_ROOT / "config" / "beacons_config.json"
        self.monitoring_active = False
        self.update_thread: Optional[threading.Thread] = None
        self.demo_active = False
        self.demo_thread: Optional[threading.Thread] = None
        self._demo_start_time = time.time()
        
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
                    self.discovery_config = dict(data.get("discovery", {}))
                    for beacon_id, config in data.get('beacons', {}).items():
                        self.beacons[beacon_id] = BeaconSettings(**config)
                        self.beacon_status[beacon_id] = BeaconStatus(beacon_id=beacon_id)
                logger.info(f"Loaded {len(self.beacons)} beacons from config")
            except Exception as e:
                logger.error(f"Error loading beacon config: {e}")
        
        if not self.beacons:
            self._create_default_beacons()
        self.discovery_config.setdefault("enabled", True)
        self.discovery_config.setdefault("udp_port", 4210)
        self.discovery_config.setdefault("http_ports", [5000, 80])
        self.discovery_config.setdefault("timeout_seconds", 0.25)
        self.discovery_config.setdefault("max_hosts", 254)
    
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
                },
                'discovery': self.discovery_config,
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
        colors = get_adaptive_colors()
        
        style.configure('Title.TLabel', font=('Arial', 14, 'bold'), foreground='#1a1a1a')
        style.configure('Subtitle.TLabel', font=('Arial', 11, 'bold'), foreground='#2c3e50')
        style.configure('Status.TLabel', font=('Arial', 9), foreground='#34495e')
        style.configure('Success.TLabel', font=('Arial', 9), foreground=colors['accent_green'])
        style.configure('Warning.TLabel', font=('Arial', 9), foreground=colors['accent_orange'])
        style.configure('Error.TLabel', font=('Arial', 9), foreground=colors['accent_red'])
        style.configure('Card.TLabelframe', background=colors['bg_secondary'])
        style.configure('Card.TLabelframe.Label', font=('Arial', 10, 'bold'), foreground=colors['fg_primary'])
    
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
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Flash Beacon (Xiao ESP32-C6)", command=self._open_beacon_flasher)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)
    
    def _open_beacon_flasher(self):
        from control.beacon_config_gui import BeaconFlashWindow
        BeaconFlashWindow(self).show()
    
    def create_widgets(self):
        """Create main GUI layout with tabs"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title bar with demo mode toggle
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        title_frame.columnconfigure(0, weight=1)
        
        colors = get_adaptive_colors()
        title = tk.Label(title_frame, text="Beacon Configurator & Live Monitor", bg=colors["bg_primary"], fg="white", font=("System", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")
        
        self.demo_mode_var = tk.BooleanVar(value=False)
        demo_check = ttk.Checkbutton(
            title_frame,
            text="Demo Mode (Simulated Data)",
            variable=self.demo_mode_var,
            command=self.toggle_demo_mode
        )
        demo_check.grid(row=0, column=1, sticky="e", padx=10)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        
        # Tab 1: Live Monitor (at-a-glance like Shure WWB)
        self.live_monitor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.live_monitor_frame, text="Live Monitor")
        self.create_live_monitor_tab(self.live_monitor_frame)
        
        # Tab 2: Configuration (per-beacon settings)
        self.config_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.config_frame, text="Configuration")
        self.create_config_tab(self.config_frame)
        
        # Tab 3: Beacon Manager (add/remove/rename)
        self.manage_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.manage_frame, text="Beacon Manager")
        self.create_manage_tab(self.manage_frame)
    
    # ========== LIVE MONITOR TAB ==========
    
    def create_live_monitor_tab(self, parent):
        """Create Live Monitor tab - at-a-glance view like Shure WWB"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Header with summary stats
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(0, weight=1)
        
        colors = get_adaptive_colors()
        title_lbl = tk.Label(header_frame, text="Live Monitor", bg=colors["bg_primary"], fg="white", font=("System", 16, "bold"))
        title_lbl.grid(row=0, column=0, sticky="w")
        
        # Summary stats
        stats_frame = ttk.Frame(header_frame)
        stats_frame.grid(row=0, column=1, sticky="e")
        
        self.summary_labels = {}
        for i, (label, key) in enumerate([
            ("Online", "online_count"),
            ("Low Battery", "low_batt_count"),
            ("High Temp", "high_temp_count"),
            ("Total", "total_count"),
        ]):
            frame = tk.Frame(stats_frame, bg=colors["bg_primary"])
            frame.grid(row=0, column=i, padx=10)
            tk.Label(frame, text=label, bg=colors["bg_primary"], fg="white", font=("System", 8)).grid(row=0, column=0)
            lbl = tk.Label(frame, text="0", bg=colors["bg_primary"], fg="white", font=("System", 14, "bold"))
            lbl.grid(row=1, column=0)
            self.summary_labels[key] = lbl
        
        # Beacon grid - scrollable
        canvas = tk.Canvas(parent, highlightthickness=0, bg=colors["bg_primary"])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.beacon_grid_frame = tk.Frame(canvas, bg=colors["bg_primary"])
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        
        canvas_window = canvas.create_window((0, 0), window=self.beacon_grid_frame, anchor="nw")
        
        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)
        
        self.beacon_grid_frame.bind("<Configure>", configure_scroll)
        canvas.bind("<Configure>", configure_scroll)
        
        parent.canvas = canvas
        parent.scrollbar = scrollbar
        
        # Store card references for efficient updates
        self._beacon_cards = {}
        
        # Initial populate
        self.update_live_monitor()
    
    def update_live_monitor(self):
        """Update the live monitor grid with current beacon status"""
        colors = get_adaptive_colors()
        
        # Update summary stats
        online_count = sum(1 for s in self.beacon_status.values() if s.online)
        low_batt_count = sum(1 for s in self.beacon_status.values() 
                            if s.battery_percent is not None and s.battery_percent < 20)
        high_temp_count = sum(1 for s in self.beacon_status.values() 
                             if s.temperature_c is not None and s.temperature_c > 55)
        total_count = len(self.beacons)
        
        self.summary_labels["online_count"].config(text=str(online_count), 
            foreground='#27ae60' if online_count == total_count else '#f39c12')
        self.summary_labels["low_batt_count"].config(text=str(low_batt_count),
            foreground='#e74c3c' if low_batt_count > 0 else '#27ae60')
        self.summary_labels["high_temp_count"].config(text=str(high_temp_count),
            foreground='#e74c3c' if high_temp_count > 0 else '#27ae60')
        self.summary_labels["total_count"].config(text=str(total_count))
        
        # Create or update beacon cards
        row = 0
        col = 0
        max_cols = 4
        
        for beacon_id, beacon in self.beacons.items():
            status = self.beacon_status[beacon_id]
            
            if beacon_id in self._beacon_cards:
                # Update existing card
                self._beacon_cards[beacon_id].update_from_status(status)
            else:
                # Create new card
                card = BeaconCard(self.beacon_grid_frame, beacon_id, beacon, status, colors,
                                on_click_callback=self.on_card_click)
                self._beacon_cards[beacon_id] = card
                card.frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # Remove cards for beacons that no longer exist
        for beacon_id in list(self._beacon_cards.keys()):
            if beacon_id not in self.beacons:
                self._beacon_cards[beacon_id].frame.destroy()
                del self._beacon_cards[beacon_id]
        
        # Configure grid weights
        for i in range(max_cols):
            self.beacon_grid_frame.columnconfigure(i, weight=1)
    
    def on_card_click(self, beacon_id: str):
        """Switch to Configuration tab and select this beacon"""
        self.notebook.select(self.config_frame)
        if beacon_id in self.beacons:
            idx = list(self.beacons.keys()).index(beacon_id)
            self.config_beacon_listbox.selection_clear(0, tk.END)
            self.config_beacon_listbox.selection_set(idx)
            self.on_config_beacon_selected()
    
    # ========== CONFIGURATION TAB ==========
    
    def create_config_tab(self, parent):
        """Create Configuration tab - per-beacon settings"""
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        
        # Left: Beacon selector
        left_frame = ttk.LabelFrame(parent, text="Select Beacon", padding="10")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)
        
        self.config_beacon_var = tk.Variable(value=())
        self.config_beacon_listbox = tk.Listbox(left_frame, listvariable=self.config_beacon_var, height=15)
        self.config_beacon_listbox.grid(row=0, column=0, sticky="nsew")
        self.config_beacon_listbox.bind("<<ListboxSelect>>", self.on_config_beacon_selected)
        
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btn_frame.columnconfigure((0, 1, 2), weight=1)
        
        ttk.Button(btn_frame, text="Add", command=self.add_beacon_dialog).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="Remove", command=self.remove_beacon).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_config_list).grid(row=0, column=2, sticky="ew", padx=2)
        
        # Right: Configuration panels
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        self.config_notebook = ttk.Notebook(right_frame)
        self.config_notebook.grid(row=0, column=0, sticky="nsew")
        
        # Fan tab
        fan_frame = ttk.Frame(self.config_notebook, padding="10")
        self.config_notebook.add(fan_frame, text="Fan Control")
        self.create_fan_config(fan_frame)
        
        # LED tab
        led_frame = ttk.Frame(self.config_notebook, padding="10")
        self.config_notebook.add(led_frame, text="LED Control")
        self.create_led_config(led_frame)
        
        # Power tab
        power_frame = ttk.Frame(self.config_notebook, padding="10")
        self.config_notebook.add(power_frame, text="Power")
        self.create_power_config(power_frame)
        
        # Network tab
        net_frame = ttk.Frame(self.config_notebook, padding="10")
        self.config_notebook.add(net_frame, text="Network")
        self.create_network_config(net_frame)
        
        # Apply button
        ttk.Button(right_frame, text="Apply Settings to Beacon", command=self.apply_settings).grid(
            row=1, column=0, sticky="ew", pady=(10, 0))
        
        self.refresh_config_list()
    
    def create_fan_config(self, parent):
        row = 0
        
        self.fan_auto_var = tk.BooleanVar(value=True)
        auto_check = ttk.Checkbutton(
            parent,
            text="Automatic Fan (temperature-driven)",
            variable=self.fan_auto_var,
            command=self._update_fan_controls_state,
        )
        auto_check.grid(row=row, column=0, columnspan=3, sticky="w", pady=5)
        row += 1
        
        ttk.Label(parent, text="Fan Speed (PWM 0-255):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_speed_var = tk.IntVar(value=100)
        self.fan_scale = ttk.Scale(parent, from_=0, to=255, orient=tk.HORIZONTAL, variable=self.fan_speed_var)
        self.fan_scale.grid(row=row, column=1, sticky="ew", padx=(10, 5))
        self.fan_speed_label = ttk.Label(parent, text="100", width=4)
        self.fan_speed_label.grid(row=row, column=2)
        self.fan_speed_var.trace_add(
            "write",
            lambda *_: self.fan_speed_label.config(text=str(self.fan_speed_var.get())),
        )
        row += 1
        
        ttk.Label(parent, text="Fan Ramp Start Temp (°C):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_temp_start_var = tk.DoubleVar(value=40.0)
        ttk.Spinbox(parent, from_=0, to=90, increment=0.5, textvariable=self.fan_temp_start_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Fan Full Speed Temp (°C):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_temp_full_var = tk.DoubleVar(value=55.0)
        ttk.Spinbox(parent, from_=0, to=100, increment=0.5, textvariable=self.fan_temp_full_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Fan Min PWM (auto):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_min_pwm_var = tk.IntVar(value=80)
        ttk.Spinbox(parent, from_=0, to=255, textvariable=self.fan_min_pwm_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Fan Max PWM (auto):").grid(row=row, column=0, sticky="w", pady=5)
        self.fan_max_pwm_var = tk.IntVar(value=255)
        ttk.Spinbox(parent, from_=0, to=255, textvariable=self.fan_max_pwm_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        parent.columnconfigure(1, weight=1)
    
    def create_led_config(self, parent):
        row = 0
        
        ttk.Label(parent, text="LED Duty Cycle (0-100%):").grid(row=row, column=0, sticky="w", pady=5)
        self.led_duty_var = tk.IntVar(value=100)
        led_scale = ttk.Scale(parent, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.led_duty_var)
        led_scale.grid(row=row, column=1, sticky="ew", padx=(10, 5))
        self.led_duty_label = ttk.Label(parent, text="100%", width=4)
        self.led_duty_label.grid(row=row, column=2)
        self.led_duty_var.trace_add(
            "write",
            lambda *_: self.led_duty_label.config(text=f"{self.led_duty_var.get()}%"),
        )
        row += 1
        
        self.led_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="LED Enabled", variable=self.led_enabled_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=10)
        row += 1
        
        parent.columnconfigure(1, weight=1)
    
    def create_power_config(self, parent):
        row = 0
        
        ttk.Label(parent, text="Battery Low Threshold (%):").grid(row=row, column=0, sticky="w", pady=5)
        self.battery_threshold_var = tk.IntVar(value=20)
        ttk.Spinbox(parent, from_=1, to=50, textvariable=self.battery_threshold_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Amperage Limit (A):").grid(row=row, column=0, sticky="w", pady=5)
        self.amperage_limit_var = tk.DoubleVar(value=5.0)
        ttk.Spinbox(parent, from_=0.1, to=20.0, increment=0.1, textvariable=self.amperage_limit_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Nominal Voltage (V):").grid(row=row, column=0, sticky="w", pady=5)
        self.voltage_nominal_var = tk.DoubleVar(value=12.0)
        ttk.Spinbox(parent, from_=5.0, to=24.0, increment=0.1, textvariable=self.voltage_nominal_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        parent.columnconfigure(1, weight=1)
    
    def create_network_config(self, parent):
        row = 0
        
        ttk.Label(parent, text="Beacon ID:").grid(row=row, column=0, sticky="w", pady=5)
        self.config_beacon_id_var = tk.StringVar()
        self.config_beacon_id_entry = ttk.Entry(parent, textvariable=self.config_beacon_id_var, width=30, state="readonly")
        self.config_beacon_id_entry.grid(row=row, column=1, sticky="ew", padx=10)
        row += 1
        
        ttk.Label(parent, text="IP Address:").grid(row=row, column=0, sticky="w", pady=5)
        self.config_ip_var = tk.StringVar()
        self.config_ip_entry = ttk.Entry(parent, textvariable=self.config_ip_var, width=30)
        self.config_ip_entry.grid(row=row, column=1, sticky="ew", padx=10)
        row += 1
        
        ttk.Label(parent, text="Port:").grid(row=row, column=0, sticky="w", pady=5)
        self.config_port_var = tk.IntVar(value=5000)
        ttk.Spinbox(parent, from_=1, to=65535, textvariable=self.config_port_var, width=10).grid(row=row, column=1, sticky="w", padx=10)
        row += 1
        
        ttk.Label(parent, text="Display Name:").grid(row=row, column=0, sticky="w", pady=5)
        self.config_name_var = tk.StringVar()
        self.config_name_entry = ttk.Entry(parent, textvariable=self.config_name_var, width=30)
        self.config_name_entry.grid(row=row, column=1, sticky="ew", padx=10)
        row += 1
        
        ttk.Button(parent, text="Update Name on Beacon", command=self.rename_beacon).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=10)
        
        parent.columnconfigure(1, weight=1)
    
    def on_config_beacon_selected(self, event=None):
        selection = self.config_beacon_listbox.curselection()
        if not selection:
            return
        beacon_id = self.config_beacon_listbox.get(selection[0])
        if beacon_id in self.beacons:
            beacon = self.beacons[beacon_id]
            status = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id))
            
            self.fan_auto_var.set(beacon.fan_auto)
            self.fan_speed_var.set(beacon.fan_speed_pwm)
            self.fan_temp_start_var.set(beacon.fan_temp_start)
            self.fan_temp_full_var.set(beacon.fan_temp_full)
            self.fan_min_pwm_var.set(beacon.fan_min_pwm)
            self.fan_max_pwm_var.set(beacon.fan_max_pwm)
            self.led_duty_var.set(beacon.led_duty_cycle)
            self.led_enabled_var.set(beacon.led_duty_cycle > 0)
            self.battery_threshold_var.set(int(beacon.battery_low_threshold))
            self.amperage_limit_var.set(beacon.amperage_limit)
            self.voltage_nominal_var.set(beacon.voltage_nominal)
            
            self.config_beacon_id_var.set(beacon.beacon_id)
            self.config_ip_var.set(beacon.ip_address)
            self.config_port_var.set(beacon.port)
            self.config_name_var.set(status.display_name or beacon.display_name)
            
            self._update_fan_controls_state()
    
    def refresh_config_list(self):
        beacon_list = list(self.beacons.keys())
        self.config_beacon_var.set(tuple(beacon_list))
        if beacon_list and not self.config_beacon_listbox.curselection():
            self.config_beacon_listbox.selection_set(0)
            self.on_config_beacon_selected()
    
    # ========== BEACON MANAGER TAB ==========
    
    def create_manage_tab(self, parent):
        """Create Beacon Manager tab - bulk operations"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Button(toolbar, text="Add Beacon", command=self.add_beacon_dialog).grid(row=0, column=0, padx=5)
        ttk.Button(toolbar, text="Remove Selected", command=self.remove_beacon).grid(row=0, column=1, padx=5)
        ttk.Button(toolbar, text="Save Config", command=self.save_config).grid(row=0, column=2, padx=5)
        ttk.Button(toolbar, text="Load Config", command=self.load_config_dialog).grid(row=0, column=3, padx=5)
        ttk.Separator(toolbar, orient="vertical").grid(row=0, column=4, padx=10, sticky="ns")
        ttk.Button(toolbar, text="Test All Connections", command=self.test_all_connections).grid(row=0, column=5, padx=5)
        ttk.Button(toolbar, text="Discover Beacons", command=self.discover_beacons).grid(row=0, column=6, padx=5)
        
        # Beacon table
        table_frame = ttk.Frame(parent)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        columns = ("ID", "Name", "IP Address", "Port", "Status", "Battery", "Temp", "Fan", "LED")
        self.beacon_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.beacon_tree.heading(col, text=col)
            self.beacon_tree.column(col, width=100, anchor="center")
        
        self.beacon_tree.column("ID", width=120)
        self.beacon_tree.column("Name", width=150)
        self.beacon_tree.column("IP Address", width=130)
        self.beacon_tree.column("Status", width=100)
        
        v_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.beacon_tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.beacon_tree.xview)
        self.beacon_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        self.beacon_tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        self.beacon_tree.bind("<Double-1>", self.on_tree_double_click)
        
        # Context menu
        self.tree_menu = tk.Menu(parent, tearoff=0)
        self.tree_menu.add_command(label="Edit", command=self.edit_selected_beacon)
        self.tree_menu.add_command(label="Remove", command=self.remove_beacon)
        self.tree_menu.add_separator()
        self.tree_menu.add_command(label="Test Connection", command=self.test_selected_connection)
        self.tree_menu.add_command(label="Rename", command=self.rename_beacon)
        self.beacon_tree.bind("<Button-3>", self.show_tree_menu)
        
        self.refresh_beacon_table()
    
    def refresh_beacon_table(self):
        for item in self.beacon_tree.get_children():
            self.beacon_tree.delete(item)
        
        for beacon_id, beacon in self.beacons.items():
            status = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id))
            
            conn_status = "● Online" if status.online else "○ Offline"
            batt_text = f"{status.battery_percent:.0f}%" if status.battery_percent else "--"
            temp_text = f"{status.temperature_c:.0f}°C" if status.temperature_c else "--"
            fan_text = f"{status.fan_speed_rpm} RPM" if status.fan_speed_rpm else "--"
            led_text = f"{status.led_brightness}%" if status.led_brightness else "--"
            
            self.beacon_tree.insert("", "end", values=(
                beacon_id,
                status.display_name or beacon.display_name,
                f"{beacon.ip_address}:{beacon.port}",
                beacon.port,
                conn_status,
                batt_text,
                temp_text,
                fan_text,
                led_text
            ), tags=(beacon_id,))
        
        self.beacon_tree.tag_configure("online", foreground="#27ae60")
        self.beacon_tree.tag_configure("offline", foreground="#e74c3c")
    
    def show_tree_menu(self, event):
        item = self.beacon_tree.identify_row(event.y)
        if item:
            self.beacon_tree.selection_set(item)
            self.tree_menu.post(event.x_root, event.y_root)
    
    def get_selected_beacon_id(self) -> Optional[str]:
        selection = self.beacon_tree.selection()
        if selection:
            return self.beacon_tree.item(selection[0])["values"][0]
        return None
    
    def edit_selected_beacon(self):
        beacon_id = self.get_selected_beacon_id()
        if beacon_id:
            self.notebook.select(self.config_frame)
            idx = list(self.beacons.keys()).index(beacon_id)
            self.config_beacon_listbox.selection_clear(0, tk.END)
            self.config_beacon_listbox.selection_set(idx)
            self.on_config_beacon_selected()
    
    def test_selected_connection(self):
        beacon_id = self.get_selected_beacon_id()
        if beacon_id and beacon_id in self.beacons:
            beacon = self.beacons[beacon_id]
            try:
                payload = fetch_status(beacon, timeout=3.0)
                self._apply_payload(beacon_id, payload)
                self.refresh_beacon_table()
                self.update_live_monitor()
                messagebox.showinfo("Success", f"Connected to {beacon_id}")
            except Exception as exc:
                logger.error(f"Failed to reach {beacon_id}: {exc}")
                messagebox.showerror("Error", f"Unable to reach {beacon_id}: {exc}")
    
    def test_all_connections(self):
        for beacon_id, beacon in self.beacons.items():
            try:
                payload = fetch_status(beacon, timeout=2.0)
                self._apply_payload(beacon_id, payload)
            except Exception:
                pass
        self.refresh_beacon_table()
        self.update_live_monitor()
        messagebox.showinfo("Done", "Connection test complete")
    
    def discover_beacons(self):
        discovery = self.discovery_config
        try:
            found = discover_beacons(
                discovery.get("network"),
                ports=tuple(discovery.get("http_ports", [5000, 80])),
                udp_port=int(discovery.get("udp_port", 4210)),
                timeout=float(discovery.get("timeout_seconds", 0.25)),
                max_hosts=int(discovery.get("max_hosts", 254)),
            )
        except Exception as exc:
            logger.exception("Beacon discovery failed")
            messagebox.showerror("Discovery failed", str(exc))
            return

        added = 0
        updated = 0
        for item in found:
            beacon_id = str(item["beacon_id"])
            address = str(item["ip_address"])
            port = int(item.get("port", 80))
            existing = self.beacons.get(beacon_id)
            if existing is None:
                self.beacons[beacon_id] = BeaconSettings(
                    beacon_id=beacon_id,
                    ip_address=address,
                    port=port,
                    display_name=str(item.get("status", {}).get("name", "Beacon")),
                )
                self.beacon_status[beacon_id] = BeaconStatus(beacon_id=beacon_id)
                added += 1
            elif existing.ip_address != address or existing.port != port:
                existing.ip_address = address
                existing.port = port
                updated += 1

        self.refresh_config_list()
        self.refresh_beacon_table()
        self.update_live_monitor()
        messagebox.showinfo("Discovery complete", f"Found {len(found)} beacon(s): {added} added, {updated} updated.")
    
    def on_tree_double_click(self, event):
        self.edit_selected_beacon()
    
    # ========== COMMON METHODS ==========
    
    def _update_fan_controls_state(self):
        manual_enabled = not self.fan_auto_var.get()
        if manual_enabled:
            self.fan_scale.state(["!disabled"])
        else:
            self.fan_scale.state(["disabled"])
    
    def toggle_demo_mode(self):
        if self.demo_mode_var.get():
            self.start_demo_mode()
        else:
            self.stop_demo_mode()
    
    def start_demo_mode(self):
        self.demo_active = True
        self.demo_thread = threading.Thread(target=self._demo_loop, daemon=True)
        self.demo_thread.start()
        for beacon_id in self.beacons:
            self._generate_demo_status(beacon_id)
        self.update_live_monitor()
    
    def stop_demo_mode(self):
        self.demo_active = False
        if hasattr(self, 'demo_thread'):
            self.demo_thread.join(timeout=1.0)
    
    def _demo_loop(self):
        import random
        while self.demo_active:
            for beacon_id in self.beacons:
                self._generate_demo_status(beacon_id)
            try:
                self.root.after(0, self.update_live_monitor)
            except RuntimeError:
                break
            time.sleep(1.0)
    
    def _generate_demo_status(self, beacon_id: str):
        import random
        status = self.beacon_status[beacon_id]
        beacon = self.beacons[beacon_id]
        
        status.online = True
        status.status_message = "OK (Demo)"
        status.last_update = time.time()
        
        current_batt = status.battery_percent if status.battery_percent is not None else 85.0
        status.battery_percent = max(5.0, current_batt - random.uniform(0.0, 0.1))
        
        status.battery_voltage = 12.0 * (status.battery_percent / 100.0) + random.uniform(-0.2, 0.2)
        status.current_amperage = random.uniform(0.5, 3.5)
        
        base_temp = 35.0 + (100 - status.battery_percent) * 0.2
        status.temperature_c = base_temp + random.uniform(-2.0, 3.0)
        
        if beacon.fan_auto:
            status.fan_speed_rpm = int(self._compute_auto_fan_pwm(beacon, status.temperature_c) * 10)
        else:
            status.fan_speed_rpm = int(beacon.fan_speed_pwm * 10)
        
        status.led_brightness = beacon.led_duty_cycle
        status.uptime_seconds = int(time.time() - self._demo_start_time)
        status.display_name = beacon.display_name
    
    def refresh_beacon_list(self):
        """Refresh beacon lists in all tabs"""
        beacon_list = list(self.beacons.keys())
        
        # Update live monitor
        self.update_live_monitor()
        
        # Update config tab
        if hasattr(self, 'config_beacon_var'):
            self.config_beacon_var.set(tuple(beacon_list))
        
        # Update manage tab
        if hasattr(self, 'beacon_tree'):
            self.refresh_beacon_table()
    
    def load_config_dialog(self):
        file_path = filedialog.askopenfilename(
            initialdir=str(self.config_file.parent),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.config_file = Path(file_path)
            self.load_config()
            self.refresh_beacon_list()
    
    def test_connection(self):
        beacon_id = self.notebook.index(self.notebook.select())
        if beacon_id != 2:  # Not on manage tab
            # Get selected from config tab
            selection = self.config_beacon_listbox.curselection()
            if selection:
                beacon_id = self.config_beacon_listbox.get(selection[0])
            else:
                return
        
        if beacon_id in self.beacons:
            beacon = self.beacons[beacon_id]
            try:
                payload = fetch_status(beacon, timeout=3.0)
                self._apply_payload(beacon_id, payload)
                self.update_live_monitor()
                self.refresh_beacon_table()
                messagebox.showinfo("Success", f"Connected to {beacon_id}")
            except Exception as exc:
                logger.error(f"Failed to reach {beacon_id}: {exc}")
                messagebox.showerror("Error", f"Unable to reach {beacon_id}: {exc}")
    
    def add_beacon_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Beacon")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
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
            
            if beacon_id in self.beacons:
                messagebox.showwarning("Warning", f"Beacon '{beacon_id}' already exists")
                return
            
            new_beacon = BeaconSettings(beacon_id=beacon_id, ip_address=ip, port=port)
            self.beacons[beacon_id] = new_beacon
            self.beacon_status[beacon_id] = BeaconStatus(beacon_id=beacon_id)
            
            self.save_config()
            dialog.destroy()
            self.refresh_beacon_list()
            
            idx = list(self.beacons.keys()).index(beacon_id)
            if hasattr(self, 'config_beacon_listbox'):
                self.config_beacon_listbox.selection_clear(0, tk.END)
                self.config_beacon_listbox.selection_set(idx)
                self.on_config_beacon_selected()
        
        ttk.Button(dialog, text="Add", command=save_beacon).grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=20)
        dialog.columnconfigure(1, weight=1)
        ensure_window_fits_content(dialog, min_width=400, min_height=200, center=True)
    
    def remove_beacon(self):
        beacon_id = None
        
        # Try config tab selection first
        if hasattr(self, 'config_beacon_listbox'):
            selection = self.config_beacon_listbox.curselection()
            if selection:
                beacon_id = self.config_beacon_listbox.get(selection[0])
        
        # Try manage tab
        if not beacon_id and hasattr(self, 'beacon_tree'):
            selection = self.beacon_tree.selection()
            if selection:
                beacon_id = self.beacon_tree.item(selection[0])["values"][0]
        
        if not beacon_id:
            messagebox.showwarning("Warning", "Please select a beacon to remove")
            return
        
        if messagebox.askyesno("Confirm", f"Remove beacon '{beacon_id}'?"):
            del self.beacons[beacon_id]
            if beacon_id in self.beacon_status:
                del self.beacon_status[beacon_id]
            self.save_config()
            self.refresh_beacon_list()
    
    def rename_beacon(self):
        beacon_id = None
        
        if hasattr(self, 'config_beacon_listbox'):
            selection = self.config_beacon_listbox.curselection()
            if selection:
                beacon_id = self.config_beacon_listbox.get(selection[0])
        
        if not beacon_id and hasattr(self, 'beacon_tree'):
            selection = self.beacon_tree.selection()
            if selection:
                beacon_id = self.beacon_tree.item(selection[0])["values"][0]
        
        if not beacon_id or beacon_id not in self.beacons:
            messagebox.showwarning("Warning", "Please select a beacon")
            return

        beacon = self.beacons[beacon_id]
        current = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id)).display_name or beacon.display_name
        name = simpledialog.askstring("Rename Beacon", "Display name to show on beacon:", initialvalue=current)
        if not name:
            return

        beacon.display_name = name
        try:
            push_name(beacon, name=name)
            if hasattr(self, 'config_name_var'):
                self.config_name_var.set(name)
            self.refresh_beacon_list()
            messagebox.showinfo("Success", f"Renamed {beacon_id} to '{name}'")
        except Exception as exc:
            logger.error(f"Failed to rename {beacon_id}: {exc}")
            messagebox.showerror("Error", f"Could not rename beacon: {exc}")
    
    def apply_settings(self):
        """Apply settings to selected beacon"""
        selection = self.config_beacon_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a beacon")
            return
        
        beacon_id = self.config_beacon_listbox.get(selection[0])
        if beacon_id not in self.beacons:
            return
        
        beacon = self.beacons[beacon_id]
        
        beacon.fan_auto = self.fan_auto_var.get()
        beacon.fan_speed_pwm = self.fan_speed_var.get()
        beacon.fan_temp_start = float(self.fan_temp_start_var.get())
        beacon.fan_temp_full = float(self.fan_temp_full_var.get())
        beacon.fan_min_pwm = int(self.fan_min_pwm_var.get())
        beacon.fan_max_pwm = int(self.fan_max_pwm_var.get())
        beacon.led_duty_cycle = self.led_duty_var.get()
        beacon.battery_low_threshold = float(self.battery_threshold_var.get())
        beacon.amperage_limit = self.amperage_limit_var.get()
        beacon.voltage_nominal = self.voltage_nominal_var.get()
        
        new_ip = self.config_ip_var.get().strip()
        new_port = self.config_port_var.get()
        new_name = self.config_name_var.get().strip()
        
        if new_ip != beacon.ip_address or new_port != beacon.port:
            beacon.ip_address = new_ip
            beacon.port = new_port
            self.save_config()
        
        if new_name:
            beacon.display_name = new_name
        
        try:
            push_config(
                beacon,
                brightness_pct=beacon.led_duty_cycle,
                led_on=beacon.led_duty_cycle > 0,
            )
            if new_name:
                push_name(beacon, name=new_name)
            logger.info(f"Pushed settings to {beacon_id}")
            messagebox.showinfo("Success", f"Settings applied to {beacon_id}")
        except Exception as exc:
            logger.error(f"Failed to push settings to {beacon_id}: {exc}")
            messagebox.showerror("Error", f"Could not send settings to {beacon_id}: {exc}")
    
    def start_monitoring(self):
        self.monitoring_active = True
        self.update_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.update_thread.start()
    
    def _monitoring_loop(self):
        while self.monitoring_active:
            if not self.demo_active:
                # Copy items to avoid "dictionary changed size during iteration" if beacons are added/removed
                beacon_items = list(self.beacons.items())
                for beacon_id, beacon in beacon_items:
                    if not self.monitoring_active:
                        break
                    if beacon_id not in self.beacon_status:
                        continue
                    status = self.beacon_status[beacon_id]
                    try:
                        payload = fetch_status(beacon, timeout=2.5)
                        self._apply_payload(beacon_id, payload)
                    except Exception as exc:
                        status.online = False
                        status.status_message = str(exc)
                        status.last_update = time.time()
                    time.sleep(beacon.poll_interval)
            else:
                time.sleep(1.0)
    
    def _apply_payload(self, beacon_id: str, payload: dict):
        status = self.beacon_status[beacon_id]
        status.online = True
        status.status_message = "OK"
        status.last_update = time.time()

        status.battery_voltage = payload.get("battery_v")
        status.battery_percent = payload.get("battery_pct")
        status.current_amperage = payload.get("current_a")
        status.fan_speed_rpm = payload.get("fan_rpm")
        status.led_brightness = payload.get("brightness_pct")
        status.temperature_c = payload.get("temp_c")
        status.uptime_seconds = payload.get("uptime_s")
        status.display_name = payload.get("name")
    
    def _compute_auto_fan_pwm(self, beacon: BeaconSettings, temperature_c: float) -> int:
        start = beacon.fan_temp_start
        full = beacon.fan_temp_full
        min_pwm = max(0, min(255, beacon.fan_min_pwm))
        max_pwm = max(min_pwm, min(255, beacon.fan_max_pwm))

        if full <= start:
            return max_pwm

        if temperature_c <= start:
            return min_pwm
        if temperature_c >= full:
            return max_pwm

        ratio = (temperature_c - start) / (full - start)
        pwm = int(round(min_pwm + ratio * (max_pwm - min_pwm)))
        return max(min_pwm, min(max_pwm, pwm))
    
    def show_about(self):
        messagebox.showinfo(
            "About Beacon Configurator & Live Monitor",
            "Beacon Configurator & Live Monitor v1.0\n\n"
            "Network-accessible interface for managing IR beacon hardware.\n"
            "Automatic fan control adjusts PWM from temperature, plus manual overrides.\n"
            "Control fan speed, LED duty cycles, and monitor battery/power status."
        )
    
    def on_closing(self):
        self.monitoring_active = False
        self.demo_active = False
        if self.update_thread:
            self.update_thread.join(timeout=1.0)
        if hasattr(self, 'demo_thread') and self.demo_thread:
            self.demo_thread.join(timeout=1.0)
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()


def main():
    app = BeaconConfigGUI()
    app.run()


if __name__ == "__main__":
    main()
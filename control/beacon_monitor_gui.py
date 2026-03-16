#!/usr/bin/env python3
"""
Graphical Beacon Monitor - Real-time Dashboard
Displays multiple beacons with visual status indicators, battery levels, 
fan speeds, temperatures, and LED states. Designed for quick glance monitoring
of entire beacon array during live operation.
"""

import tkinter as tk
from tkinter import ttk
import json
import logging
import threading
import time
import platform
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import random
import math
import sys

logger = logging.getLogger("beacon_monitor_gui")
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
        if system == "Darwin":  # macOS
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
        """Detect system appearance (light/dark mode)."""
        import subprocess
        system = platform.system()
        if system == "Darwin":
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
        """Get color scheme that adapts to system appearance."""
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
class BeaconStatus:
    """Real-time beacon status"""
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
    ip_address: str = "0.0.0.0"
    port: int = 5000

class BeaconCard:
    """Visual beacon status card"""
    
    def __init__(self, parent: tk.Frame, beacon_id: str, status: BeaconStatus, colors: dict):
        self.beacon_id = beacon_id
        self.status = status
        self.colors = colors
        self.frame = tk.Frame(parent, bg=colors["bg_secondary"], relief=tk.RAISED, borderwidth=1)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Header with ID and status indicator
        header = tk.Frame(self.frame, bg=colors["bg_secondary"], height=35)
        header.pack(fill=tk.X, padx=1, pady=1)
        header.pack_propagate(False)
        
        # Status LED (online/offline indicator)
        self.status_led = tk.Canvas(header, width=12, height=12, bg=colors["bg_secondary"], highlightthickness=0)
        self.status_led.pack(side=tk.LEFT, padx=8, pady=11)
        
        # Beacon ID label
        id_label = tk.Label(
            header,
            text=f"{beacon_id}",
            bg=colors["bg_secondary"],
            fg=colors["accent_green"] if status.online else colors["accent_red"],
            font=("System", 12, "bold")
        )
        id_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Status text
        self.status_text = tk.Label(
            header,
            text="OFFLINE" if not status.online else "ONLINE",
            bg=colors["bg_secondary"],
            fg=colors["accent_red"] if not status.online else colors["accent_green"],
            font=("System", 9, "bold")
        )
        self.status_text.pack(side=tk.RIGHT, padx=8)
        
        # Content area
        content = tk.Frame(self.frame, bg=colors["bg_secondary"])
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # IP and Port info
        info_text = f"{status.ip_address}:{status.port}"
        tk.Label(content, text=info_text, bg=colors["bg_secondary"], fg=colors["fg_secondary"], font=("System", 8)).pack(anchor=tk.W)
        
        # Battery section
        battery_color = colors["accent_red"] if status.battery_percent and status.battery_percent < 20 else colors["accent_orange"] if status.battery_percent and status.battery_percent < 50 else colors["accent_green"]
        self._create_metric_row(content, "Battery", status.battery_percent, "%", battery_color)
        
        # Voltage section
        self._create_metric_row(content, "Voltage", status.battery_voltage, "V", colors["accent_green"])
        
        # Amperage section
        self._create_metric_row(content, "Current", status.current_amperage, "A", colors["accent_green"])
        
        # Fan section
        self._create_metric_row(content, "Fan Speed", status.fan_speed_rpm, "RPM", colors["accent_orange"])
        
        # Temperature section
        temp_color = colors["accent_red"] if status.temperature_c and status.temperature_c > 50 else colors["accent_orange"] if status.temperature_c and status.temperature_c > 40 else colors["accent_green"]
        self._create_metric_row(content, "Temperature", status.temperature_c, "C", temp_color)
        
        # LED brightness section
        self._create_metric_row(content, "LED Brightness", status.led_brightness, "%", colors["accent_orange"])
        
        # Uptime section
        uptime_str = self._format_uptime(status.uptime_seconds) if status.uptime_seconds else "N/A"
        tk.Label(content, text=f"Uptime: {uptime_str}", bg=colors["bg_secondary"], fg=colors["fg_secondary"], font=("System", 8)).pack(anchor=tk.W, pady=2)
        
        # Last update time
        if status.last_update:
            last_update_age = time.time() - status.last_update
            age_str = f"{last_update_age:.0f}s ago" if last_update_age < 60 else f"{last_update_age/60:.0f}m ago"
            tk.Label(content, text=f"Last update: {age_str}", bg=colors["bg_secondary"], fg=colors["fg_secondary"], font=("System", 7)).pack(anchor=tk.W)
        
        self._draw_status_led()
    
    def _create_metric_row(self, parent: tk.Frame, label: str, value: Optional[float], unit: str, color: str):
        """Create a metric display row"""
        if value is None:
            value_str = "N/A"
        else:
            value_str = f"{value:.1f}" if isinstance(value, float) else str(value)
        
        row = tk.Frame(parent, bg=self.colors["bg_secondary"])
        row.pack(fill=tk.X, pady=2)
        
        tk.Label(row, text=label, bg=self.colors["bg_secondary"], fg=self.colors["fg_secondary"], font=("System", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        tk.Label(row, text=f"{value_str} {unit}", bg=self.colors["bg_secondary"], fg=color, font=("System", 9, "bold")).pack(side=tk.LEFT, padx=5)
    
    def _draw_status_led(self):
        """Draw the online/offline status LED"""
        color = "#00ff00" if self.status.online else "#ff4444"
        self.status_led.create_oval(1, 1, 11, 11, fill=color, outline=color)
        if self.status.online:
            self.status_led.create_oval(3, 3, 9, 9, fill="#ffffff", outline=color)
    
    @staticmethod
    def _format_uptime(seconds: int) -> str:
        """Format uptime in human readable format"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds//60}m"
        elif seconds < 86400:
            return f"{seconds//3600}h"
        else:
            return f"{seconds//86400}d"

class BeaconMonitorGUI:
    """Main beacon monitoring dashboard"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Beacon Monitor - Live Dashboard")
        self.root.geometry("1400x900")
        
        # Get adaptive colors for light/dark mode
        self.colors = get_adaptive_colors()
        self.root.configure(bg=self.colors["bg_primary"])
        
        self.beacons_config: Dict[str, Dict[str, Any]] = {}
        self.beacon_status: Dict[str, BeaconStatus] = {}
        self.beacon_cards: Dict[str, BeaconCard] = {}
        self.config_file = PROJECT_ROOT / "config" / "beacons_config.json"
        self.monitoring_active = False
        self.update_thread: Optional[threading.Thread] = None
        self.poll_interval = 2.0  # Poll every 2 seconds
        
        # Load configuration
        self.load_config()
        
        # Initialize beacon status
        for beacon_id in self.beacons_config.keys():
            config = self.beacons_config[beacon_id]
            self.beacon_status[beacon_id] = BeaconStatus(
                beacon_id=beacon_id,
                ip_address=config.get("ip_address", "0.0.0.0"),
                port=config.get("port", 5000)
            )
        
        # Setup GUI
        self._setup_styles()
        self._create_ui()
        self._start_monitoring()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def _setup_styles(self):
        """Setup ttk styles"""
        style = ttk.Style()
        set_native_theme(style)
        
        # Use system colors and fonts
        style.configure('Header.TLabel', font=('System', 14, 'bold'))
    
    def _create_ui(self):
        """Create the main UI"""
        # Header
        header = tk.Frame(self.root, bg=self.colors["bg_secondary"], height=60)
        header.pack(fill=tk.X, padx=0, pady=0)
        header.pack_propagate(False)
        
        title = tk.Label(
            header,
            text="BEACON MONITOR - Live Dashboard",
            bg=self.colors["bg_secondary"],
            fg=self.colors["accent_green"],
            font=("System", 16, "bold")
        )
        title.pack(side=tk.LEFT, padx=20, pady=15)
        
        # Status summary
        self.summary_var = tk.StringVar(value="Initializing...")
        summary_label = tk.Label(
            header,
            textvariable=self.summary_var,
            bg=self.colors["bg_secondary"],
            fg=self.colors["accent_orange"],
            font=("System", 11)
        )
        summary_label.pack(side=tk.RIGHT, padx=20, pady=15)
        
        # Main content area with scrollbar
        main_frame = tk.Frame(self.root, bg=self.colors["bg_primary"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas for scrolling
        canvas = tk.Canvas(main_frame, bg=self.colors["bg_primary"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors["bg_primary"])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Grid layout for beacon cards
        self.cards_frame = scrollable_frame
        self._arrange_beacon_cards()
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Footer with controls
        footer = tk.Frame(self.root, bg=self.colors["bg_secondary"], height=50)
        footer.pack(fill=tk.X, padx=0, pady=0)
        footer.pack_propagate(False)
        
        # Create button frame with proper styling
        button_frame = tk.Frame(footer, bg=self.colors["bg_secondary"])
        button_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        
        # Refresh button
        refresh_btn = ttk.Button(
            button_frame,
            text="Refresh Now",
            command=self._force_refresh
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Connection status button
        conn_btn = ttk.Button(
            button_frame,
            text="Connection Status",
            command=self._show_connection_status
        )
        conn_btn.pack(side=tk.LEFT, padx=5)
        
        # Export button
        export_btn = ttk.Button(
            button_frame,
            text="Export Report",
            command=self._export_report
        )
        export_btn.pack(side=tk.LEFT, padx=5)
        
        # Close button
        close_btn = ttk.Button(
            button_frame,
            text="Close",
            command=self.on_closing
        )
        close_btn.pack(side=tk.RIGHT, padx=5)
    
    def _arrange_beacon_cards(self):
        """Arrange beacon cards in grid layout"""
        # Clear existing cards
        for card in self.beacon_cards.values():
            card.frame.destroy()
        self.beacon_cards.clear()
        
        # Calculate grid columns based on number of beacons
        num_beacons = len(self.beacons_config)
        if num_beacons == 0:
            empty_label = tk.Label(
                self.cards_frame,
                text="No beacons configured",
                bg=self.colors["bg_primary"],
                fg=self.colors["fg_secondary"],
                font=("System", 12)
            )
            empty_label.pack(pady=20)
            return
        
        cols = min(4, max(1, int(math.sqrt(num_beacons))))
        
        # Create grid structure
        grid_frame = tk.Frame(self.cards_frame, bg=self.colors["bg_primary"])
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        for idx, beacon_id in enumerate(sorted(self.beacons_config.keys())):
            row = idx // cols
            col = idx % cols
            
            # Create cell frame
            cell = tk.Frame(grid_frame, bg=self.colors["bg_primary"])
            cell.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            
            # Create beacon card
            status = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id))
            card = BeaconCard(cell, beacon_id, status, self.colors)
            self.beacon_cards[beacon_id] = card
        
        # Configure grid weights
        for i in range(cols):
            grid_frame.columnconfigure(i, weight=1)
    
    def _update_cards(self):
        """Update beacon cards with latest status"""
        for beacon_id, card in self.beacon_cards.items():
            status = self.beacon_status.get(beacon_id)
            if status:
                card.status = status
                card._draw_status_led()
        
        # Update summary
        online_count = sum(1 for s in self.beacon_status.values() if s.online)
        total_count = len(self.beacon_status)
        self.summary_var.set(f"Online: {online_count}/{total_count} beacons • Last update: {time.strftime('%H:%M:%S')}")
    
    def _monitoring_loop(self):
        """Background thread for monitoring beacons"""
        while self.monitoring_active:
            try:
                # Simulate beacon polling (replace with actual network calls)
                for beacon_id, config in self.beacons_config.items():
                    status = self._poll_beacon(beacon_id, config)
                    if status:
                        self.beacon_status[beacon_id] = status
                
                # Update UI
                self.root.after(0, self._update_cards)
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(1)
    
    def _poll_beacon(self, beacon_id: str, config: Dict[str, Any]) -> Optional[BeaconStatus]:
        """Poll a single beacon for status (simulated)"""
        # TODO: Replace with actual network polling
        # For now, simulate beacon status with random values
        
        status = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id))
        status.ip_address = config.get("ip_address", "0.0.0.0")
        status.port = config.get("port", 5000)
        status.last_update = time.time()
        
        # Simulate online status (90% of beacons online)
        status.online = random.random() > 0.1
        
        if status.online:
            # Simulate healthy beacon data
            status.battery_percent = random.uniform(70, 95)
            status.battery_voltage = random.uniform(11.8, 12.2)
            status.current_amperage = random.uniform(1.5, 3.5)
            status.fan_speed_rpm = random.randint(1500, 3000)
            status.led_brightness = random.randint(80, 100)
            status.temperature_c = random.uniform(35, 45)
            status.uptime_seconds = random.randint(3600, 604800)  # 1 hour to 7 days
        
        return status
    
    def _force_refresh(self):
        """Force immediate refresh of all beacon status"""
        logger.info("Forcing beacon status refresh...")
        self._update_cards()
    
    def _export_report(self):
        """Export beacon status report"""
        report_data = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "beacons": []
        }
        
        for beacon_id, status in self.beacon_status.items():
            report_data["beacons"].append({
                "beacon_id": beacon_id,
                "ip_address": status.ip_address,
                "port": status.port,
                "online": status.online,
                "battery_percent": status.battery_percent,
                "battery_voltage": status.battery_voltage,
                "current_amperage": status.current_amperage,
                "fan_speed_rpm": status.fan_speed_rpm,
                "led_brightness": status.led_brightness,
                "temperature_c": status.temperature_c,
                "uptime_seconds": status.uptime_seconds
            })
        
        # Save to file
        report_file = PROJECT_ROOT / "backups" / f"beacon_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"Report exported to {report_file}")
    
    def _show_connection_status(self):
        """Show beacon connection status window"""
        # Create connection status window
        conn_window = tk.Toplevel(self.root)
        conn_window.title("Beacon Connection Status")
        conn_window.geometry("800x500")
        conn_window.configure(bg=self.colors["bg_primary"])
        
        # Header
        header = tk.Frame(conn_window, bg=self.colors["bg_secondary"], height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        title = tk.Label(
            header,
            text="BEACON CONNECTION STATUS",
            bg=self.colors["bg_secondary"],
            fg=self.colors["accent_green"],
            font=("System", 14, "bold"),
            anchor=tk.W
        )
        title.pack(side=tk.LEFT, padx=15, pady=10)
        
        # Summary
        online_count = sum(1 for s in self.beacon_status.values() if s.online)
        total_count = len(self.beacon_status)
        
        summary_frame = tk.Frame(conn_window, bg=self.colors["bg_primary"])
        summary_frame.pack(fill=tk.X, padx=10, pady=10)
        
        summary_text = f"Online: {online_count}/{total_count} beacons ({100*online_count//max(1,total_count)}%)"
        tk.Label(
            summary_frame,
            text=summary_text,
            bg=self.colors["bg_primary"],
            fg=self.colors["accent_green"] if online_count == total_count else self.colors["accent_orange"],
            font=("System", 11, "bold")
        ).pack(anchor=tk.W, padx=10, pady=5)
        
        # Connection list
        list_frame = tk.Frame(conn_window, bg=self.colors["bg_primary"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Canvas for scrolling
        canvas = tk.Canvas(list_frame, bg=self.colors["bg_primary"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors["bg_primary"])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Add beacon connection items
        for beacon_id in sorted(self.beacon_status.keys()):
            status = self.beacon_status[beacon_id]
            self._create_connection_item(scrollable_frame, beacon_id, status)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Footer
        footer = tk.Frame(conn_window, bg="#1a1a1a", height=40)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)
        
        close_btn = tk.Button(
            footer,
            text="Close",
            bg="#8f2d2d",
            fg="#ffffff",
            activebackground="#cc3333",
            activeforeground="#ffffff",
            font=("Arial", 10),
            relief=tk.RAISED,
            borderwidth=2,
            padx=12,
            pady=6,
            command=conn_window.destroy
        )
        close_btn.pack(side=tk.RIGHT, padx=10, pady=8)
        
        ensure_window_fits_content(conn_window, min_width=800, min_height=500, padding=60, center=True)
    
    def _create_connection_item(self, parent: tk.Frame, beacon_id: str, status: BeaconStatus):
        """Create a connection status item"""
        item_frame = tk.Frame(parent, bg="#222222", relief=tk.SUNKEN, borderwidth=1)
        item_frame.pack(fill=tk.X, pady=3, padx=2)
        
        # Status indicator and ID
        header_frame = tk.Frame(item_frame, bg="#222222")
        header_frame.pack(fill=tk.X, padx=8, pady=6)
        
        # Online/Offline status
        status_color = "#00ff00" if status.online else "#ff4444"
        status_text = "ONLINE" if status.online else "OFFLINE"
        
        tk.Label(
            header_frame,
            text=status_text,
            bg="#222222",
            fg=status_color,
            font=("Arial", 10, "bold"),
            width=10,
            anchor=tk.W
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Label(
            header_frame,
            text=beacon_id,
            bg="#222222",
            fg="#cccccc",
            font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT, padx=5)
        
        # Network info
        tk.Label(
            header_frame,
            text=f"{status.ip_address}:{status.port}",
            bg="#222222",
            fg="#888888",
            font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=5)
        
        # Last update
        if status.last_update:
            last_update_age = time.time() - status.last_update
            age_str = f"{last_update_age:.0f}s ago" if last_update_age < 60 else f"{last_update_age/60:.1f}m ago"
            tk.Label(
                header_frame,
                text=age_str,
                bg="#222222",
                fg="#666666",
                font=("Arial", 8)
            ).pack(side=tk.RIGHT, padx=5)
    
    def load_config(self):
        """Load beacon configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                    self.beacons_config = config_data.get("beacons", {})
                    logger.info(f"Loaded {len(self.beacons_config)} beacons from config")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self.beacons_config = {}
        else:
            # Create sample beacons for demonstration
            self.beacons_config = {
                f"beacon_{i:02d}": {
                    "ip_address": f"192.168.1.{100+i}",
                    "port": 5000 + i
                }
                for i in range(6)
            }
            logger.info(f"Created {len(self.beacons_config)} sample beacons")
    
    def _start_monitoring(self):
        """Start the monitoring background thread"""
        self.monitoring_active = True
        self.update_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.update_thread.start()
        logger.info("Monitoring started")
    
    def on_closing(self):
        """Handle window closing"""
        self.monitoring_active = False
        if self.update_thread:
            self.update_thread.join(timeout=2.0)
        self.root.destroy()
        logger.info("Monitor closed")
    
    def run(self):
        """Run the GUI"""
        ensure_window_fits_content(self.root, min_width=1400, min_height=900, padding=80, center=True)
        self.root.mainloop()

def main():
    """Entry point"""
    monitor = BeaconMonitorGUI()
    monitor.run()

if __name__ == "__main__":
    main()

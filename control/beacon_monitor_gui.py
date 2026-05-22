#!/usr/bin/env python3
"""
Beacon Monitor GUI.
"""

import tkinter as tk
from tkinter import ttk
import json
import logging
import threading
import time
import platform
from collections import deque
from types import SimpleNamespace
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import math
import sys

logger = logging.getLogger("beacon_monitor_gui")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from launcher_gui import ensure_window_fits_content, set_native_theme, get_adaptive_colors, get_system_appearance
    from beacon_network import fetch_status
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
    from beacon_network import fetch_status


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
    STALE_DATA_TIMEOUT_SECONDS = 2.0
    TTD_WINDOW_SIZE = 10
    TEMPERATURE_WARNING_THRESHOLD_C = 40.0
    TEMPERATURE_CRITICAL_THRESHOLD_C = 50.0
    TEMPERATURE_SHAKE_INTERVAL_MS = 140
    
    def __init__(self, parent: tk.Frame, beacon_id: str, status: BeaconStatus, colors: dict):
        self.beacon_id = beacon_id
        self.status = status
        self.colors = colors
        self.metric_bars: Dict[str, Dict[str, Any]] = {}
        self.temperature_widgets: Dict[str, Any] = {}
        self.packet_intervals: deque[float] = deque(maxlen=self.TTD_WINDOW_SIZE)
        self.last_packet_timestamp: Optional[float] = None
        self.last_seen_status_timestamp: Optional[float] = None
        self.is_stale = False
        self.temperature_alert_state = "normal"
        self.temperature_shake_phase = 0
        self.temperature_shake_job: Optional[str] = None
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

        self.title_label = id_label
        self.overlay = tk.Frame(self.frame, bg="#7a0000")
        self.overlay_label = tk.Label(
            self.overlay,
            text="OFFLINE",
            bg="#7a0000",
            fg="#ffffff",
            font=("System", 22, "bold"),
        )
        self.overlay_label.pack(expand=True, fill=tk.BOTH)
        self.overlay.place_forget()
        
        # Content area
        content = tk.Frame(self.frame, bg=colors["bg_secondary"])
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # IP and Port info
        info_text = f"{status.ip_address}:{status.port}"
        tk.Label(content, text=info_text, bg=colors["bg_secondary"], fg=colors["fg_secondary"], font=("System", 8)).pack(anchor=tk.W)
        
        # Visual overview section
        visuals = tk.Frame(content, bg=colors["bg_secondary"])
        visuals.pack(fill=tk.X, pady=(8, 6))

        self._create_metric_row(content, "Voltage", status.battery_voltage, "V", colors["accent_green"])
        self._create_metric_row(content, "Current", status.current_amperage, "A", colors["accent_green"])
        self._create_metric_row(content, "Fan Speed", status.fan_speed_rpm, "RPM", colors["accent_orange"])
        self._create_temperature_row(content, status.temperature_c)
        self._create_metric_row(content, "LED Brightness", status.led_brightness, "%", colors["accent_orange"])

        self._create_visual_bar(
            visuals,
            "Battery",
            self._metric_to_percent(status.battery_percent, 0, 100),
            self._battery_color(status.battery_percent),
        )
        self._create_visual_bar(
            visuals,
            "Thermal",
            self._metric_to_percent(status.temperature_c, 20, 60),
            self._temperature_color(status.temperature_c),
        )
        self._create_visual_bar(
            visuals,
            "Fan",
            self._metric_to_percent(status.fan_speed_rpm, 0, 3000),
            colors["accent_orange"],
        )
        self._create_visual_bar(
            visuals,
            "LED",
            self._metric_to_percent(status.led_brightness, 0, 100),
            colors["accent_green"],
        )
        
        # Uptime section
        uptime_str = self._format_uptime(status.uptime_seconds) if status.uptime_seconds else "N/A"
        tk.Label(content, text=f"Uptime: {uptime_str}", bg=colors["bg_secondary"], fg=colors["fg_secondary"], font=("System", 8)).pack(anchor=tk.W, pady=2)

        self.last_update_label = tk.Label(
            content,
            text="Last update: N/A",
            bg=colors["bg_secondary"],
            fg=colors["fg_secondary"],
            font=("System", 7),
        )
        self.last_update_label.pack(anchor=tk.W)

        self.ttd_label = tk.Label(
            content,
            text="Time to dead: N/A",
            bg=colors["bg_secondary"],
            fg=colors["fg_secondary"],
            font=("System", 8, "bold"),
        )
        self.ttd_label.pack(anchor=tk.W, pady=(1, 0))
        
        self.record_packet(status.last_update)
        self.update_time_to_dead_display()
        self._apply_freshness_state()
        self.update_temperature_state(status.temperature_c)
        self._draw_status_led()

    def record_packet(self, packet_timestamp: Optional[float]) -> None:
        """Track packet arrival timing for sliding-window cadence estimation."""
        if packet_timestamp is None:
            return

        if self.last_seen_status_timestamp is not None and packet_timestamp <= self.last_seen_status_timestamp:
            return

        if self.last_packet_timestamp is not None:
            interval = packet_timestamp - self.last_packet_timestamp
            if 0.0 < interval < 30.0:
                self.packet_intervals.append(interval)

        self.last_packet_timestamp = packet_timestamp
        self.last_seen_status_timestamp = packet_timestamp

    def _sliding_window_interval(self) -> Optional[float]:
        if not self.packet_intervals:
            return None
        return sum(self.packet_intervals) / len(self.packet_intervals)

    def _sliding_window_jitter(self) -> Optional[float]:
        if len(self.packet_intervals) < 2:
            return None
        mean = self._sliding_window_interval()
        if mean is None:
            return None
        variance = sum((x - mean) ** 2 for x in self.packet_intervals) / len(self.packet_intervals)
        return math.sqrt(variance)

    def update_time_to_dead_display(self) -> None:
        """Update last-update age and time-to-dead using a sliding timing window."""
        now = time.time()
        last_update = self.status.last_update

        if last_update is None:
            self.last_update_label.config(text="Last update: N/A")
            self.ttd_label.config(text="Time to dead: 0.00s", fg=self.colors["accent_red"])
            return

        age = max(0.0, now - last_update)
        if age < 60:
            age_str = f"{age:.1f}s ago"
        else:
            age_str = f"{age/60:.1f}m ago"
        self.last_update_label.config(text=f"Last update: {age_str}")

        remaining = max(0.0, self.STALE_DATA_TIMEOUT_SECONDS - age)
        cadence = self._sliding_window_interval()
        jitter = self._sliding_window_jitter()
        if cadence is not None and jitter is not None:
            detail = f" (cadence {cadence:.2f}s ±{jitter:.2f}s)"
        elif cadence is not None:
            detail = f" (cadence {cadence:.2f}s)"
        else:
            detail = ""

        if remaining <= 0.25:
            ttd_color = self.colors["accent_red"]
        elif remaining <= 0.75:
            ttd_color = self.colors["accent_orange"]
        else:
            ttd_color = self.colors["accent_green"]

        self.ttd_label.config(text=f"Time to dead: {remaining:.2f}s{detail}", fg=ttd_color)
    
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

    def _create_temperature_row(self, parent: tk.Frame, value: Optional[float]):
        """Create the temperature row with visual alert affordances."""
        row = tk.Frame(parent, bg=self.colors["bg_secondary"])
        row.pack(fill=tk.X, pady=2)

        label = tk.Label(
            row,
            text="Temperature",
            bg=self.colors["bg_secondary"],
            fg=self.colors["fg_secondary"],
            font=("System", 9),
            width=12,
            anchor=tk.W,
        )
        label.pack(side=tk.LEFT)

        icon = tk.Canvas(
            row,
            width=18,
            height=18,
            bg=self.colors["bg_secondary"],
            highlightthickness=0,
        )
        icon.pack(side=tk.LEFT, padx=(0, 5))

        value_label = tk.Label(
            row,
            text=self._format_temperature_value(value),
            bg=self.colors["bg_secondary"],
            fg=self._temperature_color(value),
            font=("System", 9, "bold"),
        )
        value_label.pack(side=tk.LEFT, padx=5)

        self.temperature_widgets = {
            "row": row,
            "label": label,
            "icon": icon,
            "value": value_label,
        }
        self._render_thermometer_icon(0)
        self._apply_temperature_style(value)

    def _apply_temperature_style(self, value: Optional[float]) -> str:
        """Update the temperature row according to the current temperature state."""
        if value is None:
            state = "normal"
        elif value >= self.TEMPERATURE_CRITICAL_THRESHOLD_C:
            state = "critical"
        elif value >= self.TEMPERATURE_WARNING_THRESHOLD_C:
            state = "warning"
        else:
            state = "normal"

        self.temperature_alert_state = state

        label = self.temperature_widgets.get("label")
        value_label = self.temperature_widgets.get("value")
        if not label or not value_label:
            return state

        if state == "critical":
            fg_color = self.colors["accent_red"]
            font = ("System", 9, "bold")
        elif state == "warning":
            fg_color = "#e6c200"
            font = ("System", 9, "bold")
        else:
            fg_color = self.colors["fg_secondary"]
            font = ("System", 9)

        label.config(fg=fg_color, font=font)
        value_label.config(fg=fg_color, font=font)
        self._render_thermometer_icon(self.temperature_shake_offset())
        self._manage_temperature_animation()
        return state

    def _format_temperature_value(self, value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.1f} C"

    def _temperature_color(self, temperature_c: Optional[float]) -> str:
        if temperature_c is None:
            return self.colors["accent_orange"]
        if temperature_c >= self.TEMPERATURE_CRITICAL_THRESHOLD_C:
            return self.colors["accent_red"]
        if temperature_c >= self.TEMPERATURE_WARNING_THRESHOLD_C:
            return "#e6c200"
        return self.colors["accent_green"]

    def _render_thermometer_icon(self, x_offset: int) -> None:
        icon = self.temperature_widgets.get("icon")
        if not icon:
            return

        icon.delete("all")
        base_x = 8 + x_offset
        tube_top = 3
        tube_bottom = 12
        bulb_radius = 4
        fill_color = self._temperature_color(self.status.temperature_c)
        outline_color = fill_color if self.temperature_alert_state != "normal" else self.colors["fg_secondary"]

        icon.create_line(base_x, tube_top, base_x, tube_bottom, fill=outline_color, width=2, capstyle=tk.ROUND)
        icon.create_oval(base_x - bulb_radius, tube_bottom - 1, base_x + bulb_radius, tube_bottom + 7, fill=fill_color, outline=outline_color, width=2)
        icon.create_rectangle(base_x - 1, tube_top + 2, base_x + 1, tube_bottom - 1, fill=fill_color, outline=fill_color)

    def temperature_shake_offset(self) -> int:
        if self.temperature_alert_state == "critical":
            return 2 if self.temperature_shake_phase % 2 == 0 else -2
        if self.temperature_alert_state == "warning":
            return 1 if self.temperature_shake_phase % 2 == 0 else -1
        return 0

    def _manage_temperature_animation(self) -> None:
        if self.temperature_shake_job is not None:
            try:
                self.frame.after_cancel(self.temperature_shake_job)
            except Exception:
                pass
            self.temperature_shake_job = None

        if self.temperature_alert_state in {"warning", "critical"}:
            self.temperature_shake_job = self.frame.after(self.TEMPERATURE_SHAKE_INTERVAL_MS, self._temperature_animation_tick)

    def _temperature_animation_tick(self) -> None:
        self.temperature_shake_job = None
        if not self.temperature_widgets:
            return

        if self.temperature_alert_state not in {"warning", "critical"}:
            self._render_thermometer_icon(0)
            return

        self.temperature_shake_phase = (self.temperature_shake_phase + 1) % 8
        self._render_thermometer_icon(self.temperature_shake_offset())
        self.temperature_shake_job = self.frame.after(self.TEMPERATURE_SHAKE_INTERVAL_MS, self._temperature_animation_tick)

    def update_temperature_state(self, temperature_c: Optional[float]) -> None:
        """Refresh the temperature row from the latest telemetry value."""
        self.status.temperature_c = temperature_c
        self._apply_temperature_style(temperature_c)

    def _create_visual_bar(self, parent: tk.Frame, label: str, percent: Optional[float], color: str):
        """Create a small inline progress-style visualization."""
        container = tk.Frame(parent, bg=self.colors["bg_secondary"])
        container.pack(fill=tk.X, pady=3)

        tk.Label(
            container,
            text=label,
            bg=self.colors["bg_secondary"],
            fg=self.colors["fg_secondary"],
            font=("System", 8),
            width=11,
            anchor=tk.W,
        ).pack(side=tk.LEFT)

        canvas = tk.Canvas(
            container,
            width=140,
            height=14,
            bg=self.colors["bg_secondary"],
            highlightthickness=0,
        )
        canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        track = canvas.create_rectangle(1, 2, 139, 12, fill="#2a2a2a", outline=self.colors["border"])
        fill = canvas.create_rectangle(1, 2, 1, 12, fill=color, outline=color)
        value_text = canvas.create_text(138, 7, text=self._format_percent_text(percent), anchor=tk.E, fill=self.colors["fg_secondary"], font=("System", 8, "bold"))

        self.metric_bars[label] = {
            "canvas": canvas,
            "track": track,
            "fill": fill,
            "text": value_text,
        }
        self._update_visual_bar(label, percent, color)

    def _update_visual_bar(self, label: str, percent: Optional[float], color: str) -> None:
        bar = self.metric_bars.get(label)
        if not bar:
            return

        canvas: tk.Canvas = bar["canvas"]
        fill = bar["fill"]
        value_text = bar["text"]
        width = 138

        if percent is None:
            percent_value = 0.0
        else:
            percent_value = max(0.0, min(100.0, float(percent)))

        fill_width = max(1, int(round(width * (percent_value / 100.0)))) if percent is not None else 1
        canvas.coords(fill, 1, 2, fill_width, 12)
        canvas.itemconfig(fill, fill=color, outline=color)
        canvas.itemconfig(value_text, text=self._format_percent_text(percent))

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

    @staticmethod
    def _format_percent_text(percent: Optional[float]) -> str:
        if percent is None:
            return "N/A"
        return f"{percent:.0f}%"

    def _apply_freshness_state(self) -> None:
        """Render the card as stale when telemetry stops updating."""
        last_update = self.status.last_update
        now = time.time()
        is_stale = last_update is None or (now - last_update) > self.STALE_DATA_TIMEOUT_SECONDS

        if is_stale == self.is_stale:
            self._sync_visual_state()
            return

        self.is_stale = is_stale
        self._sync_visual_state()

    def _sync_visual_state(self) -> None:
        base_id_color = self.colors["accent_red"] if self.is_stale else self.colors["accent_green"]
        base_status_text = "OFFLINE" if self.is_stale or not self.status.online else "ONLINE"
        base_status_color = self.colors["accent_red"] if base_status_text == "OFFLINE" else self.colors["accent_green"]

        self.title_label.config(fg=base_id_color)
        self.status_text.config(text=base_status_text, fg=base_status_color)

        if self.is_stale:
            self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.overlay.lift()
            self.overlay_label.config(text="OFFLINE\nSTALE DATA")
        else:
            self.overlay.place_forget()
    
    def _draw_status_led(self):
        """Draw the online/offline status LED"""
        color = "#00ff00" if self.status.online and not self.is_stale else "#ff4444"
        self.status_led.create_oval(1, 1, 11, 11, fill=color, outline=color)
        if self.status.online and not self.is_stale:
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
        self._start_stale_watchdog()
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
        
        cols = min(4, max(1, math.ceil(math.sqrt(num_beacons))))
        rows = max(1, math.ceil(num_beacons / cols))

        # Place cards from the center outward so the grid grows in expanding rings
        center_row = (rows - 1) / 2.0
        center_col = (cols - 1) / 2.0
        positions = [(r, c) for r in range(rows) for c in range(cols)]
        positions.sort(
            key=lambda rc: (
                abs(rc[0] - center_row) + abs(rc[1] - center_col),
                (rc[0] - center_row) ** 2 + (rc[1] - center_col) ** 2,
                rc[0],
                rc[1],
            )
        )
        
        # Create grid structure
        grid_frame = tk.Frame(self.cards_frame, bg=self.colors["bg_primary"])
        grid_frame.pack(fill=tk.BOTH, expand=True)
        
        for idx, beacon_id in enumerate(sorted(self.beacons_config.keys())):
            row, col = positions[idx]
            
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
        for i in range(rows):
            grid_frame.rowconfigure(i, weight=1)
    
    def _update_cards(self):
        """Update beacon cards with latest status"""
        for beacon_id, card in self.beacon_cards.items():
            status = self.beacon_status.get(beacon_id)
            if status:
                card.status = status
                card.record_packet(status.last_update)
                card._apply_freshness_state()
                card.update_temperature_state(status.temperature_c)
                card.update_time_to_dead_display()
                card._draw_status_led()
                card._update_visual_bar("Battery", card._metric_to_percent(status.battery_percent, 0, 100), card._battery_color(status.battery_percent))
                card._update_visual_bar("Thermal", card._metric_to_percent(status.temperature_c, 20, 60), card._temperature_color(status.temperature_c))
                card._update_visual_bar("Fan", card._metric_to_percent(status.fan_speed_rpm, 0, 3000), self.colors["accent_orange"])
                card._update_visual_bar("LED", card._metric_to_percent(status.led_brightness, 0, 100), self.colors["accent_green"])
        
        # Update summary
        online_count = sum(1 for s in self.beacon_status.values() if s.online)
        total_count = len(self.beacon_status)
        self.summary_var.set(f"Online: {online_count}/{total_count} beacons • Last update: {time.strftime('%H:%M:%S')}")

    def _start_stale_watchdog(self):
        """Start a UI watchdog that marks cards stale when their data ages out."""
        self.root.after(250, self._watchdog_tick)

    def _watchdog_tick(self):
        """Check all beacon cards for stale telemetry and refresh their visual state."""
        if not self.monitoring_active:
            self.root.after(250, self._watchdog_tick)
            return

        for card in self.beacon_cards.values():
            card._apply_freshness_state()
            card.update_time_to_dead_display()

        self.root.after(250, self._watchdog_tick)
    
    def _monitoring_loop(self):
        """Background thread for monitoring beacons"""
        next_poll_times: Dict[str, float] = {}

        while self.monitoring_active:
            try:
                now = time.time()
                next_due_time = now + max(0.2, float(self.poll_interval))

                for beacon_id, config in self.beacons_config.items():
                    interval = config.get("poll_interval", self.poll_interval)
                    try:
                        poll_interval = max(0.2, float(interval))
                    except (TypeError, ValueError):
                        poll_interval = max(0.2, float(self.poll_interval))

                    due_time = next_poll_times.get(beacon_id, 0.0)
                    if now >= due_time:
                        status = self._poll_beacon(beacon_id, config)
                        if status:
                            self.beacon_status[beacon_id] = status
                        due_time = now + poll_interval
                        next_poll_times[beacon_id] = due_time

                    next_due_time = min(next_due_time, due_time)

                # Update UI
                self.root.after(0, self._update_cards)

                sleep_for = max(0.05, next_due_time - time.time())
                time.sleep(sleep_for)
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(1)
    
    def _poll_beacon(self, beacon_id: str, config: Dict[str, Any]) -> Optional[BeaconStatus]:
        """Poll a single beacon for live status."""
        
        status = self.beacon_status.get(beacon_id, BeaconStatus(beacon_id=beacon_id))
        status.ip_address = config.get("ip_address", "0.0.0.0")
        status.port = config.get("port", 5000)

        beacon = SimpleNamespace(ip_address=status.ip_address, port=status.port)
        try:
            payload = fetch_status(beacon, timeout=2.5)
            status.online = True
            status.last_update = time.time()
            status.battery_voltage = payload.get("battery_v")
            status.battery_percent = payload.get("battery_pct")
            status.current_amperage = payload.get("current_a")
            status.fan_speed_rpm = payload.get("fan_rpm")
            status.led_brightness = payload.get("brightness_pct")
            status.temperature_c = payload.get("temp_c")
            status.uptime_seconds = payload.get("uptime_s")
        except Exception as exc:
            status.online = False
            logger.debug("Beacon poll failed for %s (%s:%s): %s", beacon_id, status.ip_address, status.port, exc)
        
        return status
    
    def _force_refresh(self):
        """Force immediate refresh of all beacon status"""
        logger.info("Forcing beacon status refresh...")
        for beacon_id, config in self.beacons_config.items():
            status = self._poll_beacon(beacon_id, config)
            if status:
                self.beacon_status[beacon_id] = status
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
            self.beacons_config = {}
            logger.warning(
                "Beacon configuration file not found at %s. Configure beacons first in Beacon Configuration & Monitor.",
                self.config_file,
            )
    
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

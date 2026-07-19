#!/usr/bin/env python3
"""
Beacon Monitor GUI - Industrial Dark Theme
Live dashboard for ESP32-C6 IR beacon telemetry monitoring.
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

from control._theme import (
    DARK_BG, DARK_BG_MED, DARK_BG_LIGHT, DARK_FG, DARK_FG_SEC, DARK_FG_MUTED,
    GREEN_OK, AMBER_WARN, RED_ERR, BLUE_LINK,
    FailsafeAnnunciator, StealthAnnunciator,
    apply_treeview_style, get_status_color,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from control.beacon_network import fetch_status  # type: ignore[import-not-found]
except Exception:
    fetch_status = None  # type: ignore[assignment]

logger = logging.getLogger("beacon_monitor_gui")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


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
    endpoint_url: str = ""
    wifi_ssid: Optional[str] = None
    signal_dbm: Optional[float] = None
    last_error: Optional[str] = None
    last_telemetry: Optional[str] = None
    telemetry: Optional[Dict[str, Any]] = None
    display_name: Optional[str] = None


class BeaconCard:
    """Visual beacon status card - Industrial theme"""
    STALE_DATA_TIMEOUT_SECONDS = 2.0
    TTD_WINDOW_SIZE = 10
    TEMPERATURE_WARNING_THRESHOLD_C = 40.0
    TEMPERATURE_CRITICAL_THRESHOLD_C = 50.0
    TEMPERATURE_SHAKE_INTERVAL_MS = 140
    
    def __init__(self, parent: tk.Frame, beacon_id: str, status: BeaconStatus):
        self.beacon_id = beacon_id
        self.status = status
        self.metric_bars: Dict[str, Dict[str, Any]] = {}
        self.temperature_widgets: Dict[str, Any] = {}
        self.packet_intervals: deque[float] = deque(maxlen=self.TTD_WINDOW_SIZE)
        self.last_packet_timestamp: Optional[float] = None
        self.last_seen_status_timestamp: Optional[float] = None
        self.is_stale = False
        self.temperature_alert_state = "normal"
        self.temperature_shake_phase = 0
        self.temperature_shake_job: Optional[str] = None
        
        # Card frame with subtle border
        self.frame = tk.Frame(
            parent, 
            bg=DARK_BG_MED, 
            highlightbackground=DARK_BG, 
            highlightthickness=1
        )
        self.frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        
        # Header with ID and status LED
        header = tk.Frame(self.frame, bg=DARK_BG_MED, height=36)
        header.pack(fill=tk.X, padx=2, pady=2)
        header.pack_propagate(False)
        
        # Status LED (canvas circle)
        self.status_led = tk.Canvas(
            header, width=14, height=14, 
            bg=DARK_BG_MED, highlightthickness=0
        )
        self.status_led.pack(side=tk.LEFT, padx=10, pady=11)
        
        # Beacon ID label
        self.id_label = tk.Label(
            header,
            text=beacon_id,
            bg=DARK_BG_MED,
            fg=GREEN_OK if status.online else RED_ERR,
            font=("Segoe UI", 12, "bold")
        )
        self.id_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Status text
        self.status_text = tk.Label(
            header,
            text="OFFLINE" if not status.online else "ONLINE",
            bg=DARK_BG_MED,
            fg=RED_ERR if not status.online else GREEN_OK,
            font=("Segoe UI", 9, "bold")
        )
        self.status_text.pack(side=tk.RIGHT, padx=10)
        
        self.title_label = self.id_label
        
        # Offline overlay
        self.overlay = tk.Frame(self.frame, bg="#561e15")
        self.overlay_label = tk.Label(
            self.overlay,
            text="OFFLINE",
            bg="#561e15",
            fg="#fad2c9",
            font=("Segoe UI", 20, "bold"),
        )
        self.overlay_label.pack(expand=True, fill=tk.BOTH)
        self.overlay.place_forget()
        
        # Content area
        content = tk.Frame(self.frame, bg=DARK_BG_MED)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # IP and Port
        info_text = f"{status.ip_address}:{status.port}"
        tk.Label(content, text=info_text, bg=DARK_BG_MED, fg=DARK_FG_SEC, font=("Segoe UI", 8)).pack(anchor=tk.W)

        endpoint_text = status.endpoint_url or f"http://{status.ip_address}:{status.port}/api/status"
        tk.Label(
            content,
            text=f"Endpoint: {endpoint_text}",
            bg=DARK_BG_MED,
            fg=DARK_FG_MUTED,
            font=("Segoe UI", 8),
            wraplength=260,
        ).pack(anchor=tk.W, pady=(2, 8))
        
        # Metrics rows
        self._create_metric_row(content, "Voltage", "--", "V", is_battery=False)
        self._create_metric_row(content, "Current", "--", "A", is_battery=False)
        
        self._create_metric_row(content, "Fan", "--", "RPM", is_battery=False)
        
        self._create_metric_row(content, "LED", "--", "%", is_battery=False)
        
        self._create_metric_row(content, "Battery", "--", "%", is_battery=True)
        
        # Temperature row with alert icon
        self._create_temperature_row(content)
        
        # TTD row
        self.ttd_row = tk.Frame(content, bg=DARK_BG_MED)
        self.ttd_row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(
            self.ttd_row, text="Time to Dead:",
            bg=DARK_BG_MED, fg=DARK_FG_SEC, font=("Segoe UI", 9), width=14, anchor=tk.W
        ).pack(side=tk.LEFT)
        self.ttd_label = tk.Label(
            self.ttd_row, text="--",
            bg=DARK_BG_MED, fg=DARK_FG_MUTED, font=("Segoe UI", 9, "bold")
        )
        self.ttd_label.pack(side=tk.LEFT, padx=5)
        
        # Uptime row
        self.uptime_row = tk.Frame(content, bg=DARK_BG_MED)
        self.uptime_row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(
            self.uptime_row, text="Uptime:",
            bg=DARK_BG_MED, fg=DARK_FG_SEC, font=("Segoe UI", 9), width=14, anchor=tk.W
        ).pack(side=tk.LEFT)
        self.uptime_label = tk.Label(
            self.uptime_row, text="--",
            bg=DARK_BG_MED, fg=DARK_FG_MUTED, font=("Segoe UI", 9)
        )
        self.uptime_label.pack(side=tk.LEFT, padx=5)
        
        # Stale data overlay (applied on top)
        self.stale_overlay = tk.Frame(self.frame, bg="#584011")
        self.stale_label = tk.Label(
            self.stale_overlay,
            text="STALE DATA",
            bg="#584011",
            fg="#fad2c9",
            font=("Segoe UI", 14, "bold"),
        )
        self.stale_label.pack(expand=True, fill=tk.BOTH)
        self.stale_overlay.place_forget()
        
        # Record initial packet
        self.record_packet(time.time())
        self._draw_status_led()
        self.update_temperature_state(status.temperature_c)
    
    def _create_metric_row(self, parent: tk.Frame, label: str, value: str, unit: str, is_battery: bool = False):
        row = tk.Frame(parent, bg=DARK_BG_MED)
        row.pack(fill=tk.X, pady=3)
        
        tk.Label(
            row, text=label,
            bg=DARK_BG_MED, fg=DARK_FG_SEC, font=("Segoe UI", 9), width=10, anchor=tk.W
        ).pack(side=tk.LEFT)
        
        val_label = tk.Label(
            row, text=f"{value} {unit}",
            bg=DARK_BG_MED, fg=DARK_FG, font=("Segoe UI", 9, "bold")
        )
        val_label.pack(side=tk.LEFT, padx=5)
        
        # Visual bar (canvas)
        canvas = tk.Canvas(
            row, width=160, height=10,
            bg="#2a2e33", highlightthickness=0,
            borderwidth=0
        )
        canvas.pack(side=tk.LEFT, padx=8)
        
        track = canvas.create_rectangle(1, 2, 159, 8, fill="#2a2e33", outline=DARK_BG, width=0)
        fill = canvas.create_rectangle(1, 2, 1, 8, fill=GREEN_OK, outline="", width=0)
        value_text = canvas.create_text(
            158, 5, text=f"{value}{unit}", anchor=tk.E,
            fill=DARK_FG_SEC, font=("Segoe UI", 8, "bold")
        )
        
        self.metric_bars[label] = {
            "canvas": canvas,
            "track": track,
            "fill": fill,
            "value_text": value_text,
            "is_battery": is_battery,
            "unit": unit,
        }
    
    def _create_temperature_row(self, parent: tk.Frame):
        row = tk.Frame(parent, bg=DARK_BG_MED)
        row.pack(fill=tk.X, pady=3)
        
        tk.Label(
            row, text="Temp",
            bg=DARK_BG_MED, fg=DARK_FG_SEC, font=("Segoe UI", 9), width=10, anchor=tk.W
        ).pack(side=tk.LEFT)
        
        self.temp_value = tk.Label(
            row, text="--°C",
            bg=DARK_BG_MED, fg=DARK_FG, font=("Segoe UI", 9, "bold")
        )
        self.temp_value.pack(side=tk.LEFT, padx=5)
        
        # Animated thermometer icon
        self.temp_icon = tk.Canvas(
            row, width=20, height=20,
            bg=DARK_BG_MED, highlightthickness=0
        )
        self.temp_icon.pack(side=tk.LEFT, padx=8)
        
        # Temperature alert badge (initially hidden)
        self.temp_badge = tk.Label(
            row, text="⚠", bg=DARK_BG_MED, fg=AMBER_WARN,
            font=("Segoe UI", 9, "bold")
        )
        self.temp_badge.pack(side=tk.LEFT, padx=4)
        self.temp_badge.pack_forget()
        
        self.temperature_widgets = {
            "value": self.temp_value,
            "icon": self.temp_icon,
            "badge": self.temp_badge,
        }
    
    def _draw_status_led(self):
        self.status_led.delete("led")
        color = GREEN_OK if self.status.online else RED_ERR
        self.status_led.create_oval(2, 2, 12, 12, fill=color, outline="#ffffff", width=1, tags="led")
        # Inner highlight for depth
        self.status_led.create_oval(4, 4, 8, 8, fill="#ffffff", outline="", tags="led")
    
    def _draw_temperature_icon(self):
        c = self.temp_icon
        c.delete("all")
        temp = self.status.temperature_c or 0
        
        if temp >= self.TEMPERATURE_CRITICAL_THRESHOLD_C:
            fill = RED_ERR
        elif temp >= self.TEMPERATURE_WARNING_THRESHOLD_C:
            fill = AMBER_WARN
        else:
            fill = GREEN_OK
        
        # Thermometer bulb
        c.create_oval(6, 10, 14, 18, fill=fill, outline="#ffffff", width=1)
        # Tube
        c.create_rectangle(9, 4, 11, 10, fill=fill, outline="#ffffff", width=1)
        # Mercury level
        level = min(1.0, max(0.0, temp / 60.0))
        h = 4 + (6 - 4) * (1 - level)
        c.create_rectangle(9, h, 11, 10, fill=fill, outline="")
    
    def update_temperature_state(self, temp_c: Optional[float]):
        if temp_c is None:
            self.temp_value.configure(text="--°C", fg=DARK_FG_MUTED)
            self.temp_badge.pack_forget()
            self.temperature_alert_state = "normal"
            self._stop_temperature_shake()
            return
        
        self.temp_value.configure(text=f"{temp_c:.1f}°C")
        
        if temp_c >= self.TEMPERATURE_CRITICAL_THRESHOLD_C:
            self.temp_value.configure(fg=RED_ERR)
            self.temp_badge.configure(text="⚠ CRIT", fg=RED_ERR)
            self.temp_badge.pack(side=tk.LEFT, padx=4)
            self.temperature_alert_state = "critical"
            self._start_temperature_shake()
        elif temp_c >= self.TEMPERATURE_WARNING_THRESHOLD_C:
            self.temp_value.configure(fg=AMBER_WARN)
            self.temp_badge.configure(text="⚠ WARN", fg=AMBER_WARN)
            self.temp_badge.pack(side=tk.LEFT, padx=4)
            self.temperature_alert_state = "warning"
            self._stop_temperature_shake()
        else:
            self.temp_value.configure(fg=GREEN_OK)
            self.temp_badge.pack_forget()
            self.temperature_alert_state = "normal"
            self._stop_temperature_shake()
        
        self._draw_temperature_icon()
    
    def _start_temperature_shake(self):
        self._stop_temperature_shake()
        self._temperature_shake_tick()
    
    def _temperature_shake_tick(self):
        self.temperature_shake_phase = (self.temperature_shake_phase + 1) % 4
        offset = [0, 2, 0, -2][self.temperature_shake_phase]
        self.temp_icon.place_configure(x=offset)
        self.temperature_shake_job = self.temp_icon.after(
            self.TEMPERATURE_SHAKE_INTERVAL_MS, self._temperature_shake_tick
        )
    
    def _stop_temperature_shake(self):
        if self.temperature_shake_job:
            try:
                self.temp_icon.after_cancel(self.temperature_shake_job)
            except Exception:
                pass
            self.temperature_shake_job = None
        self.temp_icon.place_configure(x=0)
    
    def record_packet(self, timestamp: float):
        if self.last_packet_timestamp is not None:
            interval = timestamp - self.last_packet_timestamp
            if 0.05 < interval < 5.0:
                self.packet_intervals.append(interval)
        self.last_packet_timestamp = timestamp
        self.last_seen_status_timestamp = timestamp
    
    def update_time_to_dead_display(self):
        if not self.packet_intervals:
            self.ttd_label.configure(text="--", fg=DARK_FG_MUTED)
            return
        
        avg_interval = sum(self.packet_intervals) / len(self.packet_intervals)
        time_since_last = time.time() - (self.last_packet_timestamp or time.time())
        ttd = self.STALE_DATA_TIMEOUT_SECONDS - time_since_last
        
        if ttd <= 0:
            self.ttd_label.configure(text="0.00s", fg=RED_ERR)
        elif ttd < 0.25:
            self.ttd_label.configure(text=f"{ttd:.2f}s", fg=RED_ERR)
        elif ttd < 0.75:
            self.ttd_label.configure(text=f"{ttd:.2f}s", fg=AMBER_WARN)
        else:
            self.ttd_label.configure(text=f"{ttd:.2f}s", fg=GREEN_OK)
    
    def update_uptime_display(self, seconds: Optional[int]):
        if seconds is None:
            self.uptime_label.configure(text="--", fg=DARK_FG_MUTED)
            return
        
        if seconds < 60:
            text = f"{seconds}s"
        elif seconds < 3600:
            text = f"{seconds//60}m {seconds%60}s"
        elif seconds < 86400:
            text = f"{seconds//3600}h {(seconds%3600)//60}m"
        else:
            text = f"{seconds//86400}d"
        self.uptime_label.configure(text=text, fg=DARK_FG)
    
    def _apply_freshness_state(self):
        is_stale = False
        if self.last_seen_status_timestamp is not None:
            elapsed = time.time() - self.last_seen_status_timestamp
            is_stale = elapsed > self.STALE_DATA_TIMEOUT_SECONDS
        
        if is_stale != self.is_stale:
            self.is_stale = is_stale
            if is_stale:
                self.stale_overlay.place(x=0, y=0, relwidth=1, relheight=1)
                self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
            else:
                self.stale_overlay.place_forget()
                self.overlay.place_forget()
    
    def _battery_color(self, pct: Optional[float]) -> str:
        if pct is None:
            return DARK_FG_MUTED
        if pct >= 50:
            return GREEN_OK
        if pct >= 20:
            return AMBER_WARN
        return RED_ERR
    
    def _metric_to_percent(self, value: Optional[float], min_v: float, max_v: float) -> float:
        if value is None:
            return 0.0
        return max(0.0, min(1.0, (value - min_v) / (max_v - min_v)))
    
    def _update_visual_bar(self, label: str, percent: float, color: str):
        bar = self.metric_bars.get(label)
        if not bar:
            return
        c = bar["canvas"]
        w = 158
        fill_w = 1 + int(w * percent)
        c.coords(bar["fill"], 1, 2, fill_w, 8)
        c.itemconfig(bar["fill"], fill=color)
        val = bar.get("value", "--")
        unit = bar.get("unit", "")
        c.itemconfig(bar["value_text"], text=f"{val}{unit}", fill=color)
    
    def _draw_status_led(self):
        self.status_led.delete("led")
        color = GREEN_OK if self.status.online else RED_ERR
        self.status_led.create_oval(2, 2, 12, 12, fill=color, outline="#ffffff", width=1, tags="led")
        self.status_led.create_oval(4, 4, 8, 8, fill="#ffffff", outline="", tags="led")


class BeaconMonitorGUI:
    """Main beacon monitoring dashboard - Industrial Dark Theme"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Beacon Monitor - Live Dashboard")
        self.root.geometry("1400x900")
        
        # Industrial dark theme
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self._setup_styles(style)
        
        self.root.configure(bg=DARK_BG)
        
        # Failsafe annunciator (top banner)
        self.annunciator = FailsafeAnnunciator(self.root, max_alarms=4)
        self.annunciator.pack(fill=tk.X, side=tk.TOP)

        self.beacons_config: Dict[str, Dict[str, Any]] = {}
        self.beacon_status: Dict[str, BeaconStatus] = {}
        self.beacon_cards: Dict[str, BeaconCard] = {}
        self.config_file = PROJECT_ROOT / "config" / "beacons_config.json"
        self.monitoring_active = False
        self.update_thread: Optional[threading.Thread] = None
        self.poll_interval = 2.0  # Poll every 2 seconds
        
        # Load configuration
        self.load_config()

        if not self.beacons_config:
            self.beacons_config = self._default_beacon_configs()
            logger.info(
                "Beacon configuration missing or empty; showing %d offline placeholders.",
                len(self.beacons_config),
            )
        
        # Initialize beacon status
        for beacon_id in self.beacons_config.keys():
            config = self.beacons_config[beacon_id]
            self.beacon_status[beacon_id] = BeaconStatus(
                beacon_id=beacon_id,
                ip_address=config.get("ip_address", "0.0.0.0"),
                port=config.get("port", 5000),
                display_name=config.get("display_name"),
            )
        
        # Setup GUI
        self._create_ui()
        self._start_stale_watchdog()
        self._start_monitoring()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def _setup_styles(self, style: ttk.Style):
        """Setup ttk styles for industrial dark theme"""
        # Base colours
        style.configure(".",
            background=DARK_BG,
            foreground=DARK_FG,
            fieldbackground=DARK_BG_MED,
            selectbackground=DARK_BG_LIGHT,
            selectforeground=DARK_FG,
            bordercolor=DARK_BG,
            lightcolor=DARK_BG_MED,
            darkcolor=DARK_BG_MED,
        )

        style.configure("TFrame", background=DARK_BG)
        style.configure("TLabelframe", background=DARK_BG, foreground=DARK_FG_SEC)
        style.configure("TLabelframe.Label", background=DARK_BG, foreground=DARK_FG_SEC, font=("Segoe UI", 9, "bold"))

        style.configure("TLabel", background=DARK_BG, foreground=DARK_FG, font=("Segoe UI", 9))
        
        style.configure("TButton",
            font=("Segoe UI", 9), padding=6,
            background=DARK_BG_MED, foreground=DARK_FG,
            bordercolor=DARK_BG, focuscolor=DARK_BG,
        )
        style.map("TButton",
            background=[("active", DARK_BG_LIGHT), ("pressed", DARK_BG)],
            foreground=[("active", DARK_FG), ("disabled", DARK_FG_MUTED)],
        )
        
        style.configure("Primary.TButton",
            font=("Segoe UI", 10, "bold"), padding=10,
            background=BLUE_LINK, foreground=DARK_FG,
        )
        style.map("Primary.TButton",
            background=[("active", "#3a8fc2"), ("pressed", "#1e5a8a")],
        )
        
        style.configure("Treeview",
            background=DARK_BG_MED, foreground=DARK_FG,
            fieldbackground=DARK_BG_MED,
            bordercolor=DARK_BG_MED, lightcolor=DARK_BG_MED, darkcolor=DARK_BG_MED,
            font=("Segoe UI", 9), rowheight=24,
        )
        style.map("Treeview",
            background=[("selected", DARK_BG_LIGHT)],
            foreground=[("selected", DARK_FG)],
        )
        style.configure("Treeview.Heading",
            background=DARK_BG, foreground=DARK_FG_SEC,
            font=("Segoe UI", 9, "bold"), bordercolor=DARK_BG,
        )
        
        style.configure("Vertical.TScrollbar",
            background=DARK_BG_MED, troughcolor=DARK_BG,
            bordercolor=DARK_BG, arrowcolor=DARK_FG,
            darkcolor=DARK_BG_MED, lightcolor=DARK_BG_MED,
        )
        style.configure("Horizontal.TScrollbar",
            background=DARK_BG_MED, troughcolor=DARK_BG,
            bordercolor=DARK_BG, arrowcolor=DARK_FG,
            darkcolor=DARK_BG_MED, lightcolor=DARK_BG_MED,
        )
        
        style.configure("TProgressbar",
            background=GREEN_OK, troughcolor=DARK_BG_MED,
            bordercolor=DARK_BG, lightcolor=GREEN_OK, darkcolor=GREEN_OK,
        )
    
    def _create_ui(self):
        """Create the main UI"""
        # Header
        header = tk.Frame(self.root, bg=DARK_BG_MED, height=60)
        header.pack(fill=tk.X, padx=0, pady=0)
        header.pack_propagate(False)
        
        title = tk.Label(
            header,
            text="BEACON MONITOR - Live Dashboard",
            bg=DARK_BG_MED,
            fg=GREEN_OK,
            font=("Segoe UI", 16, "bold")
        )
        title.pack(side=tk.LEFT, padx=20, pady=15)
        
        # Status summary
        self.summary_var = tk.StringVar(value="Initializing...")
        summary_label = tk.Label(
            header,
            textvariable=self.summary_var,
            bg=DARK_BG_MED,
            fg=AMBER_WARN,
            font=("Segoe UI", 11)
        )
        summary_label.pack(side=tk.RIGHT, padx=20, pady=15)
        
        self.link_summary_var = tk.StringVar(value="Telemetry links: checking...")
        link_summary = tk.Label(
            header,
            textvariable=self.link_summary_var,
            bg=DARK_BG_MED,
            fg=DARK_FG_SEC,
            font=("Segoe UI", 9)
        )
        link_summary.pack(side=tk.RIGHT, padx=20, pady=15)
        
        # Main content area with scrollable grid
        main_frame = tk.Frame(self.root, bg=DARK_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(main_frame, bg=DARK_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=DARK_BG)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.cards_frame = scrollable_frame
        self._layout_cards()
        
        # Footer with controls
        footer = tk.Frame(self.root, bg=DARK_BG_MED, height=50)
        footer.pack(fill=tk.X, padx=10, pady=10)
        footer.pack_propagate(False)
        
        button_frame = tk.Frame(footer, bg=DARK_BG_MED)
        button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)
        
        ttk.Button(
            button_frame, text="Refresh Now",
            command=self._trigger_manual_refresh,
            style="Primary.TButton"
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Open Connection Status",
            command=self._open_connection_status
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, text="Configure Beacons",
            command=self._open_beacon_config
        ).pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(
            footer,
            text="Monitoring active",
            bg=DARK_BG_MED,
            fg=GREEN_OK,
            font=("Segoe UI", 9)
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)
    
    def _layout_cards(self):
        """Arrange beacon cards in a responsive grid"""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        
        n = len(self.beacons_config)
        if n == 0:
            return
        
        # Calculate grid dimensions
        cols = min(4, max(1, int(math.ceil(math.sqrt(n)))))
        rows = int(math.ceil(n / cols))
        
        grid_frame = tk.Frame(self.cards_frame, bg=DARK_BG)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        beacon_items = list(self.beacons_config.items())
        
        for idx, (beacon_id, config) in enumerate(beacon_items):
            row = idx // cols
            col = idx % cols
            
            cell = tk.Frame(grid_frame, bg=DARK_BG)
            cell.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            
            status = self.beacon_status.get(beacon_id)
            if status is None:
                status = BeaconStatus(
                    beacon_id=beacon_id,
                    ip_address=config.get("ip_address", "0.0.0.0"),
                    port=config.get("port", 5000),
                    display_name=config.get("display_name"),
                )
                self.beacon_status[beacon_id] = status
            
            card = BeaconCard(cell, beacon_id, status)
            self.beacon_cards[beacon_id] = card
        
        # Configure grid weights
        for i in range(cols):
            grid_frame.columnconfigure(i, weight=1)
        for i in range(rows):
            grid_frame.rowconfigure(i, weight=1)
    
    def _update_cards(self):
        """Update beacon cards with latest status"""
        online_count = 0
        for beacon_id, card in self.beacon_cards.items():
            status = self.beacon_status.get(beacon_id)
            if status:
                card.status = status
                card.record_packet(status.last_update)
                card._apply_freshness_state()
                card.update_temperature_state(status.temperature_c)
                card.update_time_to_dead_display()
                card._draw_status_led()
                card.update_uptime_display(status.uptime_seconds)
                
                # Update metric bars
                card._update_visual_bar("Battery", card._metric_to_percent(status.battery_percent, 0, 100), card._battery_color(status.battery_percent))
                card._update_visual_bar("Voltage", card._metric_to_percent(status.battery_voltage, 3.0, 4.2), BLUE_LINK)
                card._update_visual_bar("Current", card._metric_to_percent(status.current_amperage, 0, 2.0), AMBER_WARN)
                card._update_visual_bar("Fan", card._metric_to_percent(status.fan_speed_rpm, 0, 3000), GREEN_OK)
                card._update_visual_bar("LED", card._metric_to_percent(status.led_brightness, 0, 100), BLUE_LINK)
                
                if status.online:
                    online_count += 1
        
        total_count = len(self.beacon_cards)
        self.summary_var.set(f"Beacons: {online_count}/{total_count} ONLINE")
        
        if self.link_summary_var:
            offline_names = [
                self.beacon_status[bid].display_name or bid
                for bid, s in self.beacon_status.items()
                if not s.online
            ]
            if offline_names:
                self.link_summary_var.set(f"Offline: {', '.join(offline_names)}")
            else:
                self.link_summary_var.set("All beacons online ✓")
    
    def _trigger_manual_refresh(self):
        self.annunciator.scroll_message("Manual refresh triggered", "info")
        threading.Thread(target=self._poll_all_beacons, daemon=True).start()
    
    def _open_connection_status(self):
        # Reuse the connection status window
        try:
            from launcher_gui import ConnectionStatusWindow  # type: ignore
        except Exception as exc:
            logger.error("Cannot open connection status: %s", exc)
            return
        
        class _LauncherProxy:
            def __init__(self, root: tk.Tk):
                self.root = root
            
            @staticmethod
            def log_to_terminal(message: str):
                logger.info("[ConnectionStatus] %s", message)
        
        roof_config = PROJECT_ROOT / "config" / "roof_array_config.json"
        front_config = PROJECT_ROOT / "config" / "front_array_config.json"
        
        try:
            launcher_proxy = _LauncherProxy(self.root)
            ConnectionStatusWindow(
                launcher=launcher_proxy,
                roof_config_path=str(roof_config),
                front_config_path=str(front_config),
                launch_callback=None,
                modal=False,
                allow_launch=False,
            )
        except Exception as exc:
            logger.error("Unable to open connection status: %s", exc)
    
    def _open_beacon_config(self):
        try:
            from control.beacon_config_gui import BeaconConfigGUI  # type: ignore
        except Exception as exc:
            logger.error("Cannot open beacon config: %s", exc)
            return
        
        BeaconConfigGUI().run()
    
    def load_config(self):
        """Load beacon configuration from JSON file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.beacons_config = json.load(f)
            else:
                self.beacons_config = {}
        except Exception as e:
            logger.error("Failed to load beacon config: %s", e)
            self.beacons_config = {}
    
    def _default_beacon_configs(self) -> Dict[str, Dict[str, Any]]:
        return {
            "BEACON-01": {
                "ip_address": "192.168.1.101",
                "port": 5000,
                "display_name": "Stage Left",
            },
            "BEACON-02": {
                "ip_address": "192.168.1.102",
                "port": 5000,
                "display_name": "Stage Center",
            },
            "BEACON-03": {
                "ip_address": "192.168.1.103",
                "port": 5000,
                "display_name": "Stage Right",
            },
            "BEACON-04": {
                "ip_address": "192.168.1.104",
                "port": 5000,
                "display_name": "FOH",
            },
        }
    
    def _start_monitoring(self):
        """Start background monitoring thread"""
        self.monitoring_active = True
        self.update_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.update_thread.start()
        # Initial poll
        threading.Thread(target=self._poll_all_beacons, daemon=True).start()
    
    def _monitoring_loop(self):
        """Background loop that polls beacons"""
        while self.monitoring_active:
            self._poll_all_beacons()
            time.sleep(self.poll_interval)
    
    def _poll_all_beacons(self):
        """Poll all configured beacons"""
        if fetch_status is None:
            return
        
        results = []
        for beacon_id, config in self.beacons_config.items():
            ip = config.get("ip_address", "0.0.0.0")
            port = config.get("port", 5000)
            try:
                status = fetch_status(ip, port)
                if status:
                    status.beacon_id = beacon_id
                    status.display_name = config.get("display_name")
                    results.append((beacon_id, status))
            except Exception as e:
                logger.debug("Beacon %s poll failed: %s", beacon_id, e)
        
        if results:
            self.root.after(0, self._apply_poll_results, results)
    
    def _apply_poll_results(self, results: List[Tuple[str, BeaconStatus]]):
        for beacon_id, status in results:
            self.beacon_status[beacon_id] = status
        self._update_cards()
    
    def _start_stale_watchdog(self):
        """Watchdog to update staleness indicators"""
        def watchdog_tick():
            if self.monitoring_active:
                for card in self.beacon_cards.values():
                    card._apply_freshness_state()
                    card.update_time_to_dead_display()
                self.root.after(250, watchdog_tick)
        self.root.after(250, watchdog_tick)
    
    def on_closing(self):
        """Clean shutdown"""
        self.monitoring_active = False
        self.root.destroy()
    
    def run(self):
        """Run the GUI main loop"""
        self.root.mainloop()


if __name__ == "__main__":
    app = BeaconMonitorGUI()
    app.run()
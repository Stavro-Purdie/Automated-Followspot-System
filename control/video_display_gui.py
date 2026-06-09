#!/usr/bin/env python3
"""
Operator-facing dashboard for the live multi-camera followspot feed.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
import cv2
import numpy as np
from PIL import Image, ImageTk
import threading
import time
import logging
from typing import Optional, List, Dict, Tuple, Any
import importlib
import json
import sys
import subprocess
import webbrowser
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def ensure_window_fits_content(
    window: tk.Toplevel | tk.Tk,
    *,
    min_width: int = 900,
    min_height: int = 600,
    padding: int = 48,
    center: bool = True,
) -> None:
    """Resize a window so that all widgets are visible without manual resizing."""

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

    try:
        default_font = tkfont.nametofont("TkDefaultFont").copy()
        base_size = max(int(default_font.cget("size")), 10)
        body_font = (default_font.cget("family"), base_size)
        heading_font = (default_font.cget("family"), base_size + 1, "bold")

        style.configure(".", font=body_font)
        style.configure("TButton", padding=(10, 6))
        style.configure("TEntry", padding=(6, 4))
        style.configure("TCombobox", padding=(6, 4))
        style.configure("TLabelframe", padding=(10, 8))
        style.configure("TLabelframe.Label", font=heading_font)
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=heading_font)
        style.configure("TNotebook.Tab", padding=(12, 6))
    except tk.TclError:
        pass


try:
    # Data fusion for IR + ReID
    from fusion.data_fusion import DataFusion  # type: ignore
except Exception:
    try:
        DataFusion = importlib.import_module('fusion.data_fusion').DataFusion  # type: ignore
    except Exception:
        DataFusion = None  # type: ignore

try:
    # Optional import; GUI can run without ReID runner
    from reid_runner import ReIDRunner  # type: ignore
except Exception:
    try:
        ReIDRunner = importlib.import_module('control.reid_runner').ReIDRunner  # type: ignore
    except Exception:
        ReIDRunner = None  # type: ignore

try:
    from launcher_gui import get_adaptive_colors, get_system_appearance
except Exception:
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

try:
    from demo_reid_runner import DemoReIDRunner  # type: ignore
except Exception:
    try:
        DemoReIDRunner = importlib.import_module('control.demo_reid_runner').DemoReIDRunner  # type: ignore
    except Exception:
        DemoReIDRunner = None  # type: ignore

logger = logging.getLogger("video_display_gui")

class VideoDisplayGUI:
    """Handles live playback, overlays, and operator controls in one place."""

    def __init__(self, camera_manager, reid_runner: Optional[Any] = None):
        self.camera_manager = camera_manager
        self.root = tk.Tk()
        self.root.title("Multi-Camera IR Beacon Tracker")
        self.root.geometry("1200x800")
        self.root.configure(bg="SystemButtonFace")
        
        # Use native OS theme
        style = ttk.Style()
        set_native_theme(style)
        
        # Video display variables
        self.video_label = None
        self.current_frame = None
        self.display_thread = None
        self.running = False
        
        # IR detection settings
        self.ir_threshold = tk.IntVar(value=200)
        self.show_coordinates = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.show_beacons = tk.BooleanVar(value=True)
        self.show_raw_overlay = tk.BooleanVar(value=False)

        # Fused overlay settings
        self.show_fused_overlay = tk.BooleanVar(value=True)
        self.fused_count_var = tk.StringVar(value="Fused: 0")
        self.lead_target_info: Optional[Dict[str, Any]] = None
        self.last_ir_beacons: List[Dict[str, Any]] = []
        self.last_fused_positions: List[Dict[str, Any]] = []

        # Front ReID overlay settings
        self.show_reid_overlay = tk.BooleanVar(value=True)
        self.front_status_var = tk.StringVar(value="Front: idle")
        self.front_video_label = None
        self.front_display_image = None
        self.front_placeholder_image = None
        self.front_last_seen: float = 0.0
        self.front_missing_since: Optional[float] = time.time()
        
        # Animation and transition settings
        self.frame_fade_alpha = 1.0
        self.placeholder_pulse_phase = 0.0
        self.animation_speed = 0.05  # Fade speed (0.0-1.0 per frame)
        self.last_frame_timestamp = time.time()
        
        self.reid_runner = reid_runner
        if self.reid_runner is None:
            if getattr(self.camera_manager, "demo_mode", False) and DemoReIDRunner is not None:
                try:
                    self.reid_runner = DemoReIDRunner()
                    self.front_status_var.set("Front: demo")
                except Exception:
                    self.reid_runner = None
            elif ReIDRunner is not None:
                try:
                    self.reid_runner = ReIDRunner()
                except Exception:
                    self.reid_runner = None

        self._start_reid_runner()

        # Initialize Data Fusion (uses front config)
        self.fusion = None
        try:
            if DataFusion is not None:
                # Prefer config from reid_runner if available
                cfg = getattr(self.reid_runner, 'config', None)
                if not isinstance(cfg, dict):
                    # Load from default front config path relative to repo
                    control_dir = Path(__file__).parent
                    front_cfg_path = control_dir.parent / "config" / "front_array_config.json"
                    with open(front_cfg_path, 'r') as f:
                        cfg = json.load(f)
                self.fusion = DataFusion(cfg)
        except Exception as e:
            logger.warning(f"Could not initialize DataFusion: {e}")
        
        # Statistics
        self.fps_var = tk.StringVar(value="FPS: 0.0")
        self.beacon_count_var = tk.StringVar(value="Beacons: 0")
        self.frame_size_var = tk.StringVar(value="Frame: 0x0")
        
        # Help window reference
        self.help_window = None
        
        self.setup_menu()
        self.setup_ui()
        self.setup_bindings()
        
    def setup_menu(self):
        """Create a friendly menu for hopping between tools and toggling overlays."""
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Screenshot", command=self.save_screenshot)
        file_menu.add_command(label="Reset View", command=self.reset_view)
        file_menu.add_separator()
        file_menu.add_command(label="Open Launcher", command=self._open_launcher)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Show Coordinates", variable=self.show_coordinates)
        view_menu.add_checkbutton(label="Show Grid", variable=self.show_grid)
        view_menu.add_checkbutton(label="Show IR Beacons", variable=self.show_beacons)
        view_menu.add_checkbutton(label="Show Fused Targets", variable=self.show_fused_overlay)
        view_menu.add_checkbutton(label="Show Front Overlay", variable=self.show_reid_overlay)
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Open Camera Configurator",
            command=lambda: self._launch_tool("camera_config_gui.py", "Camera Configurator"),
        )
        tools_menu.add_command(
            label="Open ReID Configurator",
            command=lambda: self._launch_tool("reid_configurator.py", "ReID Configurator"),
        )
        tools_menu.add_command(
            label="Open Identity Configurator",
            command=lambda: self._launch_tool("identity_configurator.py", "Identity Configurator"),
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Beacon Configuration & Monitor",
            command=lambda: self._launch_tool("beacon_config_gui.py", "Beacon Config"),
        )
        tools_menu.add_command(
            label="Beacon Live Monitor",
            command=lambda: self._launch_tool("beacon_monitor_gui.py", "Beacon Monitor"),
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="Connection Status", command=self.show_connection_status)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_help_window)
        help_menu.add_command(label="Diagnostics Panel", command=self.show_help_window)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_separator()
        help_menu.add_command(
            label="Project README",
            command=lambda: webbrowser.open_new_tab(
                "https://github.com/Stavro-Purdie/Automated-Followspot-System"
            ),
        )
        help_menu.add_command(
            label="Report Issue",
            command=lambda: webbrowser.open_new_tab(
                "https://github.com/Stavro-Purdie/Automated-Followspot-System/issues/new/choose"
            ),
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _start_reid_runner(self) -> None:
        runner = self.reid_runner
        if runner is None:
            return
        start_fn = getattr(runner, "start", None)
        if callable(start_fn):
            try:
                start_fn()
            except Exception as exc:
                logger.warning("Could not start ReID runner: %s", exc)

    def _launch_tool(self, script_name: str, description: str) -> None:
        script_path = Path(__file__).resolve().parent / script_name
        if not script_path.exists():
            messagebox.showerror("Missing Tool", f"{description} not found at:\n{script_path}")
            return
        try:
            subprocess.Popen([sys.executable, str(script_path)])
        except Exception as exc:
            messagebox.showerror("Launch Failed", f"Could not open {description}:\n{exc}")

    def _open_launcher(self) -> None:
        launcher_path = PROJECT_ROOT / "launcher_gui.py"
        if not launcher_path.exists():
            messagebox.showerror("Launcher Missing", "launcher_gui.py could not be found.")
            return
        try:
            subprocess.Popen([sys.executable, str(launcher_path)])
        except Exception as exc:
            messagebox.showerror("Launcher Error", f"Failed to open launcher:\n{exc}")

    def show_connection_status(self) -> None:
        """Open the connection status window to inspect camera reachability."""
        try:
            from launcher_gui import ConnectionStatusWindow  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive import guard
            messagebox.showerror(
                "Connection Status Unavailable",
                f"Could not load connection status window:\n{exc}",
            )
            return

        class _LauncherProxy:
            def __init__(self, root: tk.Tk):
                self.root = root

            @staticmethod
            def log_to_terminal(message: str) -> None:
                logger.info("[ConnectionStatus] %s", message)

        config_root = PROJECT_ROOT / "config"
        roof_path = getattr(self.camera_manager, "config_file", str(config_root / "roof_array_config.json"))
        roof_config = Path(roof_path)
        if not roof_config.is_absolute():
            roof_config = (PROJECT_ROOT / roof_config).resolve()
        if not roof_config.exists():
            roof_config = config_root / "roof_array_config.json"

        front_config = config_root / "front_array_config.json"

        try:
            launcher_proxy: Any = _LauncherProxy(self.root)
            ConnectionStatusWindow(  # type: ignore[arg-type]
                launcher=launcher_proxy,
                roof_config_path=str(roof_config),
                front_config_path=str(front_config),
                launch_callback=None,
                modal=False,
                allow_launch=False,
            )
        except Exception as exc:  # pragma: no cover - UI fallback
            messagebox.showerror(
                "Connection Status Error",
                f"Unable to open connection status window:\n{exc}",
            )
            return
        
    def setup_ui(self):
        """Assemble the main layout: controls on the left, video wall on the right."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Control panel (left side)
        self.setup_control_panel(main_frame)
        
        # Video display area (right side)
        self.setup_video_display(main_frame)
        
        # Status bar (bottom)
        self.setup_status_bar(main_frame)
        ensure_window_fits_content(self.root, min_width=1200, min_height=820, padding=80, center=True)
        
    def setup_control_panel(self, parent):
        """Layout the tactile controls operators reach for during a show."""
        control_frame = ttk.LabelFrame(parent, text="Controls", padding="10")
        control_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ttk.Label(control_frame, text="IR Threshold:").grid(row=0, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(control_frame)
        threshold_frame.grid(row=1, column=0, sticky="we", pady=5)

        threshold_scale = ttk.Scale(
            threshold_frame,
            from_=0,
            to=255,
            variable=self.ir_threshold,
            orient=tk.HORIZONTAL,
        )
        threshold_scale.grid(row=0, column=0, sticky="we")
        threshold_frame.columnconfigure(0, weight=1)

        threshold_entry = ttk.Entry(threshold_frame, textvariable=self.ir_threshold, width=5)
        threshold_entry.grid(row=0, column=1, padx=(5, 0))

        ttk.Label(control_frame, text="Display Options:").grid(row=2, column=0, sticky=tk.W, pady=(20, 5))

        ttk.Checkbutton(
            control_frame,
            text="Show Coordinates",
            variable=self.show_coordinates,
        ).grid(row=3, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(
            control_frame,
            text="Show Grid",
            variable=self.show_grid,
        ).grid(row=4, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(
            control_frame,
            text="Show IR Beacons",
            variable=self.show_beacons,
        ).grid(row=5, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(
            control_frame,
            text="Show Raw Overlay",
            variable=self.show_raw_overlay,
        ).grid(row=6, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(
            control_frame,
            text="Show Fused Targets",
            variable=self.show_fused_overlay,
        ).grid(row=7, column=0, sticky=tk.W, pady=2)

        ttk.Label(control_frame, text="Front ReID Overlay:").grid(row=8, column=0, sticky=tk.W, pady=(20, 5))
        ttk.Checkbutton(
            control_frame,
            text="Show Front Camera Overlay",
            variable=self.show_reid_overlay,
        ).grid(row=9, column=0, sticky=tk.W, pady=2)

        stats_frame = ttk.LabelFrame(control_frame, text="Statistics", padding="10")
        stats_frame.grid(row=10, column=0, sticky="we", pady=(20, 0))

        ttk.Label(stats_frame, textvariable=self.fps_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.beacon_count_var).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.frame_size_var).grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.fused_count_var).grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.front_status_var).grid(row=4, column=0, sticky=tk.W, pady=2)

        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=11, column=0, sticky="we", pady=(20, 0))

        ttk.Button(button_frame, text="Save Screenshot", command=self.save_screenshot).grid(row=0, column=0, pady=5)
        ttk.Button(button_frame, text="Reset View", command=self.reset_view).grid(row=1, column=0, pady=5)
        
    def setup_video_display(self, parent):
        """Setup the video display area"""
        video_frame = ttk.LabelFrame(parent, text="Video Feeds", padding="10")
        video_frame.grid(row=0, column=1, sticky="nsew")

        # IR Composite view (top)
        ir_title = ttk.Label(video_frame, text="Roof IR Composite", anchor=tk.W)
        ir_title.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.video_label = ttk.Label(
            video_frame,
            text="No video feed available",
            background="black",
            foreground="white",
        )
        self.video_label.grid(row=1, column=0, sticky="nsew")

        # Front ReID view (bottom)
        front_title = ttk.Label(video_frame, text="Front ReID Overlay", anchor=tk.W)
        front_title.grid(row=2, column=0, sticky="w", pady=(15, 5))
        self.front_video_label = ttk.Label(
            video_frame,
            text="Front camera not available",
            background="black",
            foreground="white",
        )
        self.front_video_label.grid(row=3, column=0, sticky="nsew")

        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(1, weight=3)
        video_frame.rowconfigure(3, weight=1)

        # Mouse click handler for coordinates on IR view
        self.video_label.bind("<Button-1>", self.on_video_click)
        
    def setup_status_bar(self, parent):
        """Setup the status bar with error highlighting"""
        # Create a tk.Frame instead of ttk.Frame for background color control
        status_frame = tk.Frame(parent, bg="#1a1a1a", height=32)
        status_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=(10, 0), padx=0)
        
        self.status_var = tk.StringVar(value="Connecting to cameras...")
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg="#1a1a1a",
            fg="#00ff00",
            font=("Arial", 10),
            anchor=tk.W,
            padx=10,
            pady=6
        )
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        # Front status indicator with error highlighting
        self.front_status_label = tk.Label(
            status_frame,
            textvariable=self.front_status_var,
            bg="#1a1a1a",
            fg="#00ff00",
            font=("Arial", 9),
            anchor=tk.E,
            padx=10,
            pady=6
        )
        self.front_status_label.grid(row=0, column=1, sticky=tk.E)
        
        # Mode indicator
        mode_text = "DEMO MODE" if self.camera_manager.demo_mode else "LIVE MODE"
        mode_color = "#ff9900" if self.camera_manager.demo_mode else "#00cc00"
        mode_label = tk.Label(
            status_frame,
            text=f"  {mode_text}  ",
            bg=("#333300" if self.camera_manager.demo_mode else "#003300"),
            fg=mode_color,
            font=("Arial", 9, "bold"),
            anchor=tk.E,
            padx=8,
            pady=4,
            relief=tk.SUNKEN,
            borderwidth=1
        )
        mode_label.grid(row=0, column=2, sticky=tk.E, padx=(5, 0))
        
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=0)
        status_frame.columnconfigure(2, weight=0)
        
        # Store references for error highlighting
        self.status_frame = status_frame
        self.mode_label = mode_label
        
    def setup_bindings(self):
        """Setup keyboard and event bindings"""
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Focus to receive key events
        self.root.focus_set()
    
    def _update_status_highlighting(self) -> None:
        """Update status bar colors based on error state"""
        if not hasattr(self, 'status_label') or not hasattr(self, 'front_status_label'):
            return
        
        main_status = self.status_var.get().lower()
        front_status = self.front_status_var.get().lower()
        
        # Check for errors in main status
        has_main_error = 'error' in main_status or 'failed' in main_status or 'offline' in main_status
        if has_main_error:
            self.status_label.config(fg="#ff2020", bg="#330000")  # Bright red on dark red background
            self.status_frame.config(bg="#330000")
        else:
            self.status_label.config(fg="#00ff00", bg="#1a1a1a")  # Green on dark background
            self.status_frame.config(bg="#1a1a1a")
        
        # Check for errors in front status
        has_front_error = 'error' in front_status or 'offline' in front_status or 'failed' in front_status
        if has_front_error:
            self.front_status_label.config(fg="#ffff00", bg="#331100")  # Yellow on dark red-brown background
        else:
            self.front_status_label.config(fg="#00ff00", bg="#1a1a1a")  # Green on dark background
    
    def _flash_error(self, label, cycles: int = 3) -> None:
        """Flash a label red to indicate error"""
        if not hasattr(label, 'config'):
            return
        
        original_fg = label.cget('fg')
        original_bg = label.cget('bg')
        
        def flash(count: int = 0) -> None:
            if count >= cycles * 2:
                label.config(fg=original_fg, bg=original_bg)
                self._update_status_highlighting()
                return
            
            if count % 2 == 0:
                label.config(fg="#ffff00", bg="#cc0000")  # Bright yellow on bright red
            else:
                label.config(fg=original_fg, bg=original_bg)
            
            self.root.after(150, lambda: flash(count + 1))
        
        flash()
        
    def on_key_press(self, event):
        """Handle key press events"""
        key = event.keysym.lower()
        
        if key == 'q':
            self.on_closing()
        elif key == 'h':
            self.show_help_window()
        elif key == 'plus' or key == 'equal':
            self.ir_threshold.set(min(255, self.ir_threshold.get() + 5))
        elif key == 'minus':
            self.ir_threshold.set(max(0, self.ir_threshold.get() - 5))
        elif key == 's':
            self.save_screenshot()
        elif key == 'r':
            self.reset_view()
        elif key == 'o':
            # Toggle raw overlay
            self.show_raw_overlay.set(not self.show_raw_overlay.get())
        elif key == 'g':
            # Toggle grid
            self.show_grid.set(not self.show_grid.get())
        elif key == 'c':
            # Toggle coordinates
            self.show_coordinates.set(not self.show_coordinates.get())
        elif key == 'b':
            # Toggle beacons
            self.show_beacons.set(not self.show_beacons.get())
            
    def on_video_click(self, event):
        """Handle mouse clicks on video display"""
        if self.current_frame is not None and self.video_label is not None:
            # Calculate actual coordinates in the video frame
            label_width = self.video_label.winfo_width()
            label_height = self.video_label.winfo_height()
            
            if hasattr(self, 'display_image') and self.display_image:
                img_width = self.display_image.width()
                img_height = self.display_image.height()
                
                # Calculate scale factors
                scale_x = self.current_frame.shape[1] / img_width
                scale_y = self.current_frame.shape[0] / img_height
                
                # Convert click coordinates to frame coordinates
                frame_x = int(event.x * scale_x)
                frame_y = int(event.y * scale_y)
                
                # Update status with coordinates
                self.status_var.set(f"Clicked at: ({frame_x}, {frame_y})")
                
                logger.info(f"Mouse click at frame coordinates: ({frame_x}, {frame_y})")
                
    def start_display(self):
        """Start the video display thread"""
        if not self.running:
            self.running = True
            # Start front ReID runner if available
            if self.reid_runner is not None:
                try:
                    if not getattr(self.reid_runner, 'running', False):
                        start_fn = getattr(self.reid_runner, 'start', None)
                        ok = bool(start_fn()) if callable(start_fn) else False
                        if ok:
                            if DemoReIDRunner is not None and isinstance(self.reid_runner, DemoReIDRunner):
                                mode_label = "demo"
                            else:
                                mode_label = "running"
                            self.front_status_var.set(f"Front: {mode_label}")
                            self._update_status_highlighting()
                        else:
                            self.front_status_var.set("❌ Front: failed to start")
                            self._flash_error(self.front_status_label)
                            self._update_status_highlighting()
                    else:
                        self.front_status_var.set("Front: running")
                        self._update_status_highlighting()
                except Exception as e:
                    self.front_status_var.set(f"❌ Front: error {e}")
                    self._flash_error(self.front_status_label)
                    self._update_status_highlighting()
            self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
            self.display_thread.start()
            self.status_var.set("Connecting to cameras...")
            logger.info("Video display started")
            
    def stop_display(self):
        """Stop the video display"""
        self.running = False
        if self.display_thread:
            self.display_thread.join(timeout=1.0)
        try:
            if self.reid_runner is not None:
                stop_fn = getattr(self.reid_runner, "stop", None)
                if callable(stop_fn):
                    stop_fn()
        except Exception:
            pass
        self.status_var.set("Display stopped")
        logger.info("Video display stopped")
        
    def display_loop(self):
        """Main display loop running in separate thread"""
        frame_count = 0
        fps_start_time = time.time()
        
        while self.running:
            try:
                # Get composite frame from camera manager
                composite_frame = self.camera_manager.create_composite_frame()
                
                if composite_frame is not None:
                    # If available, run a ReID processing step here to pass tracks into processing
                    reid_tracks = None
                    if self.reid_runner is not None:
                        try:
                            read_fn = getattr(self.reid_runner, 'read_and_process', None)
                            get_overlay = getattr(self.reid_runner, 'get_overlay_frame', None)
                            if callable(read_fn):
                                reid_tracks = read_fn()
                            overlay_bgr = None
                            if callable(get_overlay):
                                overlay_bgr = get_overlay()
                            if self.show_reid_overlay.get() and isinstance(overlay_bgr, np.ndarray):
                                self.display_front_frame(overlay_bgr)
                                self.front_status_var.set("Front: streaming")
                                self._update_status_highlighting()
                            elif self.show_reid_overlay.get():
                                self.display_front_placeholder()
                                self.front_status_var.set("Front: waiting for frames")
                                self._update_status_highlighting()
                            else:
                                if self.front_video_label is not None:
                                    self.front_video_label.configure(image="", text="Front overlay hidden")
                        except Exception as e:
                            self.front_status_var.set(f"❌ Front: error {e}")
                            self._flash_error(self.front_status_label, cycles=2)
                            self._update_status_highlighting()

                    # Normalize ReID tracks typing for fusion/processing
                    reid_tracks_dict: Optional[Dict[int, Dict[str, Any]]] = None
                    if isinstance(reid_tracks, dict):
                        tmp: Dict[int, Dict[str, Any]] = {}
                        try:
                            for k, v in reid_tracks.items():
                                try:
                                    tmp[int(k)] = v  # type: ignore[arg-type]
                                except Exception:
                                    continue
                            reid_tracks_dict = tmp
                        except Exception:
                            reid_tracks_dict = None

                    # Process frame with IR detection, fusion, and overlays
                    processed_frame = self.process_frame(composite_frame, reid_tracks=reid_tracks_dict)
                    
                    # Convert to PIL Image and display
                    self.display_frame(processed_frame)
                    if self.camera_manager.has_active_feeds():
                        self.status_var.set("Streaming live feeds")
                    else:
                        self.status_var.set("Connecting to cameras...")
                    
                    # Update statistics with smooth animation
                    frame_count += 1
                    if frame_count % 30 == 0:  # Update every 30 frames
                        fps = frame_count / (time.time() - fps_start_time)
                        fps_text = f"FPS: {fps:.1f}"
                        beacon_text = f"Beacons: {len(self.last_ir_beacons)}"
                        frame_text = f"Frame: {composite_frame.shape[1]}x{composite_frame.shape[0]}"
                        
                        # Update with subtle visual feedback
                        self.fps_var.set(fps_text)
                        self.beacon_count_var.set(beacon_text)
                        self.frame_size_var.set(frame_text)
                        
                else:
                    # No frame available (e.g., no configured cameras)
                    self.display_no_feed_message()
                    self.display_front_placeholder()
                    self.status_var.set("⚠️ No camera feeds available")
                    self._update_status_highlighting()
                    
                target_fps = 120 if not self.camera_manager.has_active_feeds() else 30
                sleep_interval = max(1.0 / target_fps, 0.001)
                time.sleep(sleep_interval)
                
            except Exception as e:
                logger.error(f"Error in display loop: {e}")
                self.status_var.set(f"❌ Display error: {str(e)[:50]}")
                self._flash_error(self.status_label)
                self._update_status_highlighting()
                time.sleep(0.1)
                
    def process_frame(self, frame: np.ndarray, reid_tracks: Optional[Dict[int, Dict[str, Any]]] = None) -> np.ndarray:
        """Process frame with IR detection, fusion, and overlays"""
        processed_frame = frame.copy()
        
        # Store original frame for raw overlay
        raw_frame = frame.copy()
        
        # Detect IR beacons
        beacons, viz_frame = self.camera_manager.detect_ir_beacons_composite(frame)
        # Cache last IR beacons
        try:
            self.last_ir_beacons = beacons if isinstance(beacons, list) else []
        except Exception:
            self.last_ir_beacons = []
        
        if self.show_beacons.get():
            processed_frame = viz_frame
            
        # Update beacon count
        self.beacon_count_var.set(f"Beacons: {len(beacons)}")

        # Fused overlay
        if self.fusion is not None and self.show_fused_overlay.get():
            try:
                # Build IR beacon inputs for fusion (convert pixels to meters)
                ir_inputs = []
                for i, b in enumerate(self.last_ir_beacons):
                    cx, cy = b.get("center", (0, 0))
                    ir_inputs.append({
                        "id": i,
                        "x": float(cx) * 0.01,
                        "y": float(cy) * 0.01,
                        "confidence": 0.8
                    })
                # ReID tracks if provided
                reid_dict: Dict[int, Dict[str, Any]] = reid_tracks if isinstance(reid_tracks, dict) else {}
                fused_persons = self.fusion.update_fusion(reid_dict, ir_inputs, time.time())
                positions = self.fusion.get_person_positions()
                self.last_fused_positions = positions
                self.fused_count_var.set(f"Fused: {len(positions)}")
                # Draw fused targets
                processed_frame = self.draw_fused_targets(processed_frame, positions)
            except Exception as e:
                logger.debug(f"Fusion overlay error: {e}")
        
        # Add coordinate grid if enabled
        if self.show_grid.get():
            processed_frame = self.add_coordinate_grid(processed_frame)
            
        # Add coordinate system info
        if self.show_coordinates.get():
            processed_frame = self.add_coordinate_info(processed_frame)
            
        # Add raw overlay if enabled
        if self.show_raw_overlay.get():
            processed_frame = self.add_raw_overlay(processed_frame, raw_frame)
            
        return processed_frame

    def draw_fused_targets(self, frame: np.ndarray, positions: List[Dict[str, Any]]) -> np.ndarray:
        """Draw fused person positions onto the composite frame.
        Note: We visualize stage coordinates heuristically on the composite by simple scaling.
        """
        if not positions:
            self.lead_target_info = None
            return frame

        # Determine lead target (highest confidence)
        lead = positions[0]
        self.lead_target_info = lead

        # Heuristic mapping from meters back to pixels for visualization
        # This is only for UI; true mapping would use calibration.
        def stage_to_px(x_m: float, y_m: float) -> Tuple[int, int]:
            px = int(x_m * 100.0)
            py = int(y_m * 100.0)
            # Clamp to frame bounds
            h, w = frame.shape[:2]
            return max(0, min(w - 1, px)), max(0, min(h - 1, py))

        for p in positions:
            px, py = stage_to_px(float(p.get("x", 0.0)), float(p.get("y", 0.0)))
            pid = p.get("id", 0)
            conf = p.get("confidence", 0.0)
            color = (0, 255, 0) if p is not lead else (0, 165, 255)  # orange for lead
            cv2.circle(frame, (px, py), 10 if p is lead else 6, color, 2)
            cv2.putText(frame, f"ID {pid} {conf:.2f}", (px + 12, py - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            # Small directional indicator if velocity present
            vel = p.get("velocity")
            if isinstance(vel, list) and len(vel) >= 2:
                vx, vy = float(vel[0]), float(vel[1])
                tip = (int(px + vx * 10), int(py + vy * 10))
                cv2.arrowedLine(frame, (px, py), tip, color, 1, tipLength=0.3)
        # Legend
        cv2.putText(frame, "Fused targets (orange = lead)", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        return frame
        
    def add_coordinate_grid(self, frame: np.ndarray) -> np.ndarray:
        """Add coordinate grid overlay to frame"""
        height, width = frame.shape[:2]
        
        # Grid spacing
        grid_spacing = 50
        
        # Draw vertical lines
        for x in range(0, width, grid_spacing):
            cv2.line(frame, (x, 0), (x, height), (100, 100, 100), 1)
            if x % (grid_spacing * 4) == 0:  # Label every 4th line
                cv2.putText(frame, str(x), (x + 2, 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
                
        # Draw horizontal lines
        for y in range(0, height, grid_spacing):
            cv2.line(frame, (0, y), (width, y), (100, 100, 100), 1)
            if y % (grid_spacing * 4) == 0:  # Label every 4th line
                cv2.putText(frame, str(y), (2, y + 15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
                
        return frame
        
    def add_coordinate_info(self, frame: np.ndarray) -> np.ndarray:
        """Add coordinate system information to frame"""
        height, width = frame.shape[:2]
        
        # Add origin marker
        cv2.circle(frame, (0, 0), 5, (0, 255, 0), -1)
        cv2.putText(frame, "Origin (0,0)", (10, 15), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Add frame dimensions
        cv2.putText(frame, f"Frame: {width}x{height}", (10, height - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
        
    def add_raw_overlay(self, processed_frame: np.ndarray, raw_frame: np.ndarray) -> np.ndarray:
        """Add raw video overlay in corner of processed frame"""
        height, width = processed_frame.shape[:2]
        
        # Calculate overlay size (1/4 of frame size)
        overlay_width = width // 4
        overlay_height = height // 4
        
        # Resize raw frame to overlay size
        overlay_frame = cv2.resize(raw_frame, (overlay_width, overlay_height))
        
        # Position overlay in top-right corner
        x_offset = width - overlay_width - 10
        y_offset = 10
        
        # Add border around overlay
        cv2.rectangle(processed_frame, 
                     (x_offset - 2, y_offset - 2), 
                     (x_offset + overlay_width + 2, y_offset + overlay_height + 2), 
                     (255, 255, 255), 2)
        
        # Add overlay to processed frame
        processed_frame[y_offset:y_offset + overlay_height, 
                      x_offset:x_offset + overlay_width] = overlay_frame
        
        # Add label
        cv2.putText(processed_frame, "Raw Feed", 
                   (x_offset, y_offset - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        return processed_frame
        
    def display_frame(self, frame: np.ndarray):
        """Display frame in the GUI with smooth fade transitions"""
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            pil_image = Image.fromarray(rgb_frame)
            
            # Resize to fit display area while maintaining aspect ratio
            display_width = 800
            display_height = 600
            
            # Calculate scaling to fit display area
            scale_w = display_width / pil_image.width
            scale_h = display_height / pil_image.height
            scale = min(scale_w, scale_h)
            
            new_width = int(pil_image.width * scale)
            new_height = int(pil_image.height * scale)
            
            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Apply subtle fade-in for new frames
            if self.frame_fade_alpha < 1.0:
                self.frame_fade_alpha = min(1.0, self.frame_fade_alpha + self.animation_speed)
            
            # Convert to PhotoImage
            self.display_image = ImageTk.PhotoImage(pil_image)
            
            # Update label with smooth transition
            if self.video_label is not None:
                self.video_label.configure(image=self.display_image, text="")
            self.current_frame = frame
            self.last_frame_timestamp = time.time()
            
        except Exception as e:
            logger.error(f"Error displaying frame: {e}")

    def display_front_frame(self, frame: np.ndarray):
        """Display front camera overlay in the second panel"""
        try:
            if self.front_video_label is None:
                return
            self.front_last_seen = time.time()
            self.front_missing_since = None
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            display_width = 800
            display_height = 300
            scale_w = display_width / pil_image.width
            scale_h = display_height / pil_image.height
            scale = min(scale_w, scale_h)
            new_width = int(pil_image.width * scale)
            new_height = int(pil_image.height * scale)
            pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.front_display_image = ImageTk.PhotoImage(pil_image)
            self.front_video_label.configure(image=self.front_display_image, text="")
        except Exception as e:
            logger.error(f"Error displaying front frame: {e}")

    def display_front_placeholder(self):
        """Display animated front placeholder with smooth transitions"""
        if self.front_video_label is None:
            return

        now = time.time()
        timeout = getattr(self.camera_manager, "_offline_timeout", 15.0)
        if self.front_missing_since is None:
            self.front_missing_since = now
        missing_since = self.front_missing_since or now

        is_connecting = (now - missing_since) < timeout
        message = "Front ReID\nCONNECTING" if is_connecting else "Front ReID\nOFFLINE"

        measured_width = self.front_video_label.winfo_width()
        measured_height = self.front_video_label.winfo_height()
        if measured_width <= 1 or measured_height <= 1:
            width, height = 640, 300
        else:
            width = max(320, measured_width)
            height = max(200, measured_height)
        render_connecting = getattr(self.camera_manager, "_render_connecting_tile", None)
        render_offline = getattr(self.camera_manager, "_render_offline_tile", None)

        try:
            if is_connecting and callable(render_connecting):
                tile = render_connecting(width, height, message=message)
            elif callable(render_offline):
                tile = render_offline(width, height, message=message)
            else:
                tile = np.zeros((height, width, 3), dtype=np.uint8)
                color = (0, 215, 255) if is_connecting else (0, 0, 255)
                tile[:] = color
        except Exception:
            tile = np.zeros((height, width, 3), dtype=np.uint8)

        try:
            tile = np.asarray(tile, dtype=np.uint8)
            rgb_tile = cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_tile)
            self.front_placeholder_image = ImageTk.PhotoImage(pil_image)
            self.front_video_label.configure(image=self.front_placeholder_image, text="")
        except Exception:
            self.front_video_label.configure(image="", text=message.replace("\n", " "))

        status = "connecting" if is_connecting else "offline"
        if not is_connecting:
            self.front_status_var.set(f"❌ Front: {status}")
            self._update_status_highlighting()
        else:
            self.front_status_var.set(f"Front: {status}")
            self._update_status_highlighting()
            
    def display_no_feed_message(self):
        """Display message when no video feed is available"""
        if self.video_label is not None:
            self.video_label.configure(image="", text="")
        
    def save_screenshot(self):
        """Save current frame as screenshot"""
        if self.current_frame is not None:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.jpg"
            cv2.imwrite(filename, self.current_frame)
            self.status_var.set(f"Screenshot saved: {filename}")
            logger.info(f"Screenshot saved: {filename}")
        else:
            messagebox.showwarning("No Frame", "No frame available to save")
            
    def reset_view(self):
        """Reset view settings to defaults"""
        self.ir_threshold.set(200)
        self.show_coordinates.set(True)
        self.show_grid.set(True)
        self.show_beacons.set(True)
        self.show_raw_overlay.set(False)
        self.status_var.set("View reset to defaults")
    
    def show_help_window(self):
        """Show the help/keybinds window as an independent window"""
        # Close existing help window if open
        if self.help_window and self.help_window.winfo_exists():
            self.help_window.lift()
            self.help_window.focus_set()
            return
            
        # Create new help window
        self.help_window = tk.Toplevel(self.root)
        self.help_window.title("Keyboard Shortcuts & Controls")
        self.help_window.geometry("500x600")
        self.help_window.resizable(True, True)
        
        # Make window independent (can be moved to another screen)
        self.help_window.transient()  # Remove parent dependency for multi-screen
        
        # Main frame with padding
        main_frame = ttk.Frame(self.help_window, padding="20")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights for resizing
        self.help_window.columnconfigure(0, weight=1)
        self.help_window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Keyboard Shortcuts & Controls", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 20), sticky=tk.W)
        
        # Create scrollable text area
        text_frame = ttk.Frame(main_frame)
        text_frame.grid(row=1, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        # Text widget with scrollbar
        text_widget = tk.Text(text_frame, wrap=tk.WORD, padx=10, pady=10, 
                             font=("Courier New", 11), state=tk.DISABLED)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Help content
        help_content = """KEYBOARD SHORTCUTS

Navigation & Control:
  H                    Show this help window
  Q                    Quit application
  Space                Start/Stop video display
  R                    Reset view to defaults
  S                    Save screenshot
  
Threshold Adjustment:
  +  or  =             Increase IR threshold (+5)
  -                    Decrease IR threshold (-5)
  
Display Toggles:
  G                    Toggle grid overlay
  C                    Toggle coordinate display
  B                    Toggle IR beacon markers
  O                    Toggle raw overlay view

MOUSE CONTROLS

Video Display:
  Left Click           Show coordinates at click position
  
CONTROL PANEL

IR Threshold:
  • Adjust sensitivity for IR beacon detection
  • Range: 0-255 (higher = less sensitive)
  • Use slider or enter value directly

Display Options:
  ☑ Show Coordinates   Display coordinate overlay
  ☑ Show Grid          Display reference grid
  ☑ Show IR Beacons    Highlight detected IR beacons
  ☑ Show Raw Overlay   Show raw detection overlay

BUTTONS

Start/Stop:           Toggle video feed on/off
Save Screenshot:      Capture current frame to file
Reset View:           Return all settings to defaults

STATISTICS PANEL

• FPS: Current frames per second
• Beacons: Number of IR beacons detected
• Frame: Current video resolution

STATUS BAR

• Shows current operation status
• Displays mode: LIVE MODE or DEMO MODE
• LIVE: Connected to physical cameras
• DEMO: Using simulated camera feeds

TIPS FOR OPERATORS

Multi-Screen Setup:
• This help window can be moved to a secondary monitor
• Keep it open for quick reference during operation
• Main video feed remains on primary screen

Optimal Settings:
• Adjust IR threshold based on lighting conditions
• Use grid overlay for precise positioning
• Enable all overlays for maximum information
• Save screenshots for documentation

Performance:
• Higher thresholds improve performance
• Disable unnecessary overlays if needed
• Monitor FPS for real-time feedback"""

        # Insert content
        text_widget.config(state=tk.NORMAL)
        text_widget.insert(1.0, help_content)
        text_widget.config(state=tk.DISABLED)
        
        # Close button
        close_button = ttk.Button(main_frame, text="Close", 
                                 command=self.help_window.destroy)
        close_button.grid(row=2, column=0, pady=(20, 0), sticky=tk.E)
        ensure_window_fits_content(self.help_window, min_width=640, min_height=720, padding=56, center=True)
        self.help_window.focus_set()
    
    def show_about(self):
        """Show about dialog"""
        mode_text = "Demo Mode" if self.camera_manager.demo_mode else "Live Mode"
        about_text = f"""Multi-Camera IR Beacon Tracker

Current Mode: {mode_text}
Version: 1.0.0

This application provides real-time tracking of IR beacons
using multiple camera feeds for followspot automation.

Features:
• Real-time IR beacon detection
• Multi-camera composite display
• Adjustable sensitivity controls
• Coordinate tracking and overlay
• Screenshot capture capability

For more information and documentation:
https://github.com/Stavro-Purdie/Automated-Followspot-System"""
        
        messagebox.showinfo("About Multi-Camera IR Beacon Tracker", about_text)
        
    def on_closing(self):
        """Handle window closing"""
        self.stop_display()
        self.camera_manager.running = False
        # Stop front runner if active
        try:
            if self.reid_runner is not None:
                stop_fn = getattr(self.reid_runner, "stop", None)
                if callable(stop_fn):
                    stop_fn()
        except Exception:
            pass
        self.root.destroy()
        
    def run(self):
        """Start the GUI main loop"""
        self.start_display()  # Auto-start display
        self.root.mainloop()

if __name__ == "__main__":
    # Test the GUI with a dummy camera manager
    class DummyCameraManager:
        def __init__(self):
            self.demo_mode = True
            self.running = True
            
        def create_composite_frame(self):
            # Create a dummy frame for testing
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(frame, (100, 100), (300, 200), (0, 255, 0), 2)
            cv2.putText(frame, "Test Frame", (150, 160), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            return frame
            
        def detect_ir_beacons_composite(self, frame):
            # Dummy beacon detection
            beacons = [{"center": (200, 150), "area": 100}]
            viz_frame = frame.copy()
            cv2.circle(viz_frame, (200, 150), 10, (0, 0, 255), -1)
            return beacons, viz_frame
    
    # Test the GUI
    dummy_manager = DummyCameraManager()
    gui = VideoDisplayGUI(dummy_manager)
    gui.run()

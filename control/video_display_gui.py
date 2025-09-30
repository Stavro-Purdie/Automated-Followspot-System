#!/usr/bin/env python3
"""
Operator-facing dashboard for the live multi-camera followspot feed.

This window is central to the system. It streams the stitched video
wall, layers tracking overlays, and gives the operator quick controls for
screenshots, thresholds, and diagnostic panels.
"""

import tkinter as tk
from tkinter import ttk, messagebox
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
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
        view_menu.add_command(label="Start Display", command=self.start_display)
        view_menu.add_command(label="Stop Display", command=self.stop_display)
        view_menu.add_separator()
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
            ConnectionStatusWindow(  # type: ignore[arg-type]
                launcher=_LauncherProxy(self.root),
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
        
    def setup_control_panel(self, parent):
        """Layout the tactile controls operators reach for during a show."""
        control_frame = ttk.LabelFrame(parent, text="Controls", padding="10")
        control_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # IR Threshold control
        ttk.Label(control_frame, text="IR Threshold:").grid(row=0, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(control_frame)
        threshold_frame.grid(row=1, column=0, sticky="we", pady=5)

        threshold_scale = ttk.Scale(threshold_frame, from_=0, to=255,
                                    variable=self.ir_threshold, orient=tk.HORIZONTAL)
        threshold_scale.grid(row=0, column=0, sticky="we")
        threshold_frame.columnconfigure(0, weight=1)

        threshold_entry = ttk.Entry(threshold_frame, textvariable=self.ir_threshold, width=5)
        threshold_entry.grid(row=0, column=1, padx=(5, 0))

        # Display options
        ttk.Label(control_frame, text="Display Options:").grid(row=2, column=0, sticky=tk.W, pady=(20, 5))

        ttk.Checkbutton(control_frame, text="Show Coordinates",
                        variable=self.show_coordinates).grid(row=3, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(control_frame, text="Show Grid",
                        variable=self.show_grid).grid(row=4, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(control_frame, text="Show IR Beacons",
                        variable=self.show_beacons).grid(row=5, column=0, sticky=tk.W, pady=2)

        ttk.Checkbutton(control_frame, text="Show Raw Overlay",
                        variable=self.show_raw_overlay).grid(row=6, column=0, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(control_frame, text="Show Fused Targets",
                        variable=self.show_fused_overlay).grid(row=7, column=0, sticky=tk.W, pady=2)

        # Front ReID options
        ttk.Label(control_frame, text="Front ReID Overlay:").grid(row=8, column=0, sticky=tk.W, pady=(20, 5))
        ttk.Checkbutton(control_frame, text="Show Front Camera Overlay",
                        variable=self.show_reid_overlay).grid(row=9, column=0, sticky=tk.W, pady=2)

        # Statistics
        stats_frame = ttk.LabelFrame(control_frame, text="Statistics", padding="10")
        stats_frame.grid(row=10, column=0, sticky="we", pady=(20, 0))

        ttk.Label(stats_frame, textvariable=self.fps_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.beacon_count_var).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.frame_size_var).grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.fused_count_var).grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.front_status_var).grid(row=4, column=0, sticky=tk.W, pady=2)

        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=11, column=0, sticky="we", pady=(20, 0))

        ttk.Button(button_frame, text="Start/Stop",
                   command=self.toggle_display).grid(row=0, column=0, pady=5)

        ttk.Button(button_frame, text="Save Screenshot",
                   command=self.save_screenshot).grid(row=1, column=0, pady=5)

        ttk.Button(button_frame, text="Reset View",
                   command=self.reset_view).grid(row=2, column=0, pady=5)
        
    def setup_video_display(self, parent):
        """Setup the video display area"""
        video_frame = ttk.LabelFrame(parent, text="Video Feeds", padding="10")
        video_frame.grid(row=0, column=1, sticky="nsew")

        # IR Composite view
        ir_title = ttk.Label(video_frame, text="Roof IR Composite", anchor=tk.W)
        ir_title.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.video_label = ttk.Label(video_frame, text="No video feed available",
                                     background="black", foreground="white")
        self.video_label.grid(row=1, column=0, sticky="we")

        # Front ReID view
        front_title = ttk.Label(video_frame, text="Front ReID Overlay", anchor=tk.W)
        front_title.grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.front_video_label = ttk.Label(video_frame, text="Front camera not available",
                                           background="black", foreground="white")
        self.front_video_label.grid(row=3, column=0, sticky="we")

        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(1, weight=1)
        video_frame.rowconfigure(3, weight=1)

        # Mouse click handler for coordinates on IR view
        self.video_label.bind("<Button-1>", self.on_video_click)
        
    def setup_status_bar(self, parent):
        """Setup the status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=(10, 0))
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=0, sticky=tk.W)
        
        # Mode indicator
        mode_text = "DEMO MODE" if self.camera_manager.demo_mode else "LIVE MODE"
        mode_color = "orange" if self.camera_manager.demo_mode else "green"
        mode_label = ttk.Label(status_frame, text=mode_text, foreground=mode_color)
        mode_label.grid(row=0, column=1, sticky=tk.E)
        
        status_frame.columnconfigure(0, weight=1)
        
    def setup_bindings(self):
        """Setup keyboard and event bindings"""
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Focus to receive key events
        self.root.focus_set()
        
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
        elif key == 'space':
            self.toggle_display()
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
                
    def toggle_display(self):
        """Start or stop the video display"""
        if self.running:
            self.stop_display()
        else:
            self.start_display()
            
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
                        else:
                            self.front_status_var.set("Front: failed to start")
                    else:
                        self.front_status_var.set("Front: running")
                except Exception as e:
                    self.front_status_var.set(f"Front: error {e}")
            self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
            self.display_thread.start()
            self.status_var.set("Display started")
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
                            elif self.show_reid_overlay.get():
                                self.display_front_placeholder()
                                self.front_status_var.set("Front: waiting for frames")
                            else:
                                if self.front_video_label is not None:
                                    self.front_video_label.configure(image="", text="Front overlay hidden")
                        except Exception as e:
                            self.front_status_var.set(f"Front: error {e}")

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
                    
                    # Update statistics
                    frame_count += 1
                    if frame_count % 30 == 0:  # Update every 30 frames
                        fps = frame_count / (time.time() - fps_start_time)
                        self.fps_var.set(f"FPS: {fps:.1f}")
                        self.frame_size_var.set(f"Frame: {composite_frame.shape[1]}x{composite_frame.shape[0]}")
                        
                else:
                    # No frame available
                    self.display_no_feed_message()
                    self.display_front_placeholder()
                    
                time.sleep(1/30)  # ~30 FPS
                
            except Exception as e:
                logger.error(f"Error in display loop: {e}")
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
        """Display frame in the GUI"""
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
            
            # Convert to PhotoImage
            self.display_image = ImageTk.PhotoImage(pil_image)
            
            # Update label
            if self.video_label is not None:
                self.video_label.configure(image=self.display_image, text="")
            self.current_frame = frame
            
        except Exception as e:
            logger.error(f"Error displaying frame: {e}")

    def display_front_frame(self, frame: np.ndarray):
        """Display front camera overlay in the second panel"""
        try:
            if self.front_video_label is None:
                return
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
        if self.front_video_label is not None:
            self.front_video_label.configure(image="", text="Front camera not available")
            
    def display_no_feed_message(self):
        """Display message when no video feed is available"""
        if self.video_label is not None:
            self.video_label.configure(image="", text="No video feed available\nClick 'Start/Stop' to begin")
        
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
        
        # Center window on screen initially
        self.help_window.update_idletasks()
        x = (self.help_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.help_window.winfo_screenheight() // 2) - (600 // 2)
        self.help_window.geometry(f"500x600+{x}+{y}")
        
        # Focus on help window
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

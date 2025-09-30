#!/usr/bin/env python3
"""
Guide operators through tuning the ReID camera and stage measurements.
This window is where you pick camera devices, tweak calibration points, and keep the front
array's metrics in sync with reality.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import json
import cv2
import numpy as np
import threading
import time
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

class ReIDConfigurator:
    """All-in-one toolkit for managing the front ReID camera pipeline."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Front Array (ReID) Configurator - Automated Followspot System")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # Configuration file paths
        self.config_file = Path(__file__).parent.parent / "config" / "front_array_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        # Load existing configuration
        self.config = self.load_config()
        self._ensure_camera_defaults()
        self.spotlight_config_file = PROJECT_ROOT / "config" / "spotlight_config.json"
        self.spotlight_config_file.parent.mkdir(exist_ok=True)
        self.spotlight_config = self._load_spotlight_config()
        
        # Camera preview variables
        self.camera_active = False
        self.camera_thread = None
        self.current_frame = None
        self.camera_device = None
        
        # Calibration variables
        self.calibration_points = []
        self.calibration_mode = False
        
        # Create GUI
        self.setup_styles()
        self.create_widgets()
        self._build_menubar()
        self.load_config_to_gui()
        
        # Bind cleanup
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _build_menubar(self) -> None:
        """Give operators shortcuts to hop between companion tools."""
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Configuration", command=self.save_config)
        file_menu.add_command(label="Reload Configuration", command=self.load_config_to_gui)
        file_menu.add_separator()
        file_menu.add_command(label="Open Launcher", command=self._open_launcher)
        file_menu.add_command(
            label="Open Camera Configurator",
            command=lambda: self._launch_tool("camera_config_gui.py", "Camera Configurator"),
        )
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self.on_closing)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Start Camera", command=self.start_camera)
        tools_menu.add_command(label="Stop Camera", command=self.stop_camera)
        tools_menu.add_command(label="Toggle Camera", command=self.toggle_camera)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Open Identity Configurator",
            command=lambda: self._launch_tool("identity_configurator.py", "Identity Configurator"),
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
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
        tool_path = Path(__file__).resolve().parent / script_name
        if not tool_path.exists():
            messagebox.showerror("Missing Tool", f"{description} not found at:\n{tool_path}")
            return
        try:
            subprocess.Popen([sys.executable, str(tool_path)])
        except Exception as exc:
            messagebox.showerror("Launch Failed", f"Could not start {description}:\n{exc}")

    def _open_launcher(self) -> None:
        launcher_path = PROJECT_ROOT / "launcher_gui.py"
        if not launcher_path.exists():
            messagebox.showerror("Launcher Missing", "launcher_gui.py could not be found.")
            return
        try:
            subprocess.Popen([sys.executable, str(launcher_path)])
        except Exception as exc:
            messagebox.showerror("Launcher Error", f"Failed to open launcher:\n{exc}")
    
    def load_config(self):
        """Load front array (ReID) configuration file or create default"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    # Minimal migration: if legacy key structure with 'camera':{'front_camera':{device_id:..}}, ensure server_url exists
                    cam = data.get('camera', {}).get('front_camera', {})
                    if 'server_url' not in cam:
                        # Construct placeholder server_url
                        ip = cam.get('ip', '192.168.0.50')
                        port = cam.get('port', 8000)
                        data['camera']['front_camera']['server_url'] = f"http://{ip}:{port}/offer"
                        data['camera']['front_camera']['protocol'] = cam.get('protocol', 'webrtc')
                    return data
            except Exception as e:
                messagebox.showwarning("Configuration Error", f"Error loading config: {e}\nUsing defaults.")
        
        # Default front array configuration
        return {
            "camera": {
                "front_camera": {
                    "camera_id": "front",
                    "server_url": "http://192.168.0.50:8000/offer",
                    "protocol": "webrtc",
                    "position": [0, 0, 2.5],
                    "angle": 0,
                    "fov": 60,
                    "focal_length": 1000,
                    "resolution": [1920, 1080],
                    "extrinsics": {
                        "rotation_matrix": [
                            [1.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0],
                            [0.0, 0.0, 1.0]
                        ],
                        "translation_vector": [0.0, 0.0, 0.0],
                        "reference_frame": "stage",
                        "calibrated": False,
                        "calibration_date": None
                    },
                    "depth": {
                        "enabled": True,
                        "confidence_floor": 0.4,
                        "fallback_height": 1.75,
                        "smoothing_window": 5
                    },
                    "calibration_matrix": [
                        [1000, 0, 960],
                        [0, 1000, 540],
                        [0, 0, 1]
                    ],
                    "distortion_coeffs": [0, 0, 0, 0, 0]
                }
            },
            "stage_geometry": {"width": 10.0, "depth": 8.0, "height": 3.0, "origin": [0, 0, 0], "units": "meters"},
            "performance": {"target_fps": 15, "detection_resolution": [1280, 720], "max_persons": 10, "confidence_threshold": 0.6, "nms_threshold": 0.4},
            "models": {
                "detector": {"name": "yolov8n", "device": "auto", "batch_size": 1, "model_path": "reid/models/yolov8n.pt"},
                "reid": {"name": "osnet_x0_5", "feature_dim": 512, "device": "auto", "model_path": "reid/models/osnet_x0_5_market1501.pth"}
            },
            "tracking": {"max_disappeared": 10, "max_distance": 100, "reid_threshold": 0.7, "depth_estimation_method": "geometric", "feature_similarity_threshold": 0.6, "max_tracking_distance": 2.0, "track_memory_frames": 30, "new_track_confidence_threshold": 0.5},
            "data_fusion": {"position_match_threshold": 1.0, "time_sync_tolerance": 0.1, "reid_weight": 0.4, "ir_weight": 0.6, "fusion_memory_time": 3.0},
            "calibration": {"stage_corners": [], "reference_points": [], "calibrated": False, "calibration_date": None}
        }

    def _ensure_camera_defaults(self) -> None:
        """Ensure new calibration fields exist so the UI can bind to them."""
        camera_root = self.config.setdefault("camera", {})
        cam_cfg = camera_root.setdefault("front_camera", {})

        extrinsics = cam_cfg.setdefault("extrinsics", {})
        extrinsics.setdefault("rotation_matrix", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        extrinsics.setdefault("translation_vector", [0.0, 0.0, 0.0])
        extrinsics.setdefault("reference_frame", "stage")
        extrinsics.setdefault("calibrated", False)
        extrinsics.setdefault("calibration_date", None)

        depth_cfg = cam_cfg.setdefault("depth", {})
        depth_cfg.setdefault("enabled", True)
        depth_cfg.setdefault("confidence_floor", 0.4)
        depth_cfg.setdefault("fallback_height", 1.75)
        depth_cfg.setdefault("smoothing_window", 5)

    def _load_spotlight_config(self) -> Dict:
        try:
            if self.spotlight_config_file.exists():
                with self.spotlight_config_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = {}
        except Exception as exc:
            messagebox.showwarning("Spotlight Config", f"Failed to load spotlight config: {exc}\nUsing defaults.")
            data = {}

        return self._ensure_spotlight_defaults(data)

    def _ensure_spotlight_defaults(self, cfg: Dict) -> Dict:
        rig_cfg = cfg.setdefault("rig", {})
        rig_cfg.setdefault("fixture_position_m", [0.0, -5.0, 6.5])
        rig_cfg.setdefault("stage_origin_m", [0.0, 0.0, 0.0])
        rig_cfg.setdefault("pan_zero_angle_deg", 0.0)
        rig_cfg.setdefault("tilt_zero_angle_deg", -35.0)
        rig_cfg.setdefault("pan_limits_deg", [-120.0, 120.0])
        rig_cfg.setdefault("tilt_limits_deg", [-120.0, 10.0])
        smoothing = rig_cfg.setdefault("smoothing", {})
        smoothing.setdefault("pan_alpha", 0.2)
        smoothing.setdefault("tilt_alpha", 0.25)

        dmx_cfg = cfg.setdefault("dmx", {})
        dmx_cfg.setdefault("universe", 1)
        dmx_cfg.setdefault("pan_address", 1)
        dmx_cfg.setdefault("tilt_address", 3)
        dmx_cfg.setdefault("pan_scale", 1.0)
        dmx_cfg.setdefault("tilt_scale", 1.0)
        dmx_cfg.setdefault("transport", "stub")

        return cfg
    
    def save_config(self):
        """Save configuration to file"""
        if not self.update_config_from_gui():
            return False
        try:
            # Update configuration timestamp
            self.config["last_updated"] = datetime.now().isoformat()
            
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

            with open(self.spotlight_config_file, 'w', encoding="utf-8") as fh:
                json.dump(self.spotlight_config, fh, indent=2)
            
            messagebox.showinfo("Configuration Saved", 
                               f"Configuration saved to:\n{self.config_file}\n{self.spotlight_config_file}")
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving configuration: {e}")
            return False
    
    def setup_styles(self):
        """Setup GUI styling"""
        style = ttk.Style()
        
        # Configure colors and fonts
        style.configure('Heading.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 10))
    
    def create_widgets(self):
        """Create main GUI widgets"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Left panel - Configuration
        self.create_config_panel(main_frame)
        
        # Right panel - Camera preview and calibration
        self.create_camera_panel(main_frame)
        
        # Bottom panel - Control buttons
        self.create_control_panel(main_frame)
    
    def create_config_panel(self, parent):
        """Create configuration panel"""
        config_frame = ttk.LabelFrame(parent, text="Configuration", padding="10")
        config_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        # Create notebook for different config sections
        self.notebook = ttk.Notebook(config_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        
        config_frame.columnconfigure(0, weight=1)
        config_frame.rowconfigure(0, weight=1)
        
        # Camera settings tab
        self.create_camera_tab()
        
        # Stage geometry tab
        self.create_stage_tab()
        
        # Performance tab
        self.create_performance_tab()
        
        # Tracking tab
        self.create_tracking_tab()
        
        # Data fusion tab
        self.create_fusion_tab()
        
        # Spotlight control tab
        self.create_spotlight_tab()
    
    def create_camera_tab(self):
        """Create camera configuration tab"""
        camera_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(camera_frame, text="Front Node Settings")
        cam_cfg = self.config["camera"]["front_camera"]
        ttk.Label(camera_frame, text="Front Node Server URL:").grid(row=0, column=0, sticky="w", pady=5)
        self.server_url_var = tk.StringVar(value=cam_cfg.get("server_url", "http://192.168.0.50:8000/offer"))
        ttk.Entry(camera_frame, textvariable=self.server_url_var, width=40).grid(row=0, column=1, sticky="w", padx=(5,0), pady=5)
        ttk.Label(camera_frame, text="Protocol:").grid(row=1, column=0, sticky="w", pady=5)
        self.protocol_var = tk.StringVar(value=cam_cfg.get("protocol", "webrtc"))
        ttk.Combobox(camera_frame, textvariable=self.protocol_var, values=["webrtc","rtsp"], width=10).grid(row=1, column=1, sticky="w", padx=(5,0), pady=5)
        # Resolution
        ttk.Label(camera_frame, text="Resolution:").grid(row=2, column=0, sticky="w", pady=5)
        res_frame = ttk.Frame(camera_frame); res_frame.grid(row=2, column=1, sticky="w", padx=(5,0), pady=5)
        self.camera_width_var = tk.StringVar(value=str(cam_cfg["resolution"][0]))
        self.camera_height_var = tk.StringVar(value=str(cam_cfg["resolution"][1]))
        ttk.Entry(res_frame, textvariable=self.camera_width_var, width=8).grid(row=0,column=0)
        ttk.Label(res_frame, text="×").grid(row=0,column=1,padx=5)
        ttk.Entry(res_frame, textvariable=self.camera_height_var, width=8).grid(row=0,column=2)
        # Position
        ttk.Label(camera_frame, text="Camera Position (X,Y,Z m):").grid(row=3, column=0, sticky="w", pady=5)
        pos_frame = ttk.Frame(camera_frame); pos_frame.grid(row=3, column=1, sticky="w", padx=(5,0), pady=5)
        self.camera_x_var = tk.StringVar(value=str(cam_cfg["position"][0]))
        self.camera_y_var = tk.StringVar(value=str(cam_cfg["position"][1]))
        self.camera_z_var = tk.StringVar(value=str(cam_cfg["position"][2]))
        ttk.Entry(pos_frame, textvariable=self.camera_x_var, width=8).grid(row=0,column=0)
        ttk.Entry(pos_frame, textvariable=self.camera_y_var, width=8).grid(row=0,column=1,padx=5)
        ttk.Entry(pos_frame, textvariable=self.camera_z_var, width=8).grid(row=0,column=2)
        # Angle / FOV / Focal
        ttk.Label(camera_frame, text="Camera Angle (deg):").grid(row=4,column=0,sticky="w",pady=5)
        self.camera_angle_var = tk.StringVar(value=str(cam_cfg.get("angle",0)))
        ttk.Entry(camera_frame, textvariable=self.camera_angle_var, width=10).grid(row=4,column=1,sticky="w",padx=(5,0),pady=5)
        ttk.Label(camera_frame, text="Field of View (deg):").grid(row=5,column=0,sticky="w",pady=5)
        self.camera_fov_var = tk.StringVar(value=str(cam_cfg.get("fov",60)))
        ttk.Entry(camera_frame, textvariable=self.camera_fov_var, width=10).grid(row=5,column=1,sticky="w",padx=(5,0),pady=5)
        ttk.Label(camera_frame, text="Focal Length (px):").grid(row=6,column=0,sticky="w",pady=5)
        self.camera_focal_var = tk.StringVar(value=str(cam_cfg.get("focal_length",1000)))
        ttk.Entry(camera_frame, textvariable=self.camera_focal_var, width=10).grid(row=6,column=1,sticky="w",padx=(5,0),pady=5)

        # Extrinsics section
        ttk.Separator(camera_frame, orient="horizontal").grid(row=7, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(camera_frame, text="Camera Extrinsics", style='Heading.TLabel').grid(row=8, column=0, sticky="w")
        ttk.Button(camera_frame, text="Calibration Guide", command=self.open_calibration_doc).grid(row=8, column=1, sticky="e")

        extrinsics = cam_cfg.get("extrinsics", {})
        extrinsics_frame = ttk.Frame(camera_frame)
        extrinsics_frame.grid(row=9, column=0, columnspan=2, sticky="ew", pady=5)

        self.extrinsics_calibrated_var = tk.BooleanVar(value=extrinsics.get("calibrated", False))
        ttk.Checkbutton(extrinsics_frame, text="Calibrated", variable=self.extrinsics_calibrated_var).grid(row=0, column=0, sticky="w")

        ttk.Label(extrinsics_frame, text="Calibration Date (ISO):").grid(row=0, column=1, sticky="e", padx=(10, 5))
        self.extrinsics_date_var = tk.StringVar(value=extrinsics.get("calibration_date") or "")
        ttk.Entry(extrinsics_frame, textvariable=self.extrinsics_date_var, width=20).grid(row=0, column=2, sticky="w")

        ttk.Label(extrinsics_frame, text="Reference Frame:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.extrinsics_reference_var = tk.StringVar(value=extrinsics.get("reference_frame", "stage"))
        ttk.Entry(extrinsics_frame, textvariable=self.extrinsics_reference_var, width=15).grid(row=1, column=1, sticky="w", pady=(8, 0))

        # Rotation matrix inputs
        rot_frame = ttk.LabelFrame(camera_frame, text="Rotation Matrix")
        rot_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=5)
        self.rotation_vars = []
        rotation_matrix = extrinsics.get("rotation_matrix", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        for i in range(3):
            row_vars = []
            for j in range(3):
                var = tk.StringVar(value=str(rotation_matrix[i][j]))
                row_vars.append(var)
                ttk.Entry(rot_frame, textvariable=var, width=8).grid(row=i, column=j, padx=4, pady=2)
            self.rotation_vars.append(row_vars)

        # Translation vector inputs
        trans_frame = ttk.LabelFrame(camera_frame, text="Translation Vector (m)")
        trans_frame.grid(row=11, column=0, columnspan=2, sticky="ew", pady=5)
        translation_vector = extrinsics.get("translation_vector", [0.0, 0.0, 0.0])
        self.translation_vars = []
        for idx in range(3):
            var = tk.StringVar(value=str(translation_vector[idx]))
            self.translation_vars.append(var)
            ttk.Entry(trans_frame, textvariable=var, width=10).grid(row=0, column=idx, padx=4, pady=2)

        # Depth configuration section
        depth_cfg = cam_cfg.get("depth", {})
        depth_frame = ttk.LabelFrame(camera_frame, text="Depth Settings")
        depth_frame.grid(row=12, column=0, columnspan=2, sticky="ew", pady=10)

        self.depth_enabled_var = tk.BooleanVar(value=depth_cfg.get("enabled", True))
        ttk.Checkbutton(depth_frame, text="Enable Camera Z Contribution", variable=self.depth_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(depth_frame, text="Confidence Floor:").grid(row=1, column=0, sticky="w", pady=5)
        self.depth_conf_floor_var = tk.StringVar(value=str(depth_cfg.get("confidence_floor", 0.4)))
        ttk.Entry(depth_frame, textvariable=self.depth_conf_floor_var, width=10).grid(row=1, column=1, sticky="w", pady=5)

        ttk.Label(depth_frame, text="Fallback Height (m):").grid(row=2, column=0, sticky="w", pady=5)
        self.depth_fallback_var = tk.StringVar(value=str(depth_cfg.get("fallback_height", 1.75)))
        ttk.Entry(depth_frame, textvariable=self.depth_fallback_var, width=10).grid(row=2, column=1, sticky="w", pady=5)

        ttk.Label(depth_frame, text="Smoothing Window (frames):").grid(row=3, column=0, sticky="w", pady=5)
        self.depth_smoothing_var = tk.StringVar(value=str(depth_cfg.get("smoothing_window", 5)))
        ttk.Entry(depth_frame, textvariable=self.depth_smoothing_var, width=10).grid(row=3, column=1, sticky="w", pady=5)

    def create_stage_tab(self):
        """Create stage geometry configuration tab"""
        stage_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(stage_frame, text="Stage Geometry")
        
        # Stage dimensions
        ttk.Label(stage_frame, text="Stage Width (meters):").grid(row=0, column=0, sticky="w", pady=5)
        self.stage_width_var = tk.StringVar(value=str(self.config["stage_geometry"]["width"]))
        ttk.Entry(stage_frame, textvariable=self.stage_width_var, width=10).grid(row=0, column=1, sticky="w", padx=(5, 0), pady=5)
        
        ttk.Label(stage_frame, text="Stage Depth (meters):").grid(row=1, column=0, sticky="w", pady=5)
        self.stage_depth_var = tk.StringVar(value=str(self.config["stage_geometry"]["depth"]))
        ttk.Entry(stage_frame, textvariable=self.stage_depth_var, width=10).grid(row=1, column=1, sticky="w", padx=(5, 0), pady=5)
        
        ttk.Label(stage_frame, text="Stage Height (meters):").grid(row=2, column=0, sticky="w", pady=5)
        self.stage_height_var = tk.StringVar(value=str(self.config["stage_geometry"]["height"]))
        ttk.Entry(stage_frame, textvariable=self.stage_height_var, width=10).grid(row=2, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Stage origin
        ttk.Label(stage_frame, text="Stage Origin (X, Y, Z meters):").grid(row=3, column=0, sticky="w", pady=5)
        origin_frame = ttk.Frame(stage_frame)
        origin_frame.grid(row=3, column=1, sticky="w", padx=(5, 0), pady=5)
        
        self.stage_origin_x_var = tk.StringVar(value=str(self.config["stage_geometry"]["origin"][0]))
        self.stage_origin_y_var = tk.StringVar(value=str(self.config["stage_geometry"]["origin"][1]))
        self.stage_origin_z_var = tk.StringVar(value=str(self.config["stage_geometry"]["origin"][2]))
        
        ttk.Entry(origin_frame, textvariable=self.stage_origin_x_var, width=8).grid(row=0, column=0)
        ttk.Entry(origin_frame, textvariable=self.stage_origin_y_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Entry(origin_frame, textvariable=self.stage_origin_z_var, width=8).grid(row=0, column=2)
        
        # Calibration section
        ttk.Separator(stage_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky="ew", pady=20)
        
        ttk.Label(stage_frame, text="Calibration:", style='Heading.TLabel').grid(row=5, column=0, sticky="w", pady=5)
        
        calibration_config = self.config.get("calibration", {"calibrated": False})
        calib_status = "Calibrated" if calibration_config.get("calibrated", False) else "Not Calibrated"
        ttk.Label(stage_frame, text=f"Status: {calib_status}").grid(row=6, column=0, sticky="w", pady=5)
        
        ttk.Button(stage_frame, text="Start Calibration", 
                  command=self.start_calibration).grid(row=7, column=0, sticky="w", pady=5)
    
    def create_performance_tab(self):
        """Create performance configuration tab"""
        perf_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(perf_frame, text="Performance")
        
        # Target FPS
        ttk.Label(perf_frame, text="Target FPS:").grid(row=0, column=0, sticky="w", pady=5)
        self.target_fps_var = tk.StringVar(value=str(self.config["performance"]["target_fps"]))
        ttk.Entry(perf_frame, textvariable=self.target_fps_var, width=10).grid(row=0, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Detection resolution
        ttk.Label(perf_frame, text="Detection Resolution:").grid(row=1, column=0, sticky="w", pady=5)
        det_res_frame = ttk.Frame(perf_frame)
        det_res_frame.grid(row=1, column=1, sticky="w", padx=(5, 0), pady=5)
        
        self.det_width_var = tk.StringVar(value=str(self.config["performance"]["detection_resolution"][0]))
        self.det_height_var = tk.StringVar(value=str(self.config["performance"]["detection_resolution"][1]))
        
        ttk.Entry(det_res_frame, textvariable=self.det_width_var, width=8).grid(row=0, column=0)
        ttk.Label(det_res_frame, text="×").grid(row=0, column=1, padx=5)
        ttk.Entry(det_res_frame, textvariable=self.det_height_var, width=8).grid(row=0, column=2)
        
        # Max persons
        ttk.Label(perf_frame, text="Max Persons to Track:").grid(row=2, column=0, sticky="w", pady=5)
        self.max_persons_var = tk.StringVar(value=str(self.config["performance"]["max_persons"]))
        ttk.Entry(perf_frame, textvariable=self.max_persons_var, width=10).grid(row=2, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Confidence thresholds
        ttk.Label(perf_frame, text="Confidence Threshold:").grid(row=3, column=0, sticky="w", pady=5)
        self.confidence_var = tk.DoubleVar(value=self.config["performance"]["confidence_threshold"])
        ttk.Scale(perf_frame, from_=0.1, to=1.0, variable=self.confidence_var, orient="horizontal").grid(row=3, column=1, sticky="ew", padx=(5, 0), pady=5)
        self.confidence_label = ttk.Label(perf_frame, text=f"{self.confidence_var.get():.2f}")
        self.confidence_label.grid(row=3, column=2, sticky="w", padx=(5, 0), pady=5)
        self.confidence_var.trace_add('write', self.update_confidence_label)
        
        # NMS threshold
        ttk.Label(perf_frame, text="NMS Threshold:").grid(row=4, column=0, sticky="w", pady=5)
        self.nms_var = tk.DoubleVar(value=self.config["performance"]["nms_threshold"])
        ttk.Scale(perf_frame, from_=0.1, to=1.0, variable=self.nms_var, orient="horizontal").grid(row=4, column=1, sticky="ew", padx=(5, 0), pady=5)
        self.nms_label = ttk.Label(perf_frame, text=f"{self.nms_var.get():.2f}")
        self.nms_label.grid(row=4, column=2, sticky="w", padx=(5, 0), pady=5)
        self.nms_var.trace_add('write', self.update_nms_label)
        
        perf_frame.columnconfigure(1, weight=1)
    
    def create_tracking_tab(self):
        """Create tracking configuration tab"""
        track_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(track_frame, text="Tracking")
        
        # ReID threshold
        ttk.Label(track_frame, text="ReID Similarity Threshold:").grid(row=0, column=0, sticky="w", pady=5)
        self.reid_threshold_var = tk.DoubleVar(value=self.config["tracking"]["reid_threshold"])
        ttk.Scale(track_frame, from_=0.1, to=1.0, variable=self.reid_threshold_var, orient="horizontal").grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=5)
        self.reid_threshold_label = ttk.Label(track_frame, text=f"{self.reid_threshold_var.get():.2f}")
        self.reid_threshold_label.grid(row=0, column=2, sticky="w", padx=(5, 0), pady=5)
        self.reid_threshold_var.trace_add('write', self.update_reid_threshold_label)
        
        # Depth estimation method
        ttk.Label(track_frame, text="Depth Estimation Method:").grid(row=1, column=0, sticky="w", pady=5)
        self.depth_method_var = tk.StringVar(value=self.config["tracking"]["depth_estimation_method"])
        depth_combo = ttk.Combobox(track_frame, textvariable=self.depth_method_var, 
                                  values=["simple", "height_based", "geometric", "hybrid"], width=15)
        depth_combo.grid(row=1, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Max tracking distance
        ttk.Label(track_frame, text="Max Tracking Distance (m):").grid(row=2, column=0, sticky="w", pady=5)
        self.max_track_dist_var = tk.StringVar(value=str(self.config["tracking"]["max_tracking_distance"]))
        ttk.Entry(track_frame, textvariable=self.max_track_dist_var, width=10).grid(row=2, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Track memory frames
        ttk.Label(track_frame, text="Track Memory (frames):").grid(row=3, column=0, sticky="w", pady=5)
        self.track_memory_var = tk.StringVar(value=str(self.config["tracking"]["track_memory_frames"]))
        ttk.Entry(track_frame, textvariable=self.track_memory_var, width=10).grid(row=3, column=1, sticky="w", padx=(5, 0), pady=5)
        
        track_frame.columnconfigure(1, weight=1)
    
    def create_fusion_tab(self):
        """Create data fusion configuration tab"""
        fusion_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(fusion_frame, text="Data Fusion")
        
        # Position match threshold
        ttk.Label(fusion_frame, text="Position Match Threshold (m):").grid(row=0, column=0, sticky="w", pady=5)
        self.pos_match_var = tk.StringVar(value=str(self.config["data_fusion"]["position_match_threshold"]))
        ttk.Entry(fusion_frame, textvariable=self.pos_match_var, width=10).grid(row=0, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Weight settings
        ttk.Label(fusion_frame, text="ReID Weight:").grid(row=1, column=0, sticky="w", pady=5)
        self.reid_weight_var = tk.DoubleVar(value=self.config["data_fusion"]["reid_weight"])
        ttk.Scale(fusion_frame, from_=0.0, to=1.0, variable=self.reid_weight_var, orient="horizontal").grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=5)
        self.reid_weight_label = ttk.Label(fusion_frame, text=f"{self.reid_weight_var.get():.2f}")
        self.reid_weight_label.grid(row=1, column=2, sticky="w", padx=(5, 0), pady=5)
        self.reid_weight_var.trace_add('write', self.update_reid_weight_label)
        
        ttk.Label(fusion_frame, text="IR Weight:").grid(row=2, column=0, sticky="w", pady=5)
        self.ir_weight_var = tk.DoubleVar(value=self.config["data_fusion"]["ir_weight"])
        ttk.Scale(fusion_frame, from_=0.0, to=1.0, variable=self.ir_weight_var, orient="horizontal").grid(row=2, column=1, sticky="ew", padx=(5, 0), pady=5)
        self.ir_weight_label = ttk.Label(fusion_frame, text=f"{self.ir_weight_var.get():.2f}")
        self.ir_weight_label.grid(row=2, column=2, sticky="w", padx=(5, 0), pady=5)
        self.ir_weight_var.trace_add('write', self.update_ir_weight_label)
        
        # Time sync tolerance
        ttk.Label(fusion_frame, text="Time Sync Tolerance (s):").grid(row=3, column=0, sticky="w", pady=5)
        self.time_sync_var = tk.StringVar(value=str(self.config["data_fusion"]["time_sync_tolerance"]))
        ttk.Entry(fusion_frame, textvariable=self.time_sync_var, width=10).grid(row=3, column=1, sticky="w", padx=(5, 0), pady=5)
        
        fusion_frame.columnconfigure(1, weight=1)

    def create_spotlight_tab(self):
        """Create spotlight configuration tab"""
        spot_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(spot_frame, text="Spotlight Rig")

        rig_cfg = self.spotlight_config["rig"]
        dmx_cfg = self.spotlight_config["dmx"]

        ttk.Label(spot_frame, text="Fixture Position (m)", style='Heading.TLabel').grid(row=0, column=0, sticky="w", pady=(0, 5))
        fixture_frame = ttk.Frame(spot_frame)
        fixture_frame.grid(row=0, column=1, sticky="w", pady=(0, 5))
        self.fixture_pos_vars = [tk.StringVar(value=str(rig_cfg["fixture_position_m"][idx])) for idx in range(3)]
        for idx, axis_label in enumerate(["X", "Y", "Z"]):
            ttk.Label(fixture_frame, text=f"{axis_label}:").grid(row=0, column=idx * 2, padx=(0, 2))
            ttk.Entry(fixture_frame, textvariable=self.fixture_pos_vars[idx], width=8).grid(row=0, column=idx * 2 + 1, padx=(0, 6))

        ttk.Label(spot_frame, text="Stage Origin (m)", style='Heading.TLabel').grid(row=1, column=0, sticky="w", pady=5)
        origin_frame = ttk.Frame(spot_frame)
        origin_frame.grid(row=1, column=1, sticky="w", pady=5)
        self.spot_origin_vars = [tk.StringVar(value=str(rig_cfg.get("stage_origin_m", [0.0, 0.0, 0.0])[idx])) for idx in range(3)]
        for idx, axis_label in enumerate(["X", "Y", "Z"]):
            ttk.Label(origin_frame, text=f"{axis_label}:").grid(row=0, column=idx * 2, padx=(0, 2))
            ttk.Entry(origin_frame, textvariable=self.spot_origin_vars[idx], width=8).grid(row=0, column=idx * 2 + 1, padx=(0, 6))

        ttk.Label(spot_frame, text="Zero Angles (deg)", style='Heading.TLabel').grid(row=2, column=0, sticky="w", pady=5)
        zero_frame = ttk.Frame(spot_frame)
        zero_frame.grid(row=2, column=1, sticky="w", pady=5)
        self.pan_zero_var = tk.StringVar(value=str(rig_cfg.get("pan_zero_angle_deg", 0.0)))
        self.tilt_zero_var = tk.StringVar(value=str(rig_cfg.get("tilt_zero_angle_deg", -35.0)))
        ttk.Label(zero_frame, text="Pan:").grid(row=0, column=0, padx=(0, 2))
        ttk.Entry(zero_frame, textvariable=self.pan_zero_var, width=8).grid(row=0, column=1, padx=(0, 6))
        ttk.Label(zero_frame, text="Tilt:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(zero_frame, textvariable=self.tilt_zero_var, width=8).grid(row=0, column=3)

        ttk.Label(spot_frame, text="Pan Limits (deg)").grid(row=3, column=0, sticky="w", pady=5)
        pan_limit_frame = ttk.Frame(spot_frame)
        pan_limit_frame.grid(row=3, column=1, sticky="w", pady=5)
        self.pan_limit_min_var = tk.StringVar(value=str(rig_cfg["pan_limits_deg"][0]))
        self.pan_limit_max_var = tk.StringVar(value=str(rig_cfg["pan_limits_deg"][1]))
        ttk.Label(pan_limit_frame, text="Min:").grid(row=0, column=0, padx=(0, 2))
        ttk.Entry(pan_limit_frame, textvariable=self.pan_limit_min_var, width=8).grid(row=0, column=1, padx=(0, 6))
        ttk.Label(pan_limit_frame, text="Max:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(pan_limit_frame, textvariable=self.pan_limit_max_var, width=8).grid(row=0, column=3)

        ttk.Label(spot_frame, text="Tilt Limits (deg)").grid(row=4, column=0, sticky="w", pady=5)
        tilt_limit_frame = ttk.Frame(spot_frame)
        tilt_limit_frame.grid(row=4, column=1, sticky="w", pady=5)
        self.tilt_limit_min_var = tk.StringVar(value=str(rig_cfg["tilt_limits_deg"][0]))
        self.tilt_limit_max_var = tk.StringVar(value=str(rig_cfg["tilt_limits_deg"][1]))
        ttk.Label(tilt_limit_frame, text="Min:").grid(row=0, column=0, padx=(0, 2))
        ttk.Entry(tilt_limit_frame, textvariable=self.tilt_limit_min_var, width=8).grid(row=0, column=1, padx=(0, 6))
        ttk.Label(tilt_limit_frame, text="Max:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(tilt_limit_frame, textvariable=self.tilt_limit_max_var, width=8).grid(row=0, column=3)

        ttk.Label(spot_frame, text="Smoothing", style='Heading.TLabel').grid(row=5, column=0, sticky="w", pady=5)
        smoothing_frame = ttk.Frame(spot_frame)
        smoothing_frame.grid(row=5, column=1, sticky="w", pady=5)
        self.pan_alpha_var = tk.StringVar(value=str(rig_cfg["smoothing"].get("pan_alpha", 0.2)))
        self.tilt_alpha_var = tk.StringVar(value=str(rig_cfg["smoothing"].get("tilt_alpha", 0.25)))
        ttk.Label(smoothing_frame, text="Pan α:").grid(row=0, column=0, padx=(0, 2))
        ttk.Entry(smoothing_frame, textvariable=self.pan_alpha_var, width=8).grid(row=0, column=1, padx=(0, 6))
        ttk.Label(smoothing_frame, text="Tilt α:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(smoothing_frame, textvariable=self.tilt_alpha_var, width=8).grid(row=0, column=3)

        ttk.Label(spot_frame, text="DMX Settings", style='Heading.TLabel').grid(row=6, column=0, sticky="w", pady=5)
        dmx_frame = ttk.Frame(spot_frame)
        dmx_frame.grid(row=6, column=1, sticky="w", pady=5)
        self.dmx_universe_var = tk.StringVar(value=str(dmx_cfg.get("universe", 1)))
        self.dmx_pan_address_var = tk.StringVar(value=str(dmx_cfg.get("pan_address", 1)))
        self.dmx_tilt_address_var = tk.StringVar(value=str(dmx_cfg.get("tilt_address", 3)))
        self.dmx_pan_scale_var = tk.StringVar(value=str(dmx_cfg.get("pan_scale", 1.0)))
        self.dmx_tilt_scale_var = tk.StringVar(value=str(dmx_cfg.get("tilt_scale", 1.0)))
        self.dmx_transport_var = tk.StringVar(value=dmx_cfg.get("transport", "stub"))

        ttk.Label(dmx_frame, text="Universe:").grid(row=0, column=0, padx=(0, 2))
        ttk.Entry(dmx_frame, textvariable=self.dmx_universe_var, width=6).grid(row=0, column=1, padx=(0, 6))
        ttk.Label(dmx_frame, text="Pan Addr:").grid(row=0, column=2, padx=(0, 2))
        ttk.Entry(dmx_frame, textvariable=self.dmx_pan_address_var, width=6).grid(row=0, column=3, padx=(0, 6))
        ttk.Label(dmx_frame, text="Tilt Addr:").grid(row=0, column=4, padx=(0, 2))
        ttk.Entry(dmx_frame, textvariable=self.dmx_tilt_address_var, width=6).grid(row=0, column=5)

        ttk.Label(dmx_frame, text="Pan Scale:").grid(row=1, column=0, padx=(0, 2), pady=5)
        ttk.Entry(dmx_frame, textvariable=self.dmx_pan_scale_var, width=6).grid(row=1, column=1, padx=(0, 6), pady=5)
        ttk.Label(dmx_frame, text="Tilt Scale:").grid(row=1, column=2, padx=(0, 2), pady=5)
        ttk.Entry(dmx_frame, textvariable=self.dmx_tilt_scale_var, width=6).grid(row=1, column=3, padx=(0, 6), pady=5)
        ttk.Label(dmx_frame, text="Transport:").grid(row=1, column=4, padx=(0, 2), pady=5)
        ttk.Combobox(dmx_frame, textvariable=self.dmx_transport_var, values=["stub", "artnet", "sacn", "osc"], width=8).grid(row=1, column=5, pady=5)

        spot_frame.columnconfigure(1, weight=1)
    
    def create_camera_panel(self, parent):
        """Create camera preview and calibration panel"""
        camera_frame = ttk.LabelFrame(parent, text="Camera Preview & Calibration", padding="10")
        camera_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        # Camera preview canvas
        self.camera_canvas = tk.Canvas(camera_frame, width=640, height=480, bg="black")
        self.camera_canvas.grid(row=0, column=0, columnspan=2, sticky="nsew")
        
        # Camera controls
        control_frame = ttk.Frame(camera_frame)
        control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        self.camera_btn = ttk.Button(control_frame, text="Start Camera", command=self.toggle_camera)
        self.camera_btn.grid(row=0, column=0, padx=(0, 5))
        
        ttk.Button(control_frame, text="Test Detection", command=self.test_detection).grid(row=0, column=1, padx=5)
        ttk.Button(control_frame, text="Calibrate", command=self.start_calibration).grid(row=0, column=2, padx=5)
        
        # Status display
        self.status_label = ttk.Label(camera_frame, text="Camera: Stopped", style='Status.TLabel')
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        
        camera_frame.columnconfigure(0, weight=1)
        camera_frame.rowconfigure(0, weight=1)
    
    def create_control_panel(self, parent):
        """Create control buttons panel"""
        control_frame = ttk.Frame(parent, padding="10")
        control_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        
        ttk.Button(control_frame, text="Load Configuration", command=self.load_config_file).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(control_frame, text="Save Configuration", command=self.save_config).grid(row=0, column=1, padx=5)
        ttk.Button(control_frame, text="Export Config", command=self.export_config).grid(row=0, column=2, padx=5)
        ttk.Button(control_frame, text="Test System", command=self.test_system).grid(row=0, column=3, padx=5)
        
        # Spacer
        control_frame.columnconfigure(4, weight=1)
        
        ttk.Button(control_frame, text="Reset to Defaults", command=self.reset_defaults).grid(row=0, column=5, padx=5)
        ttk.Button(control_frame, text="Close", command=self.on_closing).grid(row=0, column=6, padx=(5, 0))
    
    def load_config_to_gui(self):
        """Load configuration values into GUI elements"""
        try:
            cam_config = self.config["camera"]["front_camera"]
            # server_url etc already in vars if created, ensure sync
            if hasattr(self, 'server_url_var'):
                self.server_url_var.set(cam_config.get('server_url',''))
                self.protocol_var.set(cam_config.get('protocol','webrtc'))
            self.camera_width_var.set(str(cam_config["resolution"][0]))
            self.camera_height_var.set(str(cam_config["resolution"][1]))
            self.camera_x_var.set(str(cam_config["position"][0]))
            self.camera_y_var.set(str(cam_config["position"][1]))
            self.camera_z_var.set(str(cam_config["position"][2]))
            self.camera_angle_var.set(str(cam_config.get("angle",0)))
            self.camera_fov_var.set(str(cam_config.get("fov",60)))
            self.camera_focal_var.set(str(cam_config.get("focal_length",1000)))
            extrinsics = cam_config.get("extrinsics", {})
            if hasattr(self, "extrinsics_calibrated_var"):
                self.extrinsics_calibrated_var.set(bool(extrinsics.get("calibrated", False)))
                self.extrinsics_date_var.set(extrinsics.get("calibration_date") or "")
                self.extrinsics_reference_var.set(extrinsics.get("reference_frame", "stage"))
                rotation_matrix = extrinsics.get("rotation_matrix", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
                for i in range(3):
                    for j in range(3):
                        self.rotation_vars[i][j].set(str(rotation_matrix[i][j]))
                translation_vector = extrinsics.get("translation_vector", [0.0, 0.0, 0.0])
                for idx in range(3):
                    self.translation_vars[idx].set(str(translation_vector[idx]))
            depth_cfg = cam_config.get("depth", {})
            if hasattr(self, "depth_enabled_var"):
                self.depth_enabled_var.set(bool(depth_cfg.get("enabled", True)))
                self.depth_conf_floor_var.set(str(depth_cfg.get("confidence_floor", 0.4)))
                self.depth_fallback_var.set(str(depth_cfg.get("fallback_height", 1.75)))
                self.depth_smoothing_var.set(str(depth_cfg.get("smoothing_window", 5)))
            # Stage
            stage_config = self.config["stage_geometry"]
            self.stage_width_var.set(str(stage_config["width"]))
            self.stage_depth_var.set(str(stage_config["depth"]))
            self.stage_height_var.set(str(stage_config["height"]))
            self.stage_origin_x_var.set(str(stage_config["origin"][0]))
            self.stage_origin_y_var.set(str(stage_config["origin"][1]))
            self.stage_origin_z_var.set(str(stage_config["origin"][2]))

            self._load_spotlight_to_gui()
        except Exception as e:
            messagebox.showwarning("Load Error", f"Error loading some configuration values: {e}")
    
    def _load_spotlight_to_gui(self) -> None:
        try:
            rig_cfg = self.spotlight_config["rig"]
            for idx, var in enumerate(self.fixture_pos_vars):
                var.set(str(rig_cfg["fixture_position_m"][idx]))
            for idx, var in enumerate(self.spot_origin_vars):
                var.set(str(rig_cfg.get("stage_origin_m", [0.0, 0.0, 0.0])[idx]))
            self.pan_zero_var.set(str(rig_cfg.get("pan_zero_angle_deg", 0.0)))
            self.tilt_zero_var.set(str(rig_cfg.get("tilt_zero_angle_deg", -35.0)))
            self.pan_limit_min_var.set(str(rig_cfg["pan_limits_deg"][0]))
            self.pan_limit_max_var.set(str(rig_cfg["pan_limits_deg"][1]))
            self.tilt_limit_min_var.set(str(rig_cfg["tilt_limits_deg"][0]))
            self.tilt_limit_max_var.set(str(rig_cfg["tilt_limits_deg"][1]))
            smoothing_cfg = rig_cfg.get("smoothing", {})
            self.pan_alpha_var.set(str(smoothing_cfg.get("pan_alpha", 0.2)))
            self.tilt_alpha_var.set(str(smoothing_cfg.get("tilt_alpha", 0.25)))

            dmx_cfg = self.spotlight_config.get("dmx", {})
            self.dmx_universe_var.set(str(dmx_cfg.get("universe", 1)))
            self.dmx_pan_address_var.set(str(dmx_cfg.get("pan_address", 1)))
            self.dmx_tilt_address_var.set(str(dmx_cfg.get("tilt_address", 3)))
            self.dmx_pan_scale_var.set(str(dmx_cfg.get("pan_scale", 1.0)))
            self.dmx_tilt_scale_var.set(str(dmx_cfg.get("tilt_scale", 1.0)))
            self.dmx_transport_var.set(dmx_cfg.get("transport", "stub"))
        except Exception as exc:
            messagebox.showwarning("Spotlight Load", f"Failed to load spotlight config into UI: {exc}")

    def update_config_from_gui(self):
        """Update configuration dictionary from GUI values"""
        try:
            cam_config = self.config["camera"]["front_camera"]
            cam_config["server_url"] = self.server_url_var.get().strip()
            cam_config["protocol"] = self.protocol_var.get().strip()
            cam_config["resolution"] = [int(self.camera_width_var.get()), int(self.camera_height_var.get())]
            cam_config["position"] = [float(self.camera_x_var.get()), float(self.camera_y_var.get()), float(self.camera_z_var.get())]
            cam_config["angle"] = float(self.camera_angle_var.get())
            cam_config["fov"] = float(self.camera_fov_var.get())
            cam_config["focal_length"] = float(self.camera_focal_var.get())
            extrinsics = cam_config.setdefault("extrinsics", {})
            extrinsics["calibrated"] = bool(self.extrinsics_calibrated_var.get())
            date_value = self.extrinsics_date_var.get().strip()
            extrinsics["calibration_date"] = date_value or None
            extrinsics["reference_frame"] = self.extrinsics_reference_var.get().strip() or "stage"
            extrinsics["rotation_matrix"] = [
                [float(self.rotation_vars[i][j].get()) for j in range(3)]
                for i in range(3)
            ]
            extrinsics["translation_vector"] = [float(var.get()) for var in self.translation_vars]

            depth_cfg = cam_config.setdefault("depth", {})
            depth_cfg["enabled"] = bool(self.depth_enabled_var.get())
            depth_cfg["confidence_floor"] = float(self.depth_conf_floor_var.get())
            depth_cfg["fallback_height"] = float(self.depth_fallback_var.get())
            depth_cfg["smoothing_window"] = int(self.depth_smoothing_var.get())
            # Stage geometry
            stage_config = self.config["stage_geometry"]
            stage_config["width"] = float(self.stage_width_var.get())
            stage_config["depth"] = float(self.stage_depth_var.get())
            stage_config["height"] = float(self.stage_height_var.get())
            stage_config["origin"] = [float(self.stage_origin_x_var.get()), float(self.stage_origin_y_var.get()), float(self.stage_origin_z_var.get())]
            # Performance
            perf = self.config.get("performance", {})
            perf["target_fps"] = int(self.target_fps_var.get())
            perf["detection_resolution"] = [int(self.det_width_var.get()), int(self.det_height_var.get())]
            perf["max_persons"] = int(self.max_persons_var.get())
            perf["confidence_threshold"] = self.confidence_var.get()
            perf["nms_threshold"] = self.nms_var.get()
            # Tracking
            track = self.config.get("tracking", {})
            track["reid_threshold"] = self.reid_threshold_var.get()
            track["depth_estimation_method"] = self.depth_method_var.get()
            track["max_tracking_distance"] = float(self.max_track_dist_var.get())
            track["track_memory_frames"] = int(self.track_memory_var.get())
            # Data fusion
            fusion = self.config.get("data_fusion", {})
            fusion["position_match_threshold"] = float(self.pos_match_var.get())
            fusion["reid_weight"] = self.reid_weight_var.get()
            fusion["ir_weight"] = self.ir_weight_var.get()
            fusion["time_sync_tolerance"] = float(self.time_sync_var.get())

            self._update_spotlight_config_from_gui()
        except ValueError as e:
            messagebox.showerror("Configuration Error", f"Invalid value: {e}")
            return False
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Error updating configuration: {e}")
            return False
        
        return True

    def _update_spotlight_config_from_gui(self) -> None:
        rig_cfg = self.spotlight_config.setdefault("rig", {})
        rig_cfg["fixture_position_m"] = [float(var.get()) for var in self.fixture_pos_vars]
        rig_cfg["stage_origin_m"] = [float(var.get()) for var in self.spot_origin_vars]
        rig_cfg["pan_zero_angle_deg"] = float(self.pan_zero_var.get())
        rig_cfg["tilt_zero_angle_deg"] = float(self.tilt_zero_var.get())
        rig_cfg["pan_limits_deg"] = [float(self.pan_limit_min_var.get()), float(self.pan_limit_max_var.get())]
        rig_cfg["tilt_limits_deg"] = [float(self.tilt_limit_min_var.get()), float(self.tilt_limit_max_var.get())]
        smoothing_cfg = rig_cfg.setdefault("smoothing", {})
        smoothing_cfg["pan_alpha"] = float(self.pan_alpha_var.get())
        smoothing_cfg["tilt_alpha"] = float(self.tilt_alpha_var.get())

        dmx_cfg = self.spotlight_config.setdefault("dmx", {})
        dmx_cfg["universe"] = int(self.dmx_universe_var.get())
        dmx_cfg["pan_address"] = int(self.dmx_pan_address_var.get())
        dmx_cfg["tilt_address"] = int(self.dmx_tilt_address_var.get())
        dmx_cfg["pan_scale"] = float(self.dmx_pan_scale_var.get())
        dmx_cfg["tilt_scale"] = float(self.dmx_tilt_scale_var.get())
        dmx_cfg["transport"] = self.dmx_transport_var.get().strip() or "stub"

    def open_calibration_doc(self) -> None:
        """Open the calibration guide in the default viewer."""
        doc_path = PROJECT_ROOT / "docs" / "front_camera_z_calibration.md"
        if not doc_path.exists():
            messagebox.showerror("Calibration Guide Missing", str(doc_path))
            return
        webbrowser.open(doc_path.resolve().as_uri())
    
    # Label update methods
    def update_confidence_label(self, *args):
        self.confidence_label.config(text=f"{self.confidence_var.get():.2f}")
    
    def update_nms_label(self, *args):
        self.nms_label.config(text=f"{self.nms_var.get():.2f}")
    
    def update_reid_threshold_label(self, *args):
        self.reid_threshold_label.config(text=f"{self.reid_threshold_var.get():.2f}")
    
    def update_reid_weight_label(self, *args):
        self.reid_weight_label.config(text=f"{self.reid_weight_var.get():.2f}")
        # Auto-update IR weight to maintain balance
        self.ir_weight_var.set(1.0 - self.reid_weight_var.get())
    
    def update_ir_weight_label(self, *args):
        self.ir_weight_label.config(text=f"{self.ir_weight_var.get():.2f}")
        # Auto-update ReID weight to maintain balance
        self.reid_weight_var.set(1.0 - self.ir_weight_var.get())
    
    # Camera methods
    def toggle_camera(self):
        """Start or stop camera preview"""
        if not self.camera_active:
            self.start_camera()
        else:
            self.stop_camera()
    
    def start_camera(self):
        """Start network camera preview (placeholder using OpenCV if stream accessible)"""
        try:
            url = self.server_url_var.get().strip()
            self.camera_device = cv2.VideoCapture(url)
            if not self.camera_device.isOpened():
                messagebox.showerror("Camera Error", f"Could not open network stream: {url}\n(This may be expected for pure WebRTC until a bridge is implemented.)")
                return
            width = int(self.camera_width_var.get()); height = int(self.camera_height_var.get())
            self.camera_device.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.camera_device.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.camera_active = True
            self.camera_btn.config(text="Stop Camera")
            self.status_label.config(text="Camera: Running")
            self.camera_thread = threading.Thread(target=self.camera_loop, daemon=True)
            self.camera_thread.start()
        except Exception as e:
            messagebox.showerror("Camera Error", f"Error starting camera: {e}")
    
    def stop_camera(self):
        """Stop camera preview"""
        self.camera_active = False
        if self.camera_device:
            self.camera_device.release()
            self.camera_device = None
        
        self.camera_btn.config(text="Start Camera")
        self.status_label.config(text="Camera: Stopped")
        self.camera_canvas.delete("all")
        self.camera_canvas.create_text(320, 240, text="Camera Stopped", fill="white", font=("Arial", 16))
    
    def camera_loop(self):
        """Camera preview loop"""
        while self.camera_active and self.camera_device:
            try:
                ret, frame = self.camera_device.read()
                if not ret:
                    break
                display_frame = cv2.resize(frame, (640, 480))
                rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                self.current_frame = frame.copy()
                from PIL import Image, ImageTk
                pil_image = Image.fromarray(rgb_frame)
                photo = ImageTk.PhotoImage(pil_image)
                self.camera_canvas.delete("all")
                self.camera_canvas.create_image(320, 240, image=photo)
                self.camera_canvas.image = photo  # type: ignore[attr-defined]
                if self.calibration_mode:
                    self.draw_calibration_overlay()
                time.sleep(1/30)
            except Exception as e:
                print(f"Camera loop error: {e}")
                break
        self.stop_camera()

    def test_detection(self):
        """Test person detection on current frame"""
        if self.current_frame is None:
            messagebox.showwarning("No Frame", "Start camera first to test detection")
            return
        
        try:
            # This would normally use the ReID processor
            # For now, show a placeholder message
            messagebox.showinfo("Detection Test", 
                              "Detection test would run here.\n"
                              "In the full system, this would:\n"
                              "• Run YOLOv8 person detection\n"
                              "• Extract ReID features\n"
                              "• Estimate depth\n"
                              "• Show detection boxes")
            
        except Exception as e:
            messagebox.showerror("Detection Error", f"Error testing detection: {e}")
    
    def start_calibration(self):
        """Start camera calibration process"""
        if not self.camera_active:
            messagebox.showwarning("No Camera", "Start camera first to calibrate")
            return
        
        self.calibration_mode = True
        self.calibration_points.clear()
        
        messagebox.showinfo("Calibration Started", 
                          "Click on the four corners of the stage in this order:\n"
                          "1. Front-left corner\n"
                          "2. Front-right corner\n"
                          "3. Back-right corner\n"
                          "4. Back-left corner")
        
        # Bind click events
        self.camera_canvas.bind("<Button-1>", self.on_calibration_click)
    
    def on_calibration_click(self, event):
        """Handle calibration point clicks"""
        if not self.calibration_mode or len(self.calibration_points) >= 4:
            return
        if self.current_frame is None:
            return
        x, y = event.x, event.y
        actual_x = int(x * self.current_frame.shape[1] / 640)
        actual_y = int(y * self.current_frame.shape[0] / 480)
        self.calibration_points.append([actual_x, actual_y])
        if len(self.calibration_points) == 4:
            self.finish_calibration()

    def finish_calibration(self):
        """Finish calibration process"""
        self.calibration_mode = False
        self.camera_canvas.unbind("<Button-1>")
        
        # Ensure calibration section exists
        if "calibration" not in self.config:
            self.config["calibration"] = {
                "stage_corners": [],
                "reference_points": [],
                "calibrated": False,
                "calibration_date": None
            }
        # Store calibration points
        self.config["calibration"]["stage_corners"] = self.calibration_points.copy()
        self.config["calibration"]["calibrated"] = True
        self.config["calibration"]["calibration_date"] = datetime.now().isoformat()
        
        messagebox.showinfo("Calibration Complete", 
                          f"Calibration completed with {len(self.calibration_points)} points.\n"
                          "Save configuration to store calibration data.")
    
    def draw_calibration_overlay(self):
        """Draw calibration overlay on camera canvas"""
        if self.current_frame is None:
            return
        for i, point in enumerate(self.calibration_points):
            canvas_x = int(point[0] * 640 / self.current_frame.shape[1])
            canvas_y = int(point[1] * 480 / self.current_frame.shape[0])
            self.camera_canvas.create_oval(canvas_x-5, canvas_y-5, canvas_x+5, canvas_y+5, 
                                         fill="red", outline="white", width=2)
            self.camera_canvas.create_text(canvas_x+10, canvas_y-10, text=str(i+1), 
                                         fill="white", font=("Arial", 12, "bold"))
    
    # File operations
    def load_config_file(self):
        """Load configuration from file"""
        file_path = filedialog.askopenfilename(
            title="Load ReID Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.config_file.parent)
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.config = json.load(f)
                self._ensure_camera_defaults()
                self.load_config_to_gui()
                messagebox.showinfo("Configuration Loaded", f"Configuration loaded from:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Load Error", f"Error loading configuration: {e}")
    
    def export_config(self):
        """Export configuration to file"""
        file_path = filedialog.asksaveasfilename(
            title="Export ReID Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.config_file.parent)
        )
        
        if file_path:
            try:
                if self.update_config_from_gui():
                    with open(file_path, 'w') as f:
                        json.dump(self.config, f, indent=2)
                    messagebox.showinfo("Configuration Exported", f"Configuration exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Error exporting configuration: {e}")
    
    def test_system(self):
        if not self.update_config_from_gui():
            return
        try:
            results = []
            results.append("✅ Configuration format: Valid")
            # Network reachability basic check
            import urllib.request
            url = self.server_url_var.get().strip()
            try:
                req = urllib.request.Request(url, method='GET')
                with urllib.request.urlopen(req, timeout=3) as resp:
                    results.append(f"✅ Front node reachable (HTTP {resp.status})")
            except Exception as e:
                results.append(f"❌ Front node not reachable: {e}")
            # Stage
            width = float(self.stage_width_var.get()); depth = float(self.stage_depth_var.get())
            results.append("✅ Stage dimensions: Valid" if width>0 and depth>0 else "❌ Stage dimensions: Invalid")
            fps = int(self.target_fps_var.get())
            results.append("✅ Target FPS: Reasonable" if 1 <= fps <= 60 else "⚠️ Target FPS unusual")
            messagebox.showinfo("System Test", "System Test Results:\n\n" + "\n".join(results))
        except Exception as e:
            messagebox.showerror("Test Error", f"Error running system test: {e}")
    
    def reset_defaults(self):
        """Reset configuration to defaults"""
        if messagebox.askyesno("Reset Configuration", 
                              "Reset all settings to default values?\nThis cannot be undone."):
            self.config = self.load_config()
            self._ensure_camera_defaults()
            self.spotlight_config = self._ensure_spotlight_defaults({})
            self.load_config_to_gui()
            messagebox.showinfo("Reset Complete", "Configuration reset to defaults")
    
    def on_closing(self):
        """Handle application closing"""
        if self.camera_active:
            self.stop_camera()
        
        # Ask to save if there are unsaved changes
        if messagebox.askyesno("Save Configuration", 
                              "Save current configuration before closing?"):
            if self.update_config_from_gui():
                self.save_config()
        
        self.root.destroy()
    
    def run(self):
        """Run the configurator"""
        self.root.mainloop()


def main():
    """Main entry point"""
    try:
        configurator = ReIDConfigurator()
        configurator.run()
    except Exception as e:
        print(f"Error starting ReID Configurator: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
ReID Camera Configurator for Automated Followspot System
Handle            "camera": {
                "front_camera": {
                    "device_id": 0,
                    "position": [0, 0, 2.5],
                    "angle": 0,
                    "fov": 60,
                    "focal_length": 1000,
                    "resolution": [1920, 1080],
                    "calibration_matrix": [
                        [1000, 0, 960],
                        [0, 1000, 540], 
                        [0, 0, 1]
                    ],
                    "distortion_coeffs": [0, 0, 0, 0, 0]
                }
            }, of front truss camera, measurements, and ReID system parameters
Part of the Control Stack
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import json
import cv2
import numpy as np
import threading
import time
from pathlib import Path
from datetime import datetime
import os
import sys

class ReIDConfigurator:
    """
    Comprehensive configurator for ReID camera system and stage measurements
    """
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ReID Camera Configurator - Automated Followspot System")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # Configuration file paths
        self.config_file = Path(__file__).parent.parent / "config" / "reid_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        # Load existing configuration
        self.config = self.load_config()
        
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
        self.load_config_to_gui()
        
        # Bind cleanup
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def load_config(self):
        """Load ReID configuration file or create default"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                messagebox.showwarning("Configuration Error", 
                                     f"Error loading config: {e}\nUsing defaults.")
        
        # Default configuration
        return {
            "performance": {
                "target_fps": 15,
                "input_resolution": [1920, 1080],
                "detection_resolution": [1280, 720],
                "max_persons": 10,
                "confidence_threshold": 0.6,
                "nms_threshold": 0.4
            },
            "models": {
                "detector": {
                    "name": "yolov8n",
                    "device": "auto",
                    "batch_size": 1,
                    "model_path": "reid/models/yolov8n.pt"
                },
                "reid": {
                    "name": "osnet_x0_5",
                    "feature_dim": 512,
                    "device": "auto",
                    "model_path": "reid/models/osnet_x0_5_market1501.pth"
                }
            },
            "camera": {
                "front_camera": {
                    "device_id": 0,
                    "position": [0, 0, 2.5],
                    "angle": 0,
                    "fov": 60,
                    "focal_length": 1000,
                    "resolution": [1920, 1080],
                    "calibration_matrix": [
                        [1000, 0, 960],
                        [0, 1000, 540], 
                        [0, 0, 1]
                    ],
                    "distortion_coeffs": [0, 0, 0, 0, 0]
                }
            },
            "stage_geometry": {
                "width": 10.0,
                "depth": 8.0,
                "height": 3.0,
                "origin": [0, 0, 0],
                "units": "meters"
            },
            "tracking": {
                "max_disappeared": 10,
                "max_distance": 100,
                "reid_threshold": 0.7,
                "depth_estimation_method": "geometric",
                "feature_similarity_threshold": 0.6,
                "max_tracking_distance": 2.0,
                "track_memory_frames": 30,
                "new_track_confidence_threshold": 0.5
            },
            "data_fusion": {
                "position_match_threshold": 1.0,
                "time_sync_tolerance": 0.1,
                "reid_weight": 0.4,
                "ir_weight": 0.6,
                "fusion_memory_time": 3.0
            },
            "calibration": {
                "stage_corners": [],
                "reference_points": [],
                "calibrated": False,
                "calibration_date": None
            }
        }
    
    def save_config(self):
        """Save configuration to file"""
        try:
            # Update configuration timestamp
            self.config["last_updated"] = datetime.now().isoformat()
            
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            messagebox.showinfo("Configuration Saved", 
                               f"Configuration saved to:\n{self.config_file}")
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
    
    def create_camera_tab(self):
        """Create camera configuration tab"""
        camera_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(camera_frame, text="Camera Settings")
        
        # Camera device selection
        ttk.Label(camera_frame, text="Camera Device ID:").grid(row=0, column=0, sticky="w", pady=5)
        self.camera_device_var = tk.StringVar(value=str(self.config["camera"]["front_camera"].get("device_id", 0)))
        device_combo = ttk.Combobox(camera_frame, textvariable=self.camera_device_var, values=["0", "1", "2", "3"], width=10)
        device_combo.grid(row=0, column=1, sticky="w", padx=(5, 0), pady=5)
        
        # Camera resolution
        ttk.Label(camera_frame, text="Resolution:").grid(row=1, column=0, sticky="w", pady=5)
        res_frame = ttk.Frame(camera_frame)
        res_frame.grid(row=1, column=1, sticky="w", padx=(5, 0), pady=5)
        
        self.camera_width_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["resolution"][0]))
        self.camera_height_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["resolution"][1]))
        
        ttk.Entry(res_frame, textvariable=self.camera_width_var, width=8).grid(row=0, column=0)
        ttk.Label(res_frame, text="×").grid(row=0, column=1, padx=5)
        ttk.Entry(res_frame, textvariable=self.camera_height_var, width=8).grid(row=0, column=2)
        
        # Camera position (X, Y, Z in meters)
        ttk.Label(camera_frame, text="Camera Position (X, Y, Z meters):").grid(row=2, column=0, sticky="w", pady=5)
        pos_frame = ttk.Frame(camera_frame)
        pos_frame.grid(row=2, column=1, sticky="w", padx=(5, 0), pady=5)
        
        self.camera_x_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["position"][0]))
        self.camera_y_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["position"][1]))
        self.camera_z_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["position"][2]))
        
        ttk.Entry(pos_frame, textvariable=self.camera_x_var, width=8).grid(row=0, column=0)
        ttk.Entry(pos_frame, textvariable=self.camera_y_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Entry(pos_frame, textvariable=self.camera_z_var, width=8).grid(row=0, column=2)
        
        # Camera angle and FOV
        ttk.Label(camera_frame, text="Camera Angle (degrees):").grid(row=3, column=0, sticky="w", pady=5)
        self.camera_angle_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["angle"]))
        ttk.Entry(camera_frame, textvariable=self.camera_angle_var, width=10).grid(row=3, column=1, sticky="w", padx=(5, 0), pady=5)
        
        ttk.Label(camera_frame, text="Field of View (degrees):").grid(row=4, column=0, sticky="w", pady=5)
        self.camera_fov_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["fov"]))
        ttk.Entry(camera_frame, textvariable=self.camera_fov_var, width=10).grid(row=4, column=1, sticky="w", padx=(5, 0), pady=5)
        
        ttk.Label(camera_frame, text="Focal Length (pixels):").grid(row=5, column=0, sticky="w", pady=5)
        self.camera_focal_var = tk.StringVar(value=str(self.config["camera"]["front_camera"]["focal_length"]))
        ttk.Entry(camera_frame, textvariable=self.camera_focal_var, width=10).grid(row=5, column=1, sticky="w", padx=(5, 0), pady=5)
    
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
            # Camera settings
            cam_config = self.config["camera"]["front_camera"]
            self.camera_device_var.set(str(cam_config.get("device_id", 0)))
            self.camera_width_var.set(str(cam_config["resolution"][0]))
            self.camera_height_var.set(str(cam_config["resolution"][1]))
            self.camera_x_var.set(str(cam_config["position"][0]))
            self.camera_y_var.set(str(cam_config["position"][1]))
            self.camera_z_var.set(str(cam_config["position"][2]))
            self.camera_angle_var.set(str(cam_config["angle"]))
            self.camera_fov_var.set(str(cam_config["fov"]))
            self.camera_focal_var.set(str(cam_config["focal_length"]))
            
            # Stage geometry
            stage_config = self.config["stage_geometry"]
            self.stage_width_var.set(str(stage_config["width"]))
            self.stage_depth_var.set(str(stage_config["depth"]))
            self.stage_height_var.set(str(stage_config["height"]))
            self.stage_origin_x_var.set(str(stage_config["origin"][0]))
            self.stage_origin_y_var.set(str(stage_config["origin"][1]))
            self.stage_origin_z_var.set(str(stage_config["origin"][2]))
            
        except Exception as e:
            messagebox.showwarning("Load Error", f"Error loading some configuration values: {e}")
    
    def update_config_from_gui(self):
        """Update configuration dictionary from GUI values"""
        try:
            # Camera settings
            cam_config = self.config["camera"]["front_camera"]
            cam_config["device_id"] = int(self.camera_device_var.get())
            cam_config["resolution"] = [int(self.camera_width_var.get()), int(self.camera_height_var.get())]
            cam_config["position"] = [float(self.camera_x_var.get()), float(self.camera_y_var.get()), float(self.camera_z_var.get())]
            cam_config["angle"] = float(self.camera_angle_var.get())
            cam_config["fov"] = float(self.camera_fov_var.get())
            cam_config["focal_length"] = float(self.camera_focal_var.get())
            
            # Stage geometry
            stage_config = self.config["stage_geometry"]
            stage_config["width"] = float(self.stage_width_var.get())
            stage_config["depth"] = float(self.stage_depth_var.get())
            stage_config["height"] = float(self.stage_height_var.get())
            stage_config["origin"] = [float(self.stage_origin_x_var.get()), 
                                    float(self.stage_origin_y_var.get()), 
                                    float(self.stage_origin_z_var.get())]
            
            # Performance settings
            perf_config = self.config["performance"]
            perf_config["target_fps"] = int(self.target_fps_var.get())
            perf_config["detection_resolution"] = [int(self.det_width_var.get()), int(self.det_height_var.get())]
            perf_config["max_persons"] = int(self.max_persons_var.get())
            perf_config["confidence_threshold"] = self.confidence_var.get()
            perf_config["nms_threshold"] = self.nms_var.get()
            
            # Tracking settings
            track_config = self.config["tracking"]
            track_config["reid_threshold"] = self.reid_threshold_var.get()
            track_config["depth_estimation_method"] = self.depth_method_var.get()
            track_config["max_tracking_distance"] = float(self.max_track_dist_var.get())
            track_config["track_memory_frames"] = int(self.track_memory_var.get())
            
            # Data fusion settings
            fusion_config = self.config["data_fusion"]
            fusion_config["position_match_threshold"] = float(self.pos_match_var.get())
            fusion_config["reid_weight"] = self.reid_weight_var.get()
            fusion_config["ir_weight"] = self.ir_weight_var.get()
            fusion_config["time_sync_tolerance"] = float(self.time_sync_var.get())
            
        except ValueError as e:
            messagebox.showerror("Configuration Error", f"Invalid value entered: {e}")
            return False
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Error updating configuration: {e}")
            return False
        
        return True
    
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
        """Start camera preview"""
        try:
            device_id = int(self.camera_device_var.get())
            self.camera_device = cv2.VideoCapture(device_id)
            
            if not self.camera_device.isOpened():
                messagebox.showerror("Camera Error", f"Could not open camera device {device_id}")
                return
            
            # Set camera resolution
            width = int(self.camera_width_var.get())
            height = int(self.camera_height_var.get())
            self.camera_device.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.camera_device.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            self.camera_active = True
            self.camera_btn.config(text="Stop Camera")
            self.status_label.config(text="Camera: Running")
            
            # Start camera thread
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
                
                # Resize frame to fit canvas
                display_frame = cv2.resize(frame, (640, 480))
                
                # Convert to RGB for tkinter
                rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                
                # Store current frame for other operations
                self.current_frame = frame.copy()
                
                # Convert to PhotoImage and display
                from PIL import Image, ImageTk
                pil_image = Image.fromarray(rgb_frame)
                photo = ImageTk.PhotoImage(pil_image)
                
                # Update canvas
                self.camera_canvas.delete("all")
                self.camera_canvas.create_image(320, 240, image=photo)
                self.camera_canvas.image = photo  # Keep reference
                
                # Add calibration overlay if in calibration mode
                if self.calibration_mode:
                    self.draw_calibration_overlay()
                
                time.sleep(1/30)  # ~30 FPS display
                
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
        
        # Add calibration point
        x, y = event.x, event.y
        # Scale to actual frame coordinates
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
        for i, point in enumerate(self.calibration_points):
            # Scale to canvas coordinates
            canvas_x = int(point[0] * 640 / self.current_frame.shape[1])
            canvas_y = int(point[1] * 480 / self.current_frame.shape[0])
            
            # Draw calibration point
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
        """Test the ReID system configuration"""
        if not self.update_config_from_gui():
            return
        
        try:
            # Run basic system tests
            test_results = []
            
            # Test 1: Configuration validity
            test_results.append("✅ Configuration format: Valid")
            
            # Test 2: Camera device
            try:
                device_id = int(self.camera_device_var.get())
                test_camera = cv2.VideoCapture(device_id)
                if test_camera.isOpened():
                    test_results.append("✅ Camera device: Accessible")
                    test_camera.release()
                else:
                    test_results.append("❌ Camera device: Not accessible")
            except:
                test_results.append("❌ Camera device: Error accessing")
            
            # Test 3: File paths
            config_dir = self.config_file.parent
            if config_dir.exists():
                test_results.append("✅ Configuration directory: Exists")
            else:
                test_results.append("❌ Configuration directory: Missing")
            
            # Test 4: Stage geometry
            width = float(self.stage_width_var.get())
            depth = float(self.stage_depth_var.get())
            if width > 0 and depth > 0:
                test_results.append("✅ Stage dimensions: Valid")
            else:
                test_results.append("❌ Stage dimensions: Invalid")
            
            # Test 5: Performance settings
            fps = int(self.target_fps_var.get())
            if 1 <= fps <= 60:
                test_results.append("✅ Target FPS: Reasonable")
            else:
                test_results.append("⚠️ Target FPS: Unusual value")
            
            # Show results
            result_text = "System Test Results:\n\n" + "\n".join(test_results)
            messagebox.showinfo("System Test", result_text)
            
        except Exception as e:
            messagebox.showerror("Test Error", f"Error running system test: {e}")
    
    def reset_defaults(self):
        """Reset configuration to defaults"""
        if messagebox.askyesno("Reset Configuration", 
                              "Reset all settings to default values?\nThis cannot be undone."):
            self.config = self.load_config().__class__.__dict__['load_config'](self)
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

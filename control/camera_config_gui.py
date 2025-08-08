#!/usr/bin/env python3
"""
Multi-Camera Configuration GUI
Configures multiple cameras for the automated followspot system.
"""

import sys
import json
import os
import threading
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import asyncio
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription

@dataclass
class CameraConfig:
    """Configuration for a single camera"""
    server_url: str
    crop_rect: Tuple[int, int, int, int]  # (x, y, width, height)
    position: Tuple[int, int]  # (grid_x, grid_y) position in final layout
    camera_id: str
    enabled: bool = True
    auto_crop: bool = True
    overlap_threshold: float = 0.1  # For automatic seamless cropping

@dataclass
class GridConfig:
    """Grid layout configuration"""
    cameras_per_row: int
    total_cameras: int
    cell_width: int
    cell_height: int
    auto_arrange: bool = True

class CameraConfigGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Multi-Camera Configuration")
        self.root.geometry("1400x900")
        
        # Configuration
        self.config_file = "../config/camera_config.json"
        self.cameras: Dict[str, CameraConfig] = {}
        self.grid_config = GridConfig(2, 4, 320, 240, True)
        self.preview_frames: Dict[str, np.ndarray] = {}
        self.camera_connections: Dict[str, RTCPeerConnection] = {}
        self.running = True
        
        # GUI Variables
        self.camera_preview_labels: Dict[str, tk.Label] = {}
        self.crop_rectangles: Dict[str, Tuple[int, int, int, int]] = {}
        self.dragging = False
        self.drag_start = None
        self.current_camera = None
        
        # Load existing configuration
        self.load_config()
        
        # Setup GUI
        self.setup_gui()
        
        # Update GUI with loaded configuration
        self.refresh_gui_from_config()
        
        # Start preview update thread
        self.preview_thread = threading.Thread(target=self.update_preview_loop, daemon=True)
        self.preview_thread.start()
        
    def setup_gui(self):
        """Setup the main GUI layout"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Camera list and controls
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Right panel - Preview grid
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.setup_camera_controls(left_frame)
        self.setup_preview_grid(right_frame)
        self.setup_menu()
        
    def refresh_gui_from_config(self):
        """Refresh GUI elements with loaded configuration"""
        # Update GUI variables from loaded config
        if hasattr(self, 'cameras_per_row_var'):
            self.cameras_per_row_var.set(self.grid_config.cameras_per_row)
        if hasattr(self, 'cell_width_var'):
            self.cell_width_var.set(self.grid_config.cell_width)
        if hasattr(self, 'cell_height_var'):
            self.cell_height_var.set(self.grid_config.cell_height)
        
        # Update camera list
        self.update_camera_list()
        
        # Update camera grid
        self.update_camera_grid()
        
        # Update grid config to ensure consistency
        self.update_grid_config()
        
        print(f"GUI refreshed with {len(self.cameras)} cameras from configuration")
        
    def setup_menu(self):
        """Setup menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load Config", command=self.load_config_dialog)
        file_menu.add_command(label="Save Config", command=self.save_config)
        file_menu.add_command(label="Save Config As...", command=self.save_config_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Auto-Arrange Grid", command=self.auto_arrange_grid)
        tools_menu.add_command(label="Auto-Crop All", command=self.auto_crop_all)
        tools_menu.add_command(label="Test All Connections", command=self.test_all_connections)
        
    def setup_camera_controls(self, parent):
        """Setup camera control panel"""
        # Title
        title_label = ttk.Label(parent, text="Camera Configuration", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Grid settings
        grid_frame = ttk.LabelFrame(parent, text="Grid Settings")
        grid_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(grid_frame, text="Cameras per row:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.cameras_per_row_var = tk.IntVar(value=self.grid_config.cameras_per_row)
        cameras_per_row_spinbox = ttk.Spinbox(grid_frame, from_=1, to=6, textvariable=self.cameras_per_row_var, width=10)
        cameras_per_row_spinbox.grid(row=0, column=1, padx=5, pady=2)
        cameras_per_row_spinbox.bind('<Return>', self.update_grid_config)
        
        ttk.Label(grid_frame, text="Cell width:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.cell_width_var = tk.IntVar(value=self.grid_config.cell_width)
        cell_width_spinbox = ttk.Spinbox(grid_frame, from_=160, to=1920, textvariable=self.cell_width_var, width=10)
        cell_width_spinbox.grid(row=1, column=1, padx=5, pady=2)
        cell_width_spinbox.bind('<Return>', self.update_grid_config)
        
        ttk.Label(grid_frame, text="Cell height:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.cell_height_var = tk.IntVar(value=self.grid_config.cell_height)
        cell_height_spinbox = ttk.Spinbox(grid_frame, from_=120, to=1080, textvariable=self.cell_height_var, width=10)
        cell_height_spinbox.grid(row=2, column=1, padx=5, pady=2)
        cell_height_spinbox.bind('<Return>', self.update_grid_config)
        
        # Camera list
        camera_list_frame = ttk.LabelFrame(parent, text="Cameras")
        camera_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Camera list with scrollbar
        list_container = ttk.Frame(camera_list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.camera_listbox = tk.Listbox(list_container, height=10)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.camera_listbox.yview)
        self.camera_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.camera_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.camera_listbox.bind('<<ListboxSelect>>', self.on_camera_select)
        
        # Camera control buttons
        button_frame = ttk.Frame(camera_list_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Add Camera", command=self.add_camera_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove", command=self.remove_camera).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Edit", command=self.edit_camera_dialog).pack(side=tk.LEFT, padx=2)
        
        # Selected camera details
        details_frame = ttk.LabelFrame(parent, text="Camera Details")
        details_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.details_text = tk.Text(details_frame, height=6, width=30)
        self.details_text.pack(padx=5, pady=5)
        
        # Control buttons
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X)
        
        ttk.Button(control_frame, text="Start Preview", command=self.start_preview).pack(fill=tk.X, pady=2)
        ttk.Button(control_frame, text="Stop Preview", command=self.stop_preview).pack(fill=tk.X, pady=2)
        ttk.Button(control_frame, text="Save & Exit", command=self.save_and_exit).pack(fill=tk.X, pady=2)
        
    def setup_preview_grid(self, parent):
        """Setup camera preview grid"""
        # Title
        title_label = ttk.Label(parent, text="Camera Preview Grid", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Instructions
        instructions = tk.Text(parent, height=3, wrap=tk.WORD)
        instructions.pack(fill=tk.X, pady=(0, 10))
        instructions.insert(tk.END, "Instructions:\n• Click and drag on camera preview to set crop area\n• Right-click to reset crop area\n• Use mouse wheel to adjust crop size")
        instructions.config(state=tk.DISABLED)
        
        # Preview container with scrollbars
        preview_container = ttk.Frame(parent)
        preview_container.pack(fill=tk.BOTH, expand=True)
        
        # Canvas with scrollbars for large grids
        self.preview_canvas = tk.Canvas(preview_container, bg='black')
        v_scrollbar = ttk.Scrollbar(preview_container, orient=tk.VERTICAL, command=self.preview_canvas.yview)
        h_scrollbar = ttk.Scrollbar(preview_container, orient=tk.HORIZONTAL, command=self.preview_canvas.xview)
        
        self.preview_canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame inside canvas for camera grid
        self.preview_frame = ttk.Frame(self.preview_canvas)
        self.preview_canvas.create_window((0, 0), window=self.preview_frame, anchor=tk.NW)
        
        # Bind canvas events
        self.preview_canvas.bind('<Configure>', self.on_canvas_configure)
        self.preview_canvas.bind('<Button-1>', self.on_preview_click)
        self.preview_canvas.bind('<B1-Motion>', self.on_preview_drag)
        self.preview_canvas.bind('<ButtonRelease-1>', self.on_preview_release)
        self.preview_canvas.bind('<Button-3>', self.on_preview_right_click)
        
        # Update camera grid
        self.update_camera_grid()
        
    def update_grid_config(self, event=None):
        """Update grid configuration from GUI"""
        self.grid_config.cameras_per_row = self.cameras_per_row_var.get()
        self.grid_config.cell_width = self.cell_width_var.get()
        self.grid_config.cell_height = self.cell_height_var.get()
        self.grid_config.total_cameras = len(self.cameras)
        
        self.update_camera_grid()
        
    def update_camera_grid(self):
        """Update the camera preview grid layout"""
        # Clear existing preview labels
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        
        self.camera_preview_labels.clear()
        
        if not self.cameras:
            no_cameras_label = ttk.Label(self.preview_frame, text="No cameras configured\nAdd cameras using the controls on the left")
            no_cameras_label.pack(expand=True)
            return
        
        # Calculate grid dimensions
        cameras_per_row = self.grid_config.cameras_per_row
        total_cameras = len(self.cameras)
        rows = (total_cameras + cameras_per_row - 1) // cameras_per_row
        
        # Create camera preview labels
        camera_list = list(self.cameras.keys())
        for i, camera_id in enumerate(camera_list):
            row = i // cameras_per_row
            col = i % cameras_per_row
            
            # Camera frame
            camera_frame = ttk.LabelFrame(self.preview_frame, text=f"{camera_id}")
            camera_frame.grid(row=row, column=col, padx=5, pady=5, sticky=tk.NSEW)
            
            # Preview label
            preview_label = tk.Label(camera_frame, 
                                   width=self.grid_config.cell_width // 8, 
                                   height=self.grid_config.cell_height // 12,
                                   bg='black', text="No Signal", fg='white')
            preview_label.pack(padx=2, pady=2)
            
            # Bind events for crop selection
            preview_label.bind('<Button-1>', lambda e, cam=camera_id: self.start_crop_selection(e, cam))
            preview_label.bind('<B1-Motion>', lambda e, cam=camera_id: self.update_crop_selection(e, cam))
            preview_label.bind('<ButtonRelease-1>', lambda e, cam=camera_id: self.end_crop_selection(e, cam))
            preview_label.bind('<Button-3>', lambda e, cam=camera_id: self.reset_crop_selection(e, cam))
            
            self.camera_preview_labels[camera_id] = preview_label
            
            # Status label
            status_label = ttk.Label(camera_frame, text="Disconnected", foreground='red')
            status_label.pack()
        
        # Update canvas scroll region
        self.preview_frame.update_idletasks()
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
        
    def add_camera_dialog(self):
        """Show dialog to add a new camera"""
        dialog = CameraDialog(self.root, "Add Camera")
        if dialog.result:
            camera_id = dialog.result['camera_id']
            server_url = dialog.result['server_url']
            
            if camera_id in self.cameras:
                messagebox.showerror("Error", f"Camera ID '{camera_id}' already exists")
                return
            
            # Calculate position in grid
            position = self.get_next_grid_position()
            
            camera_config = CameraConfig(
                server_url=server_url,
                crop_rect=(0, 0, self.grid_config.cell_width, self.grid_config.cell_height),
                position=position,
                camera_id=camera_id,
                enabled=True,
                auto_crop=True
            )
            
            self.cameras[camera_id] = camera_config
            self.update_camera_list()
            self.update_camera_grid()
            self.update_grid_config()
            
    def edit_camera_dialog(self):
        """Show dialog to edit selected camera"""
        selection = self.camera_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a camera to edit")
            return
        
        camera_id = self.camera_listbox.get(selection[0])
        camera_config = self.cameras[camera_id]
        
        dialog = CameraDialog(self.root, "Edit Camera", camera_config)
        if dialog.result:
            # Update camera configuration
            camera_config.server_url = dialog.result['server_url']
            # Note: camera_id changes require special handling
            if dialog.result['camera_id'] != camera_id:
                # Remove old entry and add new one
                del self.cameras[camera_id]
                self.cameras[dialog.result['camera_id']] = camera_config
                camera_config.camera_id = dialog.result['camera_id']
            
            self.update_camera_list()
            self.update_camera_details()
            
    def remove_camera(self):
        """Remove selected camera"""
        selection = self.camera_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a camera to remove")
            return
        
        camera_id = self.camera_listbox.get(selection[0])
        
        if messagebox.askyesno("Confirm", f"Remove camera '{camera_id}'?"):
            del self.cameras[camera_id]
            self.update_camera_list()
            self.update_camera_grid()
            self.update_grid_config()
            
    def get_next_grid_position(self) -> Tuple[int, int]:
        """Calculate the next available grid position"""
        total_cameras = len(self.cameras)
        cameras_per_row = self.grid_config.cameras_per_row
        
        row = total_cameras // cameras_per_row
        col = total_cameras % cameras_per_row
        
        return (col, row)
        
    def update_camera_list(self):
        """Update the camera listbox"""
        self.camera_listbox.delete(0, tk.END)
        for camera_id in sorted(self.cameras.keys()):
            self.camera_listbox.insert(tk.END, camera_id)
            
    def on_camera_select(self, event):
        """Handle camera selection in listbox"""
        selection = self.camera_listbox.curselection()
        if selection:
            camera_id = self.camera_listbox.get(selection[0])
            self.current_camera = camera_id
            self.update_camera_details()
            
    def update_camera_details(self):
        """Update camera details display"""
        if not self.current_camera or self.current_camera not in self.cameras:
            self.details_text.delete(1.0, tk.END)
            return
        
        camera = self.cameras[self.current_camera]
        details = f"""Camera ID: {camera.camera_id}
Server URL: {camera.server_url}
Position: {camera.position}
Crop Rect: {camera.crop_rect}
Enabled: {camera.enabled}
Auto Crop: {camera.auto_crop}"""
        
        self.details_text.delete(1.0, tk.END)
        self.details_text.insert(1.0, details)
        
    def start_crop_selection(self, event, camera_id):
        """Start crop rectangle selection"""
        self.current_camera = camera_id
        self.dragging = True
        self.drag_start = (event.x, event.y)
        
    def update_crop_selection(self, event, camera_id):
        """Update crop rectangle during drag"""
        if not self.dragging or camera_id != self.current_camera:
            return
        
        # Visual feedback could be added here
        pass
        
    def end_crop_selection(self, event, camera_id):
        """End crop rectangle selection"""
        if not self.dragging or camera_id != self.current_camera:
            return
        
        self.dragging = False
        
        if self.drag_start and camera_id in self.cameras:
            # Calculate crop rectangle relative to the preview
            start_x, start_y = self.drag_start
            end_x, end_y = event.x, event.y
            
            # Ensure we have a valid rectangle
            x1, x2 = min(start_x, end_x), max(start_x, end_x)
            y1, y2 = min(start_y, end_y), max(start_y, end_y)
            
            # Scale to actual frame size (preview is scaled down)
            preview_label = self.camera_preview_labels[camera_id]
            preview_width = preview_label.winfo_width()
            preview_height = preview_label.winfo_height()
            
            if preview_width > 0 and preview_height > 0:
                scale_x = self.grid_config.cell_width / preview_width
                scale_y = self.grid_config.cell_height / preview_height
                
                crop_rect = (
                    int(x1 * scale_x),
                    int(y1 * scale_y),
                    int((x2 - x1) * scale_x),
                    int((y2 - y1) * scale_y)
                )
                
                self.cameras[camera_id].crop_rect = crop_rect
                self.update_camera_details()
        
        self.drag_start = None
        
    def reset_crop_selection(self, event, camera_id):
        """Reset crop rectangle to full frame"""
        if camera_id in self.cameras:
            self.cameras[camera_id].crop_rect = (0, 0, self.grid_config.cell_width, self.grid_config.cell_height)
            self.update_camera_details()
            
    def auto_arrange_grid(self):
        """Automatically arrange cameras in optimal grid"""
        num_cameras = len(self.cameras)
        if num_cameras == 0:
            return
        
        # Calculate optimal grid dimensions
        if num_cameras == 1:
            cameras_per_row = 1
        elif num_cameras <= 4:
            cameras_per_row = 2
        elif num_cameras <= 9:
            cameras_per_row = 3
        else:
            cameras_per_row = 4
        
        self.cameras_per_row_var.set(cameras_per_row)
        self.update_grid_config()
        
        # Update camera positions
        for i, camera_id in enumerate(sorted(self.cameras.keys())):
            row = i // cameras_per_row
            col = i % cameras_per_row
            self.cameras[camera_id].position = (col, row)
            
        messagebox.showinfo("Success", f"Arranged {num_cameras} cameras in {cameras_per_row}x{(num_cameras + cameras_per_row - 1) // cameras_per_row} grid")
        
    def auto_crop_all(self):
        """Automatically calculate crop rectangles for seamless overlay"""
        if len(self.cameras) < 2:
            messagebox.showinfo("Info", "Auto-crop requires at least 2 cameras")
            return
        
        # This is a placeholder for auto-crop algorithm
        # In a real implementation, this would analyze overlapping regions
        # and calculate optimal crop rectangles for seamless blending
        
        overlap_pixels = int(self.grid_config.cell_width * 0.05)  # 5% overlap
        
        for camera_id, camera in self.cameras.items():
            grid_x, grid_y = camera.position
            
            # Calculate crop based on position to create slight overlap
            x_crop = overlap_pixels if grid_x > 0 else 0
            y_crop = overlap_pixels if grid_y > 0 else 0
            
            width_crop = self.grid_config.cell_width - (overlap_pixels if grid_x < self.grid_config.cameras_per_row - 1 else 0)
            height_crop = self.grid_config.cell_height - (overlap_pixels if grid_y > 0 else 0)
            
            camera.crop_rect = (x_crop, y_crop, width_crop, height_crop)
            
        self.update_camera_details()
        messagebox.showinfo("Success", "Auto-crop applied to all cameras")
        
    def start_preview(self):
        """Start camera preview"""
        if not self.cameras:
            messagebox.showwarning("Warning", "No cameras configured")
            return
        
        # Start async preview in separate thread
        def run_preview():
            asyncio.run(self.connect_all_cameras())
        
        preview_thread = threading.Thread(target=run_preview, daemon=True)
        preview_thread.start()
        
    def stop_preview(self):
        """Stop camera preview"""
        # Close all connections
        for pc in self.camera_connections.values():
            # Schedule close in the event loop
            pass
        
        self.camera_connections.clear()
        self.preview_frames.clear()
        
        # Update preview labels to show disconnected
        for label in self.camera_preview_labels.values():
            label.configure(image='', text="Disconnected")
            
    async def connect_all_cameras(self):
        """Connect to all configured cameras"""
        connection_tasks = []
        for camera_id, camera in self.cameras.items():
            if camera.enabled:
                task = asyncio.create_task(self.connect_to_camera(camera))
                connection_tasks.append(task)
        
        # Wait for all connections
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        successful = sum(1 for result in results if result is True)
        total = len(connection_tasks)
        
        print(f"Connected to {successful}/{total} cameras")
        
    async def connect_to_camera(self, camera_config: CameraConfig) -> bool:
        """Connect to a single camera"""
        pc = RTCPeerConnection()
        self.camera_connections[camera_config.camera_id] = pc
        
        @pc.on("track")
        async def on_track(track):
            if track.kind == "video":
                print(f"Video track received from {camera_config.camera_id}")
                asyncio.create_task(self.receive_frames(track, camera_config.camera_id))
        
        try:
            pc.addTransceiver("video", direction="recvonly")
        except TypeError:
            pass
        
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{camera_config.server_url}/offer",
                    json={
                        "sdp": pc.localDescription.sdp,
                        "type": pc.localDescription.type
                    }
                ) as response:
                    if response.status == 200:
                        answer = await response.json()
                        await pc.setRemoteDescription(
                            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
                        )
                        print(f"Connected to {camera_config.camera_id}")
                        return True
                    else:
                        print(f"Failed to connect to {camera_config.camera_id}: {response.status}")
                        return False
        except Exception as e:
            print(f"Connection error for {camera_config.camera_id}: {e}")
            return False
            
    async def receive_frames(self, track, camera_id: str):
        """Receive frames from camera"""
        while self.running:
            try:
                frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                img_array = frame.to_ndarray(format="bgr24")
                self.preview_frames[camera_id] = img_array
            except asyncio.TimeoutError:
                print(f"Frame timeout for {camera_id}")
                break
            except Exception as e:
                print(f"Error receiving frame from {camera_id}: {e}")
                break
                
    def update_preview_loop(self):
        """Update preview images in GUI thread"""
        while self.running:
            try:
                for camera_id, frame in self.preview_frames.items():
                    if camera_id in self.camera_preview_labels:
                        # Apply crop if configured
                        if camera_id in self.cameras:
                            crop_rect = self.cameras[camera_id].crop_rect
                            x, y, w, h = crop_rect
                            if x + w <= frame.shape[1] and y + h <= frame.shape[0]:
                                cropped_frame = frame[y:y+h, x:x+w]
                            else:
                                cropped_frame = frame
                        else:
                            cropped_frame = frame
                        
                        # Resize for preview
                        preview_size = (200, 150)  # Small preview size
                        resized_frame = cv2.resize(cropped_frame, preview_size)
                        
                        # Convert to PhotoImage
                        rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                        pil_image = Image.fromarray(rgb_frame)
                        photo = ImageTk.PhotoImage(pil_image)
                        
                        # Update label
                        label = self.camera_preview_labels[camera_id]
                        label.configure(image=photo, text="")
                        label.image = photo  # Keep a reference
                        
            except Exception as e:
                print(f"Error updating preview: {e}")
                
            time.sleep(0.1)  # 10 FPS preview
            
    def test_all_connections(self):
        """Test connections to all cameras"""
        def test_connections():
            results = []
            for camera_id, camera in self.cameras.items():
                try:
                    # Simple HTTP test
                    import urllib.request
                    urllib.request.urlopen(camera.server_url, timeout=5)
                    results.append(f"✓ {camera_id}: Connected")
                except Exception as e:
                    results.append(f"✗ {camera_id}: {str(e)}")
            
            # Show results in dialog
            result_text = "\n".join(results)
            messagebox.showinfo("Connection Test Results", result_text)
        
        threading.Thread(target=test_connections, daemon=True).start()
        
    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                
                # Load grid config
                if 'grid_config' in data:
                    grid_data = data['grid_config']
                    self.grid_config = GridConfig(**grid_data)
                
                # Load cameras
                if 'cameras' in data:
                    self.cameras.clear()
                    for camera_data in data['cameras']:
                        camera = CameraConfig(**camera_data)
                        self.cameras[camera.camera_id] = camera
                
                print(f"Loaded configuration from {self.config_file}")
                print(f"Loaded {len(self.cameras)} cameras: {list(self.cameras.keys())}")
                
            except Exception as e:
                print(f"Error loading config: {e}")
                messagebox.showerror("Error", f"Error loading configuration: {e}")
        else:
            print(f"No existing configuration file found: {self.config_file}")
            print("Starting with empty configuration")
                
    def save_config(self):
        """Save current configuration to file"""
        try:
            data = {
                'grid_config': asdict(self.grid_config),
                'cameras': [asdict(camera) for camera in self.cameras.values()]
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"Saved configuration to {self.config_file}")
            messagebox.showinfo("Success", f"Configuration saved to {self.config_file}")
            
        except Exception as e:
            print(f"Error saving config: {e}")
            messagebox.showerror("Error", f"Error saving configuration: {e}")
            
    def load_config_dialog(self):
        """Show dialog to load configuration file"""
        filename = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            self.config_file = filename
            self.load_config()
            # Refresh GUI after loading
            self.refresh_gui_from_config()
            
    def save_config_as(self):
        """Show dialog to save configuration file"""
        filename = filedialog.asksaveasfilename(
            title="Save Configuration As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            self.config_file = filename
            self.save_config()
            
    def save_and_exit(self):
        """Save configuration and exit"""
        self.save_config()
        self.on_closing()
        
    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
        
    def on_preview_click(self, event):
        """Handle click on preview canvas"""
        pass
        
    def on_preview_drag(self, event):
        """Handle drag on preview canvas"""
        pass
        
    def on_preview_release(self, event):
        """Handle release on preview canvas"""
        pass
        
    def on_preview_right_click(self, event):
        """Handle right click on preview canvas"""
        pass
        
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        
        # Close all camera connections
        for pc in self.camera_connections.values():
            # Note: In a real implementation, you'd need to properly close these
            pass
        
        self.root.quit()
        self.root.destroy()
        
    def run(self):
        """Run the GUI application"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

class CameraDialog:
    def __init__(self, parent, title, camera_config=None):
        self.result = None
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x200")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        # Camera ID
        ttk.Label(self.dialog, text="Camera ID:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.camera_id_var = tk.StringVar(value=camera_config.camera_id if camera_config else "")
        camera_id_entry = ttk.Entry(self.dialog, textvariable=self.camera_id_var, width=30)
        camera_id_entry.grid(row=0, column=1, padx=10, pady=5)
        
        # Server URL
        ttk.Label(self.dialog, text="Server URL:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.server_url_var = tk.StringVar(value=camera_config.server_url if camera_config else "http://192.168.1.100:8080")
        server_url_entry = ttk.Entry(self.dialog, textvariable=self.server_url_var, width=30)
        server_url_entry.grid(row=1, column=1, padx=10, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel_clicked).pack(side=tk.LEFT, padx=5)
        
        # Focus on first entry
        camera_id_entry.focus()
        
        # Wait for dialog to close
        self.dialog.wait_window()
        
    def ok_clicked(self):
        """Handle OK button click"""
        camera_id = self.camera_id_var.get().strip()
        server_url = self.server_url_var.get().strip()
        
        if not camera_id:
            messagebox.showerror("Error", "Camera ID is required")
            return
            
        if not server_url:
            messagebox.showerror("Error", "Server URL is required")
            return
        
        self.result = {
            'camera_id': camera_id,
            'server_url': server_url
        }
        
        self.dialog.destroy()
        
    def cancel_clicked(self):
        """Handle Cancel button click"""
        self.dialog.destroy()

def main():
    """Main entry point"""
    app = CameraConfigGUI()
    app.run()

if __name__ == "__main__":
    main()

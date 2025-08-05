#!/usr/bin/env python3
"""
Video Display GUI for Multi-Camera System
Displays composite video feed with IR beacon overlay and coordinate system
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
import threading
import time
import logging
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("video_display_gui")

class VideoDisplayGUI:
    """Main GUI for displaying video feed with IR beacon overlay"""
    
    def __init__(self, camera_manager):
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
        
        # Statistics
        self.fps_var = tk.StringVar(value="FPS: 0.0")
        self.beacon_count_var = tk.StringVar(value="Beacons: 0")
        self.frame_size_var = tk.StringVar(value="Frame: 0x0")
        
        self.setup_ui()
        self.setup_bindings()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
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
        """Setup the control panel with settings and statistics"""
        control_frame = ttk.LabelFrame(parent, text="Controls", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # IR Threshold control
        ttk.Label(control_frame, text="IR Threshold:").grid(row=0, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(control_frame)
        threshold_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        
        threshold_scale = ttk.Scale(threshold_frame, from_=0, to=255, 
                                   variable=self.ir_threshold, orient=tk.HORIZONTAL)
        threshold_scale.grid(row=0, column=0, sticky=(tk.W, tk.E))
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
        
        # Statistics
        stats_frame = ttk.LabelFrame(control_frame, text="Statistics", padding="10")
        stats_frame.grid(row=7, column=0, sticky=(tk.W, tk.E), pady=(20, 0))
        
        ttk.Label(stats_frame, textvariable=self.fps_var).grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.beacon_count_var).grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(stats_frame, textvariable=self.frame_size_var).grid(row=2, column=0, sticky=tk.W, pady=2)
        
        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=8, column=0, sticky=(tk.W, tk.E), pady=(20, 0))
        
        ttk.Button(button_frame, text="Start/Stop", 
                  command=self.toggle_display).grid(row=0, column=0, pady=5)
        
        ttk.Button(button_frame, text="Save Screenshot", 
                  command=self.save_screenshot).grid(row=1, column=0, pady=5)
        
        ttk.Button(button_frame, text="Reset View", 
                  command=self.reset_view).grid(row=2, column=0, pady=5)
        
    def setup_video_display(self, parent):
        """Setup the video display area"""
        video_frame = ttk.LabelFrame(parent, text="Video Feed", padding="10")
        video_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Video display label
        self.video_label = ttk.Label(video_frame, text="No video feed available", 
                                    background="black", foreground="white")
        self.video_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(0, weight=1)
        
        # Mouse click handler for coordinates
        self.video_label.bind("<Button-1>", self.on_video_click)
        
    def setup_status_bar(self, parent):
        """Setup the status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
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
        if self.current_frame is not None:
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
            self.display_thread = threading.Thread(target=self.display_loop, daemon=True)
            self.display_thread.start()
            self.status_var.set("Display started")
            logger.info("Video display started")
            
    def stop_display(self):
        """Stop the video display"""
        self.running = False
        if self.display_thread:
            self.display_thread.join(timeout=1.0)
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
                    # Process frame with IR detection and overlays
                    processed_frame = self.process_frame(composite_frame)
                    
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
                    
                time.sleep(1/30)  # ~30 FPS
                
            except Exception as e:
                logger.error(f"Error in display loop: {e}")
                time.sleep(0.1)
                
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Process frame with IR detection and overlays"""
        processed_frame = frame.copy()
        
        # Store original frame for raw overlay
        raw_frame = frame.copy()
        
        # Detect IR beacons
        beacons, viz_frame = self.camera_manager.detect_ir_beacons_composite(frame)
        
        if self.show_beacons.get():
            processed_frame = viz_frame
            
        # Update beacon count
        self.beacon_count_var.set(f"Beacons: {len(beacons)}")
        
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
            self.video_label.configure(image=self.display_image, text="")
            self.current_frame = frame
            
        except Exception as e:
            logger.error(f"Error displaying frame: {e}")
            
    def display_no_feed_message(self):
        """Display message when no video feed is available"""
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
        
    def on_closing(self):
        """Handle window closing"""
        self.stop_display()
        self.camera_manager.running = False
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

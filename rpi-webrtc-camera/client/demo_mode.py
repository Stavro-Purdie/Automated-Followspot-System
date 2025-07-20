#!/usr/bin/env python3
"""
Demo Mode for Multi-Camera System
Generates simulated video feeds with IR beacons for demonstration purposes.
"""

import cv2
import numpy as np
import time
import math
import random
import threading
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger("demo_mode")

class DemoVideoGenerator:
    """Generates simulated video feeds with moving IR beacons"""
    
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self.frame_count = 0
        self.beacons = []
        self.running = True
        
        # Initialize demo beacons
        self.init_demo_beacons()
    
    def init_demo_beacons(self):
        """Initialize demo IR beacons with random positions and movements"""
        num_beacons = random.randint(1, 3)  # 1-3 beacons per camera
        
        for i in range(num_beacons):
            beacon = {
                'x': random.randint(50, self.width - 50),
                'y': random.randint(50, self.height - 50),
                'speed_x': random.uniform(-2, 2),
                'speed_y': random.uniform(-2, 2),
                'size': random.randint(8, 20),
                'brightness': random.randint(200, 255),
                'pulse_phase': random.uniform(0, 2 * math.pi)
            }
            self.beacons.append(beacon)
    
    def update_beacons(self):
        """Update beacon positions and properties"""
        for beacon in self.beacons:
            # Update position
            beacon['x'] += beacon['speed_x']
            beacon['y'] += beacon['speed_y']
            
            # Bounce off walls
            if beacon['x'] <= 10 or beacon['x'] >= self.width - 10:
                beacon['speed_x'] *= -1
            if beacon['y'] <= 10 or beacon['y'] >= self.height - 10:
                beacon['speed_y'] *= -1
            
            # Keep within bounds
            beacon['x'] = max(10, min(self.width - 10, beacon['x']))
            beacon['y'] = max(10, min(self.height - 10, beacon['y']))
            
            # Update pulsing brightness
            beacon['pulse_phase'] += 0.1
            pulse_factor = (math.sin(beacon['pulse_phase']) + 1) / 2
            beacon['current_brightness'] = int(beacon['brightness'] * (0.7 + 0.3 * pulse_factor))
    
    def generate_frame(self) -> np.ndarray:
        """Generate a single demo frame"""
        # Create base frame with some texture
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Add some random noise for realism
        noise = np.random.randint(0, 30, (self.height, self.width, 3), dtype=np.uint8)
        frame = cv2.add(frame, noise)
        
        # Add some background patterns
        cv2.rectangle(frame, (50, 50), (self.width-50, self.height-50), (20, 20, 20), -1)
        
        # Add grid pattern
        for i in range(0, self.width, 50):
            cv2.line(frame, (i, 0), (i, self.height), (10, 10, 10), 1)
        for i in range(0, self.height, 50):
            cv2.line(frame, (0, i), (self.width, i), (10, 10, 10), 1)
        
        # Update and draw beacons
        self.update_beacons()
        
        for beacon in self.beacons:
            # Draw IR beacon as bright white circle
            center = (int(beacon['x']), int(beacon['y']))
            radius = beacon['size']
            brightness = beacon.get('current_brightness', beacon['brightness'])
            
            # Draw beacon with gradient effect
            cv2.circle(frame, center, radius, (brightness, brightness, brightness), -1)
            cv2.circle(frame, center, radius//2, (255, 255, 255), -1)
            
            # Add slight bloom effect
            cv2.circle(frame, center, radius + 3, (brightness//3, brightness//3, brightness//3), 2)
        
        # Add demo watermark
        cv2.putText(frame, "DEMO MODE", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"Frame: {self.frame_count}", (10, self.height - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
        
        self.frame_count += 1
        return frame

class DemoCameraManager:
    """Manages multiple demo camera feeds"""
    
    def __init__(self, camera_configs: Dict):
        self.camera_configs = camera_configs
        self.generators = {}
        self.latest_frames = {}
        self.frame_lock = threading.Lock()
        self.running = True
        
        # Initialize generators for each camera
        for camera_id, config in camera_configs.items():
            if config.enabled:
                # Use crop dimensions if available, otherwise default
                crop_rect = config.crop_rect
                width = crop_rect[2] if crop_rect[2] > 0 else 640
                height = crop_rect[3] if crop_rect[3] > 0 else 480
                
                self.generators[camera_id] = DemoVideoGenerator(width, height)
        
        # Start generation threads
        self.start_generation_threads()
    
    def start_generation_threads(self):
        """Start frame generation threads for each camera"""
        for camera_id, generator in self.generators.items():
            thread = threading.Thread(
                target=self.generate_frames_for_camera,
                args=(camera_id, generator),
                daemon=True
            )
            thread.start()
            logger.info(f"Started demo feed for camera {camera_id}")
    
    def generate_frames_for_camera(self, camera_id: str, generator: DemoVideoGenerator):
        """Generate frames for a specific camera"""
        fps = 15  # Reduced FPS for better performance
        frame_time = 1.0 / fps
        
        while self.running:
            start_time = time.time()
            
            # Generate frame
            frame = generator.generate_frame()
            
            # Store frame
            with self.frame_lock:
                self.latest_frames[camera_id] = frame
            
            # Maintain FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_time - elapsed)
            time.sleep(sleep_time)
    
    def get_latest_frames(self) -> Dict[str, np.ndarray]:
        """Get latest frames from all cameras"""
        with self.frame_lock:
            return self.latest_frames.copy()
    
    def stop(self):
        """Stop all generation threads"""
        self.running = False
        logger.info("Stopped all demo camera feeds")

if __name__ == "__main__":
    # Test demo mode
    import sys
    import os
    
    # Add parent directory to path to import camera config
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Test with some dummy camera configs
    from dataclasses import dataclass
    
    @dataclass
    class TestCameraConfig:
        server_url: str
        crop_rect: tuple
        position: tuple
        camera_id: str
        enabled: bool = True
    
    # Create test configs
    test_configs = {
        "cam_1": TestCameraConfig("http://test:8080", (0, 0, 640, 480), (0, 0), "cam_1"),
        "cam_2": TestCameraConfig("http://test:8080", (0, 0, 640, 480), (1, 0), "cam_2")
    }
    
    # Start demo
    demo_manager = DemoCameraManager(test_configs)
    
    try:
        print("Demo mode running... Press Ctrl+C to stop")
        time.sleep(5)
        
        # Get some frames
        frames = demo_manager.get_latest_frames()
        print(f"Generated frames for cameras: {list(frames.keys())}")
        
        for camera_id, frame in frames.items():
            print(f"Camera {camera_id}: frame shape {frame.shape}")
            
    except KeyboardInterrupt:
        print("Stopping demo...")
    finally:
        demo_manager.stop()

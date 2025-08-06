#!/usr/bin/env python3
"""
Multi-Camera WebRTC Client
Processes multiple camera feeds and combines them into a single stream for IR beacon detection.
"""

import asyncio
import json
import logging
import cv2
import numpy as np
from threading import Thread, Lock
from queue import Queue, Empty
import argparse
import time
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("multi_camera_client")

# Import demo mode and connection dialog
try:
    from demo_mode import DemoCameraManager
    from connection_dialog import show_connection_dialog
    DEMO_MODE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Demo mode not available: {e}")
    DEMO_MODE_AVAILABLE = False

@dataclass
class CameraConfig:
    """Configuration for a single camera"""
    server_url: str
    crop_rect: Tuple[int, int, int, int]  # (x, y, width, height)
    position: Tuple[int, int]  # (grid_x, grid_y) position in final layout
    camera_id: str
    enabled: bool = True
    auto_crop: bool = True
    overlap_threshold: float = 0.1

@dataclass
class GridConfig:
    """Grid layout configuration"""
    cameras_per_row: int
    total_cameras: int
    cell_width: int
    cell_height: int
    auto_arrange: bool = True

class MultiCameraManager:
    def __init__(self, config_file: str = "../config/camera_config.json", demo_mode: bool = False):
        self.config_file = config_file
        self.demo_mode = demo_mode
        self.cameras: Dict[str, CameraConfig] = {}
        self.grid_config = GridConfig(2, 4, 320, 240, True)
        self.camera_connections: Dict[str, RTCPeerConnection] = {}
        self.latest_frames: Dict[str, np.ndarray] = {}
        self.frame_lock = Lock()
        self.running = True
        self.ir_threshold = 200
        self.demo_manager = None
        
        # Load configuration
        self.load_config()
        
        # Initialize demo mode if requested
        if self.demo_mode and DEMO_MODE_AVAILABLE:
            self.init_demo_mode()
        
    def load_config(self):
        """Load configuration from JSON file"""
        if not os.path.exists(self.config_file):
            logger.warning(f"Configuration file {self.config_file} not found. Using default configuration.")
            return
            
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
            
            logger.info(f"Loaded {len(self.cameras)} cameras from {self.config_file}")
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def init_demo_mode(self):
        """Initialize demo mode with simulated cameras"""
        if not DEMO_MODE_AVAILABLE:
            logger.error("Demo mode not available - required modules not found")
            return
        
        logger.info("Initializing demo mode...")
        self.demo_manager = DemoCameraManager(self.cameras)
    
    def get_demo_frames(self) -> Dict[str, np.ndarray]:
        """Get frames from demo mode"""
        if self.demo_manager:
            return self.demo_manager.get_latest_frames()
        return {}
            
    def create_composite_frame(self) -> Optional[np.ndarray]:
        """Create a composite frame from all enabled cameras"""
        enabled_cameras = {k: v for k, v in self.cameras.items() if v.enabled}
        
        if not enabled_cameras:
            return None
        
        # Get frames from appropriate source
        if self.demo_mode and self.demo_manager:
            frame_source = self.demo_manager.get_latest_frames()
        else:
            frame_source = self.latest_frames
        
        if not frame_source:
            return None
        
        # Calculate composite frame dimensions
        composite_width = self.grid_config.cameras_per_row * self.grid_config.cell_width
        composite_height = ((len(enabled_cameras) + self.grid_config.cameras_per_row - 1) // self.grid_config.cameras_per_row) * self.grid_config.cell_height
        
        # Create black canvas
        composite = np.zeros((composite_height, composite_width, 3), dtype=np.uint8)
        
        # Use appropriate lock
        if self.demo_mode:
            # Demo mode has its own locking
            frame_dict = frame_source
        else:
            with self.frame_lock:
                frame_dict = frame_source
        
        for camera_id, config in enabled_cameras.items():
            if camera_id in frame_dict:
                frame = frame_dict[camera_id]
                
                # Apply cropping
                x, y, w, h = config.crop_rect
                if x >= 0 and y >= 0 and x + w <= frame.shape[1] and y + h <= frame.shape[0] and w > 0 and h > 0:
                    cropped = frame[y:y+h, x:x+w]
                else:
                    cropped = frame
                
                # Resize to cell size
                resized = cv2.resize(cropped, (self.grid_config.cell_width, self.grid_config.cell_height))
                
                # Calculate position in composite
                grid_x, grid_y = config.position
                start_x = grid_x * self.grid_config.cell_width
                start_y = grid_y * self.grid_config.cell_height
                end_x = start_x + self.grid_config.cell_width
                end_y = start_y + self.grid_config.cell_height
                
                # Ensure we don't exceed composite bounds
                if end_x <= composite_width and end_y <= composite_height:
                    composite[start_y:end_y, start_x:end_x] = resized
                    
                    # Add camera ID overlay
                    overlay_text = f"{camera_id}"
                    if self.demo_mode:
                        overlay_text += " (DEMO)"
                    
                    cv2.putText(
                        composite,
                        overlay_text,
                        (start_x + 10, start_y + 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255) if not self.demo_mode else (255, 255, 0),
                        1
                    )
        
        return composite
        
    def detect_ir_beacons_composite(self, composite_frame: np.ndarray) -> Tuple[List, np.ndarray]:
        """Detect IR beacons across the composite frame using existing detection logic"""
        if composite_frame is None:
            return [], None
        
        # Convert to grayscale
        if len(composite_frame.shape) == 3:
            gray_frame = cv2.cvtColor(composite_frame, cv2.COLOR_BGR2GRAY)
        else:
            gray_frame = composite_frame.copy()
        
        # Apply threshold to isolate bright spots (potential IR beacons)
        _, thresholded = cv2.threshold(gray_frame, self.ir_threshold, 255, cv2.THRESH_BINARY)
        
        # Find contours in the thresholded image
        contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Create visualization
        viz_frame = composite_frame.copy()
        beacons = []
        
        # Draw rectangles around detected beacons
        for contour in contours:
            # Calculate center of contour
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Calculate area
                area = cv2.contourArea(contour)
                
                # Filter out small noise
                if area > 15:  # Minimum area threshold
                    # Get bounding rectangle
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Draw rectangle around beacon
                    cv2.rectangle(viz_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    
                    # Draw crosshair at center
                    cv2.line(viz_frame, (cx - 10, cy), (cx + 10, cy), (0, 255, 255), 1)
                    cv2.line(viz_frame, (cx, cy - 10), (cx, cy + 10), (0, 255, 255), 1)
                    
                    # Add text with area
                    cv2.putText(
                        viz_frame,
                        f"Area: {area:.0f}",
                        (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255),
                        1
                    )
                    
                    # Determine which camera this beacon belongs to
                    camera_id = self.get_camera_for_position(cx, cy)
                    
                    # Add to beacons list
                    beacons.append({
                        "center": (cx, cy),
                        "area": area,
                        "bounds": (x, y, w, h),
                        "camera_id": camera_id
                    })
        
        return beacons, viz_frame
        
    def get_camera_for_position(self, x: int, y: int) -> str:
        """Determine which camera a pixel position belongs to"""
        grid_x = x // self.grid_config.cell_width
        grid_y = y // self.grid_config.cell_height
        
        for camera_id, config in self.cameras.items():
            if config.enabled and config.position == (grid_x, grid_y):
                return camera_id
        
        return "unknown"
        
    def apply_seamless_blending(self, composite_frame: np.ndarray) -> np.ndarray:
        """Apply seamless blending to eliminate visible seams between cameras"""
        if composite_frame is None:
            return None
        
        blended = composite_frame.copy()
        
        # Apply feathering at camera boundaries
        for camera_id, config in self.cameras.items():
            if not config.enabled or camera_id not in self.latest_frames:
                continue
            
            grid_x, grid_y = config.position
            start_x = grid_x * self.grid_config.cell_width
            start_y = grid_y * self.grid_config.cell_height
            end_x = start_x + self.grid_config.cell_width
            end_y = start_y + self.grid_config.cell_height
            
            # Apply feathering on right edge (if not last column)
            if grid_x < self.grid_config.cameras_per_row - 1:
                feather_width = int(self.grid_config.cell_width * config.overlap_threshold)
                if feather_width > 0:
                    for i in range(feather_width):
                        alpha = (feather_width - i) / feather_width
                        x_pos = end_x - feather_width + i
                        if x_pos < composite_frame.shape[1]:
                            blended[start_y:end_y, x_pos] = (
                                alpha * blended[start_y:end_y, x_pos] +
                                (1 - alpha) * composite_frame[start_y:end_y, x_pos]
                            ).astype(np.uint8)
            
            # Apply feathering on bottom edge (if not last row)
            total_rows = (len([c for c in self.cameras.values() if c.enabled]) + self.grid_config.cameras_per_row - 1) // self.grid_config.cameras_per_row
            if grid_y < total_rows - 1:
                feather_height = int(self.grid_config.cell_height * config.overlap_threshold)
                if feather_height > 0:
                    for i in range(feather_height):
                        alpha = (feather_height - i) / feather_height
                        y_pos = end_y - feather_height + i
                        if y_pos < composite_frame.shape[0]:
                            blended[y_pos, start_x:end_x] = (
                                alpha * blended[y_pos, start_x:end_x] +
                                (1 - alpha) * composite_frame[y_pos, start_x:end_x]
                            ).astype(np.uint8)
        
        return blended

async def receive_track_for_camera(track, camera_id: str, manager: MultiCameraManager):
    """Process incoming video track frames for a specific camera"""
    logger.info(f"Receiving video track for camera {camera_id}")
    consecutive_errors = 0
    max_errors = 30
    
    while manager.running:
        try:
            frame = await asyncio.wait_for(track.recv(), timeout=5.0)
            img_array = frame.to_ndarray(format="bgr24")
            consecutive_errors = 0
            
            # Update latest frame
            with manager.frame_lock:
                manager.latest_frames[camera_id] = img_array
                
        except asyncio.TimeoutError:
            consecutive_errors += 1
            logger.warning(f"Frame timeout for camera {camera_id} ({consecutive_errors}/{max_errors})")
            
            if consecutive_errors >= max_errors:
                logger.error(f"Too many timeouts for camera {camera_id}, stopping")
                break
                
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error receiving frame from camera {camera_id}: {e}")
            
            if consecutive_errors >= max_errors:
                break

async def connect_to_camera(camera_config: CameraConfig, manager: MultiCameraManager) -> bool:
    """Connect to a single camera"""
    pc = RTCPeerConnection()
    manager.camera_connections[camera_config.camera_id] = pc
    
    @pc.on("track")
    async def on_track(track):
        if track.kind == "video":
            logger.info(f"Video track received from camera {camera_config.camera_id}")
            asyncio.create_task(receive_track_for_camera(track, camera_config.camera_id, manager))
    
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Camera {camera_config.camera_id} connection state: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            # Remove from latest frames if connection fails
            with manager.frame_lock:
                if camera_config.camera_id in manager.latest_frames:
                    del manager.latest_frames[camera_config.camera_id]
    
    try:
        pc.addTransceiver("video", direction="recvonly")
    except TypeError:
        logger.warning(f"Transceiver error for camera {camera_config.camera_id}")
    
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
                    logger.info(f"Connected to camera {camera_config.camera_id}")
                    return True
                else:
                    logger.error(f"Failed to connect to camera {camera_config.camera_id}: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Connection error for camera {camera_config.camera_id}: {e}")
        return False

def process_and_display_composite(manager: MultiCameraManager, dry_run: bool = False):
    """Display the composite frame with IR beacon detection"""
    if not dry_run:
        try:
            cv2.namedWindow("Multi-Camera Composite", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Multi-Camera Composite", 1000, 750)
            
            cv2.namedWindow("IR Beacon Detection", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("IR Beacon Detection", 1000, 750)
            
            cv2.namedWindow("Seamless Blend", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Seamless Blend", 1000, 750)
        except Exception as e:
            logger.warning(f"Could not create display windows (headless mode?): {e}")
            dry_run = True
    
    frame_count = 0
    fps_start_time = time.time()
    
    while manager.running:
        try:
            composite = manager.create_composite_frame()
            
            if composite is not None:
                # Detect beacons across composite
                beacons, processed_frame = manager.detect_ir_beacons_composite(composite)
                
                # Apply seamless blending
                blended_frame = manager.apply_seamless_blending(composite)
                
                # Create hot/cold visualization
                gray_composite = cv2.cvtColor(composite, cv2.COLOR_BGR2GRAY)
                _, hot_cold = cv2.threshold(gray_composite, manager.ir_threshold, 255, cv2.THRESH_BINARY)
                hot_cold_colored = cv2.applyColorMap(hot_cold, cv2.COLORMAP_HOT)
                
                # Add FPS counter
                frame_count += 1
                if frame_count % 30 == 0:  # Update every 30 frames
                    fps = frame_count / (time.time() - fps_start_time)
                    cv2.putText(processed_frame, f"FPS: {fps:.1f}", (10, 60), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Add beacon count
                cv2.putText(processed_frame, f"Beacons: {len(beacons)}", (10, 90), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Display frames
                if not dry_run:
                    try:
                        cv2.imshow("Multi-Camera Composite", processed_frame)
                        cv2.imshow("IR Beacon Detection", hot_cold_colored)
                        if blended_frame is not None:
                            cv2.imshow("Seamless Blend", blended_frame)
                    except Exception as e:
                        logger.warning(f"Could not display frames: {e}")
                        dry_run = True
                else:
                    # In dry run mode, just log the status
                    logger.info(f"Processed composite frame: {composite.shape}, Beacons: {len(beacons)}")
                
                # Handle keyboard input
                key = 0xFF  # Default to no key pressed
                if not dry_run:
                    try:
                        key = cv2.waitKey(30) & 0xFF
                    except Exception as e:
                        logger.debug(f"Input handling error: {e}")
                        dry_run = True  # Fall back to dry run mode
                else:
                    # In dry run, add small delay to prevent busy-waiting
                    time.sleep(0.1)
                
                if key == ord('q'):
                    manager.running = False
                    break
                elif key in [ord('+'), ord('=')]:
                    manager.ir_threshold = min(250, manager.ir_threshold + 5)
                    logger.info(f"IR threshold: {manager.ir_threshold}")
                elif key == ord('-'):
                    manager.ir_threshold = max(10, manager.ir_threshold - 5)
                    logger.info(f"IR threshold: {manager.ir_threshold}")
                elif key == ord('s'):
                    timestamp = int(time.time())
                    cv2.imwrite(f"composite_{timestamp}.jpg", processed_frame)
                    cv2.imwrite(f"composite_ir_{timestamp}.jpg", hot_cold_colored)
                    if blended_frame is not None:
                        cv2.imwrite(f"composite_blend_{timestamp}.jpg", blended_frame)
                    logger.info(f"Saved composite snapshots")
                elif key == ord('r'):
                    # Reload configuration
                    manager.load_config()
                    logger.info("Configuration reloaded")
                    
            else:
                # Show waiting message
                if not dry_run:
                    waiting_frame = np.zeros((600, 1000, 3), dtype=np.uint8)
                    cv2.putText(waiting_frame, "Waiting for camera connections...", 
                               (200, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                    cv2.putText(waiting_frame, f"Configured cameras: {len(manager.cameras)}", 
                               (300, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    try:
                        cv2.imshow("Multi-Camera Composite", waiting_frame)
                        cv2.waitKey(100)
                    except Exception as e:
                        logger.warning(f"Could not display waiting frame: {e}")
                        dry_run = True
                else:
                    # In dry run mode, just log the waiting status
                    logger.info(f"Waiting for camera connections... Configured cameras: {len(manager.cameras)}")
                    time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in display loop: {e}")
            time.sleep(0.1)
    
    if not dry_run:
        cv2.destroyAllWindows()

async def run_multi_camera_client(config_file: str, dry_run: bool = False):
    """Main multi-camera client with connection retry and demo mode support"""
    retry_count = 0
    max_retries = 3
    
    while retry_count <= max_retries:
        manager = MultiCameraManager(config_file, demo_mode=False)
        
        if not manager.cameras:
            logger.error("No cameras configured. Please run camera_config_gui.py first to configure cameras.")
            return
        
        # Start display thread
        display_thread = Thread(target=process_and_display_composite, args=(manager, dry_run), daemon=True)
        display_thread.start()
        
        # Connect to all enabled cameras
        connection_tasks = []
        enabled_cameras = [config for config in manager.cameras.values() if config.enabled]
        
        if not enabled_cameras:
            logger.error("No enabled cameras found in configuration.")
            manager.running = False
            return
        
        for config in enabled_cameras:
            task = asyncio.create_task(connect_to_camera(config, manager))
            connection_tasks.append(task)
        
        # Wait for all connections
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        successful_connections = sum(1 for result in results if result is True)
        failed_cameras = [
            enabled_cameras[i].camera_id for i, result in enumerate(results) 
            if result is not True
        ]
        
        logger.info(f"Connected to {successful_connections}/{len(connection_tasks)} cameras")
        
        # Handle connection results
        if successful_connections == len(connection_tasks):
            # All cameras connected successfully
            logger.info("All cameras connected successfully!")
            break
        elif successful_connections > 0:
            # Partial success - let user choose
            if DEMO_MODE_AVAILABLE and not dry_run:
                choice = show_connection_dialog(
                    failed_cameras=failed_cameras,
                    total_cameras=len(enabled_cameras)
                )
            else:
                choice = "continue"  # In dry-run mode, just continue
            
            if choice == "continue":
                logger.info(f"Continuing with {successful_connections} connected camera(s)")
                break
            elif choice == "retry":
                retry_count += 1
                if retry_count <= max_retries:
                    logger.info(f"Retrying connections (attempt {retry_count}/{max_retries})...")
                    manager.running = False
                    await cleanup_connections(manager)
                    display_thread.join(timeout=2.0)
                    continue
                else:
                    logger.error("Maximum retry attempts reached")
                    choice = "demo" if DEMO_MODE_AVAILABLE else "exit"
            
            if choice == "demo" and DEMO_MODE_AVAILABLE:
                logger.info("Entering demo mode...")
                manager.running = False
                await cleanup_connections(manager)
                display_thread.join(timeout=2.0)
                return await run_demo_mode(config_file, dry_run)
            elif choice == "exit":
                logger.info("User chose to exit")
                manager.running = False
                await cleanup_connections(manager)
                return
        else:
            # No connections successful
            if DEMO_MODE_AVAILABLE and not dry_run:
                choice = show_connection_dialog(
                    failed_cameras=failed_cameras,
                    total_cameras=len(enabled_cameras)
                )
            else:
                choice = "exit"  # In dry-run mode, just exit if no connections
            
            if choice == "retry":
                retry_count += 1
                if retry_count <= max_retries:
                    logger.info(f"Retrying connections (attempt {retry_count}/{max_retries})...")
                    manager.running = False
                    await cleanup_connections(manager)
                    display_thread.join(timeout=2.0)
                    continue
                else:
                    logger.error("Maximum retry attempts reached")
                    choice = "demo" if DEMO_MODE_AVAILABLE else "exit"
            
            if choice == "demo" and DEMO_MODE_AVAILABLE:
                logger.info("Entering demo mode...")
                manager.running = False
                await cleanup_connections(manager)
                display_thread.join(timeout=2.0)
                return await run_demo_mode(config_file, dry_run)
            else:
                logger.error("Failed to connect to any cameras.")
                manager.running = False
                await cleanup_connections(manager)
                return
    
    # Keep running with successful connections
    try:
        while manager.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        manager.running = False
        await cleanup_connections(manager)
        display_thread.join(timeout=2.0)

async def run_demo_mode(config_file: str, dry_run: bool = False):
    """Run the system in demo mode with simulated cameras"""
    if not DEMO_MODE_AVAILABLE:
        logger.error("Demo mode not available - required modules not found")
        return
    
    logger.info("Starting demo mode...")
    manager = MultiCameraManager(config_file, demo_mode=True)
    
    if not manager.cameras:
        logger.error("No cameras configured for demo mode.")
        return
    
    # Start display thread for demo
    display_thread = Thread(target=process_and_display_composite, args=(manager, dry_run), daemon=True)
    display_thread.start()
    
    logger.info("Demo mode active - all features available with simulated data")
    
    try:
        while manager.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        manager.running = False
        if manager.demo_manager:
            manager.demo_manager.stop()
        display_thread.join(timeout=2.0)

async def cleanup_connections(manager):
    """Clean up camera connections"""
    for pc in manager.camera_connections.values():
        try:
            await pc.close()
        except Exception as e:
            logger.debug(f"Error closing connection: {e}")
    manager.camera_connections.clear()

def main():
    parser = argparse.ArgumentParser(description="Multi-Camera WebRTC Client")
    parser.add_argument("--config", type=str, default="../config/camera_config.json",
                        help="Configuration file path (default: ../config/camera_config.json)")
    parser.add_argument("--configure", action="store_true",
                        help="Launch configuration GUI")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without display windows (headless mode)")
    parser.add_argument("--demo", action="store_true",
                        help="Start directly in demo mode")
    
    args = parser.parse_args()
    
    if args.configure:
        # Launch configuration GUI
        try:
            import subprocess
            import sys
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_script = os.path.join(script_dir, "camera_config_gui.py")
            subprocess.run([sys.executable, config_script])
        except Exception as e:
            logger.error(f"Error launching configuration GUI: {e}")
            logger.info("Please run 'python camera_config_gui.py' manually to configure cameras.")
        return
    
    if not os.path.exists(args.config):
        logger.error(f"Configuration file '{args.config}' not found.")
        logger.info("Run with --configure flag to create configuration, or 'python camera_config_gui.py'")
        return
    
    logger.info(f"Starting multi-camera client with configuration: {args.config}")
    if args.dry_run:
        logger.info("Running in dry-run mode (no display windows)")
    if args.demo:
        logger.info("Starting in demo mode")
    
    logger.info("Controls:")
    logger.info("  q - quit (when display is available)")
    logger.info("  +/- - adjust IR threshold")
    logger.info("  s - save snapshots")
    logger.info("  r - reload configuration")
    
    try:
        if args.demo and DEMO_MODE_AVAILABLE:
            asyncio.run(run_demo_mode(args.config, args.dry_run))
        else:
            asyncio.run(run_multi_camera_client(args.config, args.dry_run))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Multi-camera client shutdown complete")

if __name__ == "__main__":
    main()

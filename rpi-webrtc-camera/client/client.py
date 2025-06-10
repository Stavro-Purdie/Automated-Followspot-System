import asyncio
import json
import logging
import cv2
import numpy as np
import argparse
import sys
import os
import fractions
from threading import Thread
from queue import Queue, Empty

import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaPlayer

# Import the IR processing functions from the server directory
sys.path.insert(0, os.path.abspath('../server'))
from ir_processor import analyze_ir_beacons

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webrtc_client")

# Queue for passing frames between asyncio and OpenCV threads
frame_queue = Queue(maxsize=10)

# Global variables for the application state
remote_track = None
pc = None
running = True
threshold = 180  # Default IR detection threshold

class FrameProcessor:
    """Process and display frames with IR beacon detection"""
    
    def __init__(self):
        self.current_frame = None
        self.processed_frames = 0
        self.show_ir_mode = True  # Start with IR detection enabled
        
    def process_frame(self, frame):
        """Process a frame, detecting and highlighting IR beacons"""
        if frame is None:
            return None
            
        # Make a copy to avoid modifying the original
        display_frame = frame.copy()
        
        if self.show_ir_mode:
            # Detect IR beacons
            beacons = analyze_ir_beacons(frame, threshold=threshold)
            
            # Draw rectangles around detected beacons
            for beacon in beacons:
                center = beacon["center"]
                area = beacon["area"]
                radius = max(10, int(np.sqrt(area)))
                
                # Calculate rectangle coordinates
                x1 = max(0, center[0] - radius)
                y1 = max(0, center[1] - radius)
                x2 = min(frame.shape[1], center[0] + radius)
                y2 = min(frame.shape[0], center[1] + radius)
                
                # Draw red rectangle around beacon
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                
                # Add text with area information
                cv2.putText(
                    display_frame,
                    f"Area: {area:.0f}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    1
                )
        
            # Add threshold information
            cv2.putText(
                display_frame,
                f"IR Threshold: {threshold} (use +/- to adjust)",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )
        
        self.processed_frames += 1
        return display_frame

def process_and_display_frames():
    """Frame processing loop - runs in a separate thread"""
    global running, threshold
    
    cv2.namedWindow("WebRTC IR Camera Feed", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("WebRTC IR Camera Feed", 1280, 720)
    
    processor = FrameProcessor()
    
    while running:
        try:
            # Get frame from queue with timeout
            frame = frame_queue.get(timeout=1.0)
            
            # Process frame and add IR detection
            display_frame = processor.process_frame(frame)
            
            if display_frame is not None:
                # Display the processed frame
                cv2.imshow("WebRTC IR Camera Feed", display_frame)
                
                # Process keyboard input
                key = cv2.waitKey(1) & 0xFF
                
                # Quit on 'q' key
                if key == ord('q'):
                    running = False
                    break
                    
                # Toggle IR detection mode with 'i' key
                elif key == ord('i'):
                    processor.show_ir_mode = not processor.show_ir_mode
                    mode_str = "ON" if processor.show_ir_mode else "OFF"
                    logger.info(f"IR Detection mode: {mode_str}")
                
                # Save snapshot with 's' key
                elif key == ord('s'):
                    filename = f"snapshot_{processor.processed_frames}.jpg"
                    cv2.imwrite(filename, display_frame)
                    logger.info(f"Saved snapshot to {filename}")
                
                # Increase threshold with '+' or '=' key
                elif key in [ord('+'), ord('=')]:
                    threshold = min(255, threshold + 5)
                    logger.info(f"IR threshold increased to {threshold}")
                
                # Decrease threshold with '-' key
                elif key == ord('-'):
                    threshold = max(10, threshold - 5)
                    logger.info(f"IR threshold decreased to {threshold}")
                
        except Empty:
            # No frames available, continue
            pass
        except Exception as e:
            logger.error(f"Error in display loop: {e}")
            break
    
    cv2.destroyAllWindows()
    logger.info("Display thread stopped")

class VideoTrackReceiver:
    """Handles receiving and processing WebRTC video tracks"""
    
    def __init__(self):
        self.track = None
    
    async def receive_track(self, track):
        """Process incoming video track"""
        self.track = track
        logger.info(f"Receiving track: {track.kind}")
        
        while running:
            try:
                # Get next frame from track
                frame = await track.recv()
                
                # Convert to numpy array for OpenCV
                img_array = frame.to_ndarray(format="bgr24")
                
                # Put frame in queue for processing thread
                try:
                    # Use put_nowait to avoid blocking if queue is full
                    if not frame_queue.full():
                        frame_queue.put_nowait(img_array)
                except Exception as e:
                    logger.warning(f"Could not queue frame: {e}")
            
            except Exception as e:
                logger.error(f"Error receiving frame: {e}")
                break

async def connect_to_server(server_url):
    """Establish WebRTC connection with server"""
    global pc
    
    # Create a new RTCPeerConnection
    pc = RTCPeerConnection()
    
    # Set up video receiver
    receiver = VideoTrackReceiver()
    
    @pc.on("track")
    async def on_track(track):
        logger.info(f"Track received: {track.kind}")
        if track.kind == "video":
            await receiver.receive_track(track)
    
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            # Signal to stop processing
            global running
            running = False
    
    # Add a transceiver to explicitly request video with recvonly direction
    pc.addTransceiver("video", direction="recvonly")
    
    # Create an offer with specific constraints
    offer = await pc.createOffer({
        "offerToReceiveVideo": True,
        "offerToReceiveAudio": False
    })
    await pc.setLocalDescription(offer)
    
    # Send the offer to the server via HTTP
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server_url}/offer",
            json={
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }
        ) as response:
            # Check if the request was successful
            if response.status == 200:
                # Parse the server's answer
                answer = await response.json()
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
                )
            else:
                error_text = await response.text()
                logger.error(f"Server error: {response.status} - {error_text}")
                return False
    
    return True

async def run_client(server_url):
    """Main client coroutine"""
    global running
    
    # Connect to the WebRTC server
    connected = await connect_to_server(server_url)
    
    if not connected:
        logger.error("Failed to connect to server")
        return
    
    logger.info(f"Connected to {server_url}")
    
    # Keep the connection alive while display thread is running
    while running:
        await asyncio.sleep(1)
    
    # Clean up WebRTC connection
    if pc:
        await pc.close()
        logger.info("WebRTC connection closed")

def main():
    global running
    
    parser = argparse.ArgumentParser(description="WebRTC Client with IR Beacon Detection")
    parser.add_argument("--server", type=str, default="http://localhost:8080",
                        help="WebRTC signaling server URL (default: http://localhost:8080)")
    parser.add_argument("--threshold", type=int, default=180,
                        help="Initial IR detection threshold (0-255, default: 180)")
    
    args = parser.parse_args()
    global threshold
    threshold = args.threshold
    
    # Start OpenCV display thread
    display_thread = Thread(target=process_and_display_frames, daemon=True)
    display_thread.start()
    
    try:
        # Run the asyncio event loop
        asyncio.run(run_client(args.server))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Signal threads to stop
        running = False
        
        # Wait for display thread to finish
        display_thread.join(timeout=2.0)
        
        logger.info("Client shutdown complete")

if __name__ == "__main__":
    main()
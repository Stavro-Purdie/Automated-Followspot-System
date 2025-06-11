import asyncio
import json
import logging
import cv2
import numpy as np
from threading import Thread
from queue import Queue, Empty
import argparse
import time

import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webrtc_client")

# Queue for passing frames between asyncio and OpenCV threads
frame_queue = Queue(maxsize=10)

# Global variables
pc = None
running = True

def detect_ir_beacons(frame, threshold=200):
    """
    Detect IR beacons in a frame
    
    Args:
        frame: Input image frame
        threshold: Brightness threshold for IR detection (default: 200)
    
    Returns:
        beacons: List of dictionaries containing beacon information
        viz_frame: Frame with beacon boundaries highlighted
    """
    # Make a copy of the frame to draw on
    viz_frame = frame.copy()
    
    # Convert to grayscale
    if len(frame.shape) == 3:
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray_frame = frame.copy()
    
    # Apply threshold to isolate bright spots (potential IR beacons)
    _, thresholded = cv2.threshold(gray_frame, threshold, 255, cv2.THRESH_BINARY)
    
    # Find contours in the thresholded image
    contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Store beacon information
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
                
                # Add to beacons list
                beacons.append({
                    "center": (cx, cy),
                    "area": area,
                    "bounds": (x, y, w, h)
                })
    
    # Add threshold value to the image
    cv2.putText(
        viz_frame,
        f"IR Threshold: {threshold} (Press +/- to adjust)",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2
    )
    
    return beacons, viz_frame

# Add a global threshold variable
ir_threshold = 200

# Modify the process_and_display_frames function to include IR detection
def process_and_display_frames():
    """Display frames from the queue in an OpenCV window"""
    global running, ir_threshold  # Add ir_threshold to global declaration
    
    cv2.namedWindow("WebRTC IR Camera Feed", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("WebRTC IR Camera Feed", 320, 240)
    
    # Create a second window for IR visualization
    cv2.namedWindow("IR Beacon Detection", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("IR Beacon Detection", 320, 240)
    
    show_ir = True  # Toggle for IR detection display
    
    # Add a variable to track the current focus distance
    current_focus = 0.5
    
    while running:
        try:
            # Get frame from queue with timeout
            frame = frame_queue.get(timeout=1.0)
            
            if frame is not None:
                # Process for IR beacons
                beacons, processed_frame = detect_ir_beacons(frame, threshold=ir_threshold)
                
                # Create a separate hot/cold visualization
                if len(frame.shape) == 3:
                    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                else:
                    gray_frame = frame
                
                # Create a black and white visualization where white is "hot"
                _, hot_cold_viz = cv2.threshold(gray_frame, ir_threshold, 255, cv2.THRESH_BINARY)
                
                # Apply some color mapping for better visualization
                hot_cold_colored = cv2.applyColorMap(hot_cold_viz, cv2.COLORMAP_HOT)
                
                # Display the processed frame with beacon boundaries
                cv2.imshow("WebRTC IR Camera Feed", processed_frame)
                
                # Display the hot/cold visualization
                cv2.imshow("IR Beacon Detection", hot_cold_colored)
                
                # Process keyboard input
                key = cv2.waitKey(1) & 0xFF
                
                # Quit on 'q' key
                if key == ord('q'):
                    running = False
                    break
                
                # Toggle IR visualization with 'i' key
                elif key == ord('i'):
                    show_ir = not show_ir
                    logger.info(f"IR visualization: {'ON' if show_ir else 'OFF'}")
                
                # Save snapshot with 's' key
                elif key == ord('s'):
                    timestamp = int(time.time())
                    filename_main = f"snapshot_{timestamp}.jpg"
                    filename_ir = f"snapshot_ir_{timestamp}.jpg"
                    cv2.imwrite(filename_main, processed_frame)
                    cv2.imwrite(filename_ir, hot_cold_colored)
                    logger.info(f"Saved snapshots as {filename_main} and {filename_ir}")
                
                # Adjust threshold with + and - keys
                elif key in [ord('+'), ord('=')]:
                    ir_threshold = min(250, ir_threshold + 5)
                    logger.info(f"IR threshold increased to {ir_threshold}")
                
                elif key == ord('-'):
                    ir_threshold = max(10, ir_threshold - 5)
                    logger.info(f"IR threshold decreased to {ir_threshold}")
                
                # Toggle auto-focus with 'a' key
                elif key == ord('a'):
                    asyncio.run_coroutine_threadsafe(
                        set_camera_focus(server_url, mode="auto"),
                        asyncio.get_event_loop()
                    )
                    logger.info("Auto-focus enabled")
                
                # Adjust manual focus with + and - keys
                elif key in [ord('+'), ord('=')]:
                    # Increase focus distance (0 = close, 1 = far)
                    current_focus = min(1.0, current_focus + 0.05)
                    asyncio.run_coroutine_threadsafe(
                        set_camera_focus(server_url, mode="manual", position=current_focus),
                        asyncio.get_event_loop()
                    )
                    logger.info(f"Focus distance increased: {current_focus:.2f}")
                
                elif key == ord('-'):
                    # Decrease focus distance
                    current_focus = max(0.0, current_focus - 0.05)
                    asyncio.run_coroutine_threadsafe(
                        set_camera_focus(server_url, mode="manual", position=current_focus),
                        asyncio.get_event_loop()
                    )
                    logger.info(f"Focus distance decreased: {current_focus:.2f}")
                
        except Empty:
            # No frames available
            pass
        except Exception as e:
            logger.error(f"Error in display loop: {e}")
    
    cv2.destroyAllWindows()
    logger.info("Display thread stopped")

async def receive_track(track):
    """Process incoming video track frames"""
    global running
    
    logger.info(f"Receiving video track")
    consecutive_errors = 0
    max_errors = 30  # Allow up to 30 errors before giving up
    
    while running:
        try:
            # Get next frame from track with timeout
            frame = await asyncio.wait_for(track.recv(), timeout=5.0)
            
            # Convert to numpy array for OpenCV
            img_array = frame.to_ndarray(format="bgr24")
            
            # Reset error counter on success
            consecutive_errors = 0
            
            # Put frame in queue for processing thread
            if not frame_queue.full():
                frame_queue.put_nowait(img_array)
                
        except asyncio.TimeoutError:
            consecutive_errors += 1
            logger.warning(f"Frame receive timeout ({consecutive_errors}/{max_errors})")
            
            if consecutive_errors >= max_errors:
                logger.error("Too many consecutive timeouts, stopping track reception")
                break
                
            # Add a placeholder frame to show we're having issues
            error_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(
                error_frame, 
                f"Connection timeout ({consecutive_errors}/{max_errors})", 
                (40, 360),
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (0, 0, 255), 
                2
            )
            
            if not frame_queue.full():
                frame_queue.put_nowait(error_frame)
                
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error receiving frame ({consecutive_errors}/{max_errors}): {e}")
            
            if consecutive_errors >= max_errors:
                logger.error("Too many consecutive errors, stopping track reception")
                break
            
            # Add an error frame to the queue
            error_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            cv2.putText(
                error_frame, 
                f"Frame error: {str(e)[:50]}", 
                (40, 360),
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (0, 0, 255), 
                2
            )
            
            if not frame_queue.full():
                frame_queue.put_nowait(error_frame)

async def connect_to_server(server_url):
    """Create a minimal WebRTC connection to the server"""
    global pc
    
    # Create a plain RTCPeerConnection - no ICE servers for local network
    pc = RTCPeerConnection()
    
    # Handle incoming video tracks
    @pc.on("track")
    async def on_track(track):
        if track.kind == "video":
            logger.info("Video track received")
            asyncio.create_task(receive_track(track))
    
    # Monitor connection state
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state changed to: {pc.connectionState}")
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            global running
            running = False
    
    # Add video transceiver to request video
    try:
        pc.addTransceiver("video", direction="recvonly")
    except TypeError as e:
        # Fall back to a simpler method if the API changed
        logger.warning(f"Transceiver error: {e}, trying with createOffer")
    
    # Create and set local description
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    
    # Send the offer to the server via HTTP
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server_url}/offer",
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
                    logger.info("Connected successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Server error: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return False

async def run_client(server_url):
    """Main client coroutine"""
    connected = await connect_to_server(server_url)
    
    if not connected:
        logger.error("Failed to connect to server")
        return
    
    logger.info(f"Connected to {server_url}")
    
    # Keep the connection alive
    while running:
        await asyncio.sleep(1)
    
    # Cleanup
    if pc:
        await pc.close()
        logger.info("WebRTC connection closed")

# Add this function to your client
async def set_camera_focus(server_url, mode="auto", position=0.5):
    """
    Control the camera focus
    
    Args:
        server_url: Base URL for the server (e.g., "http://192.168.1.100:8080")
        mode: "auto" for automatic focus, "manual" for manual focus
        position: Focus position from 0.0 to 1.0 (0 = close focus, 1 = infinity)
    
    Returns:
        success: True if focus was set successfully
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server_url}/focus",
                json={"mode": mode, "position": position}
            ) as response:
                if response.status == 200:
                    response_text = await response.text()
                    logger.info(f"Focus adjustment: {response_text}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Server error setting focus: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logger.error(f"Error setting camera focus: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Simple WebRTC Client")
    parser.add_argument("--server", type=str, default="http://localhost:8080",
                        help="WebRTC signaling server URL")
    
    args = parser.parse_args()
    
    # Start display thread
    display_thread = Thread(target=process_and_display_frames, daemon=True)
    display_thread.start()
    
    try:
        # Run the asyncio event loop
        asyncio.run(run_client(args.server))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Signal threads to stop
        global running
        running = False
        
        # Wait for display thread to finish
        display_thread.join(timeout=2.0)
        
        logger.info("Client shutdown complete")

if __name__ == "__main__":
    main()
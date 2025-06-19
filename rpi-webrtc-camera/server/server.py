import asyncio
import json
import logging
import os
import socket
import time
import fractions
import numpy as np
from aiohttp import web
from av import VideoFrame
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from picamera2 import Picamera2
from libcamera import controls, Transform
from aiortc.mediastreams import MediaStreamError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webrtc_server")

# Global variables
camera_obj = None
pcs = set()
relay = MediaRelay()

active_tracks = set()
track_lock = asyncio.Lock()

def get_ip_address():
    """Get the server's local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def init_picamera():
    """Initialize the Raspberry Pi camera with optimized settings for Camera Module 3"""
    global camera_obj
    
    try:
        logger.info("Initializing Camera Module 3 with libcamera...")
        camera_obj = Picamera2()
        
        # Get camera info
        camera_info = camera_obj.camera_properties
        logger.info(f"Camera Model: {camera_info.get('Model', 'Unknown')}")
        
        # Allow camera to warm up and stabilize
        time.sleep(1)
        
        # Use more conservative settings for better stability
        # - Lower resolution (1024x576 instead of 1280x720)
        # - Lower framerate (15 fps instead of 20)
        # - Use YUV420 format which may be more efficient
        config = camera_obj.create_video_configuration(
            main={"size": (320, 240), "format": "YUV420"},        ## Modified Resolution
            lores={"size": (320, 240)},  # Add a lower resolution stream for processing
            controls={
                "FrameRate": 30,
                "AwbEnable": True,  # Enable auto white balance
                "NoiseReductionMode": controls.draft.NoiseReductionModeEnum.Fast,  # Faster noise reduction
                "FrameDurationLimits": (33333, 33333)  # Force exactly 30fps (1/30 = 33333μs)
            },
            transform=Transform(hflip=0, vflip=0)
        )
        
        # Apply configuration
        camera_obj.configure(config)
        
        # Set more specific controls for the Camera Module 3
        camera_obj.set_controls({
            "AfMode": controls.AfModeEnum.Continuous,  # Use continuous autofocus
            "AnalogueGain": 1.0,  # Start with normal gain
            "ExposureTime": 20000,  # 20ms exposure time (reasonable default)
            "ColourGains": (1.0, 1.0)  # Neutral color balance (red, blue)
        })
        
        # Start the camera with a longer timeout
        camera_obj.start()
        
        # Allow camera to initialize fully
        time.sleep(2)
        
        logger.info(f"Camera initialized and started (320x240 @ 30fps, using libcamera)")
        return camera_obj
    except Exception as e:
        logger.error(f"Camera initialization failed: {e}")
        return None

class Picamera2Track(MediaStreamTrack):
    """Video stream track for sending camera frames"""
    kind = "video"

    def __init__(self, camera_instance, loop):
        super().__init__()
        self.camera = camera_instance
        self._loop = loop
        self._pts = 0
        self._frame_interval = 1/30  # 30fps
        self._last_frame = None
        self._consecutive_errors = 0
        self._max_errors = 5
        self._active = True
        self._track_id = f"video-{id(self)}"
        
        # Add track to active tracks set
        active_tracks.add(self)
        logger.info(f"Created track {self._track_id}, active tracks: {len(active_tracks)}")
    
    async def stop(self):
        """Stop the track and clean up resources"""
        if not self._active:
            return
            
        self._active = False
        
        # Remove from active tracks
        if self in active_tracks:
            active_tracks.remove(self)
            
        logger.info(f"Stopped track {self._track_id}, remaining tracks: {len(active_tracks)}")
        
    async def recv(self):
        """Get the next frame from the camera"""
        if not self._active:
            # Track has been stopped, raise end-of-file
            raise MediaStreamError("Track ended")
        
        try:
            # Capture a frame from the camera
            numpy_frame = await self._loop.run_in_executor(None, self.camera.capture_array, "main")
            
            if numpy_frame is None:
                raise ValueError("Captured None frame")
            
            # Save the last good frame
            self._last_frame = numpy_frame
            self._consecutive_errors = 0
                
            # Convert to VideoFrame
            frame = VideoFrame.from_ndarray(numpy_frame, format="yuv420p")  # Match the YUV420 format
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)  # Standard timebase for WebRTC
            self._pts += int(self._frame_interval * 90000)
            return frame
            
        except Exception as e:
            if not self._active:
                raise MediaStreamError("Track ended")
                
            self._consecutive_errors += 1
            logger.error(f"Error capturing frame ({self._consecutive_errors}/{self._max_errors}): {e}")
            
            # Try to recover camera if we have multiple errors
            if self._consecutive_errors >= self._max_errors:
                logger.warning("Too many consecutive errors, attempting camera recovery...")
                try:
                    # Try to reset the camera
                    self.camera.stop()
                    time.sleep(1)
                    self.camera.start()
                    time.sleep(1)
                    self._consecutive_errors = 0
                    logger.info("Camera recovery attempted")
                except Exception as recovery_error:
                    logger.error(f"Camera recovery failed: {recovery_error}")
            
            # Use last good frame if available
            if self._last_frame is not None:
                dummy_array = self._last_frame
            else:
                # Create a dummy frame on error - use correct dimensions for your resolution
                dummy_array = np.zeros((240, 320, 3), dtype=np.uint8)  # Match your 320x240 resolution
                
                # Add text about camera error if cv2 is available
                try:
                    import cv2
                    cv2.putText(dummy_array, f"Camera error: {str(e)[:30]}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    cv2.putText(dummy_array, f"Reconnecting... ({self._consecutive_errors}/{self._max_errors})", 
                            (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                except ImportError:
                    pass
            
            # Create frame from dummy array
            frame = VideoFrame.from_ndarray(dummy_array, format="yuv420p")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)
            self._pts += int(self._frame_interval * 90000)
            return frame

async def handle_offer(request):
    """Process WebRTC offer from client"""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    
    # Track for cleanup
    current_track = None
    
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        nonlocal current_track
        logger.info(f"Connection state: {pc.connectionState}")
        
        if pc.connectionState == "failed" or pc.connectionState == "closed" or pc.connectionState == "disconnected":
            # Clean up track when connection ends
            if current_track:
                await current_track.stop()
                current_track = None
                
            # Clean up peer connection
            await pc.close()
            pcs.discard(pc)
            
            # If no more connections, log stats
            if not pcs:
                logger.info(f"No active connections. Active tracks: {len(active_tracks)}")
                
                # If there are orphaned tracks, log a warning
                if active_tracks:
                    logger.warning(f"Orphaned tracks detected: {len(active_tracks)}")
    
    # Set remote description first
    await pc.setRemoteDescription(offer)
    
    # Add to tracked connections
    pcs.add(pc)
    logger.info(f"Created PeerConnection for client {request.remote}, active connections: {len(pcs)}")
    
    # Setup video track
    if not camera_obj:
        logger.error("Camera not initialized")
        return web.Response(status=500, text="Camera not initialized")
        
    loop = asyncio.get_event_loop()
    video_track = Picamera2Track(camera_instance=camera_obj, loop=loop)
    current_track = video_track
    
    # Add video track to peer connection
    pc.addTrack(video_track)
    logger.info(f"Added video track to peer connection")
    
    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp, 
            "type": pc.localDescription.type
        })
    )

async def handle_focus(request):
    """API endpoint to control camera focus"""
    global camera_obj
    
    if not camera_obj:
        return web.Response(status=500, text="Camera not initialized")
    
    try:
        params = await request.json()
        mode = params.get("mode", "auto")
        position = params.get("position", 0.5)
        
        # Validate parameters
        position = min(1.0, max(0.0, float(position)))
        
        if mode == "auto":
            # Set continuous autofocus
            camera_obj.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            logger.info(f"Set camera to auto focus mode")
            return web.Response(text="Focus mode set to auto")
        elif mode == "manual":
            # Set manual focus - position should be between 0.0 and 1.0
            camera_obj.set_controls({
                "AfMode": controls.AfModeEnum.Manual,
                "LensPosition": position
            })
            logger.info(f"Set camera to manual focus, position: {position}")
            return web.Response(text=f"Focus set to manual, position: {position}")
        else:
            return web.Response(status=400, text="Invalid focus mode. Use 'auto' or 'manual'.")
    except Exception as e:
        logger.error(f"Error setting focus: {e}")
        return web.Response(status=500, text=f"Error setting focus: {e}")

async def handle_camera_info(request):
    """Endpoint to get camera information"""
    global camera_obj
    
    if not camera_obj:
        return web.Response(status=500, text="Camera not initialized")
    
    try:
        info = {
            "status": "running",
            "properties": camera_obj.camera_properties,
            "config": str(camera_obj.camera_config),
            "controls": str(camera_obj.camera_controls),
        }
        return web.json_response(info)
    except Exception as e:
        logger.error(f"Error getting camera info: {e}")
        return web.Response(status=500, text=f"Error getting camera info: {e}")

async def on_server_shutdown(app):
    """Cleanup when server shuts down"""
    # Stop all tracks first
    track_stop_tasks = []
    for track in list(active_tracks):
        track_stop_tasks.append(track.stop())
    
    if track_stop_tasks:
        await asyncio.gather(*track_stop_tasks)
    
    # Close all peer connections
    pc_close_tasks = [pc.close() for pc in pcs]
    if pc_close_tasks:
        await asyncio.gather(*pc_close_tasks)
    
    pcs.clear()
    
    # Stop the camera
    if camera_obj:
        camera_obj.stop()
        camera_obj.close()
        logger.info("Camera stopped and closed")

async def run_server(host, port):
    """Set up and run the web server"""
    # Initialize the camera
    if not init_picamera():
        logger.error("Failed to initialize camera, exiting")
        return
    
    # Set up web server
    app = web.Application()
    app.on_shutdown.append(on_server_shutdown)
    
    # Define routes
    app.router.add_post("/offer", handle_offer)
    app.router.add_post("/focus", handle_focus)
    app.router.add_get("/camera/info", handle_camera_info)
    
    # Add simple root endpoint
    async def handle_root(request):
        return web.Response(text="WebRTC Camera Server Running")
    app.router.add_get("/", handle_root)
    
    # Start the server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    server_ip = get_ip_address()
    logger.info(f"WebRTC Signaling Server running on http://{server_ip}:{port}")
    
    # Keep the server running
    while True:
        try:
            await asyncio.sleep(3600)  # Sleep for an hour
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down.")
            break
    
    # Cleanup
    await runner.cleanup()
    logger.info("Server process finished.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="WebRTC Camera Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind server to")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    except Exception as e:
        logger.error(f"Error running server: {e}")
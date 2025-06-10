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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webrtc_server")

# Global variables
camera_obj = None
pcs = set()
relay = MediaRelay()

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
    """Initialize the Raspberry Pi camera"""
    global camera_obj
    
    try:
        logger.info("Initializing Camera for WebRTC...")
        camera_obj = Picamera2()
        
        # Use a more modest resolution for better performance
        config = camera_obj.create_video_configuration(
            main={"size": (1280, 720), "format": "RGB888"},
            controls={"FrameRate": 20.0},
            transform=Transform(hflip=0, vflip=0)
        )
        
        camera_obj.configure(config)
        
        # Start with autofocus enabled
        camera_obj.set_controls({"AfMode": controls.AfModeEnum.Continuous})
        
        camera_obj.start()
        logger.info(f"Camera initialized and started (1280x720 @ 20fps, RGB888)")
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
        self._frame_interval = 1/20  # 20fps
        
    async def recv(self):
        """Get the next frame from the camera"""
        try:
            # Capture a frame from the camera
            numpy_frame = await self._loop.run_in_executor(None, self.camera.capture_array, "main")
            
            if numpy_frame is None:
                raise ValueError("Captured None frame")
                
            # Convert to VideoFrame
            frame = VideoFrame.from_ndarray(numpy_frame, format="rgb24")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)  # Standard timebase for WebRTC
            self._pts += int(self._frame_interval * 90000)
            return frame
            
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            
            # Create a dummy frame on error
            dummy_array = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Only add text if cv2 is available
            try:
                import cv2
                cv2.putText(dummy_array, f"Camera error", (40, 360),
                          cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            except ImportError:
                # If cv2 is not available, just use the black frame
                pass
            
            frame = VideoFrame.from_ndarray(dummy_array, format="rgb24")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)
            self._pts += int(self._frame_interval * 90000)
            return frame

async def handle_offer(request):
    """Process WebRTC offer from client"""
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info(f"Created PeerConnection for client {request.remote}")
    
    # Set remote description first
    await pc.setRemoteDescription(offer)
    
    # Setup video track
    if not camera_obj:
        logger.error("Camera not initialized")
        return web.Response(status=500, text="Camera not initialized")
        
    loop = asyncio.get_event_loop()
    video_track = Picamera2Track(camera_instance=camera_obj, loop=loop)
    
    # Add video track to peer connection
    sender = pc.addTrack(relay.subscribe(video_track))
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

async def on_server_shutdown(app):
    """Cleanup when server shuts down"""
    # Close all peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    
    # Stop the camera
    if camera_obj:
        camera_obj.stop()
        camera_obj.close()

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
    
    # Remove the static file serving since we don't need it
    # app.router.add_static("/", path=os.path.join(os.path.dirname(__file__), "static"), name="static")
    
    # Add simple root endpoint for testing
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
    if camera_obj:
        camera_obj.stop()
        camera_obj.close()
    
    logger.info("Server process finished.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="WebRTC Camera Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind server to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind server to")
    args = parser.parse_args()
    
    try:
        # Need to import cv2 here for the dummy frame creation
        import cv2
        asyncio.run(run_server(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    except Exception as e:
        logger.error(f"Error running server: {e}")
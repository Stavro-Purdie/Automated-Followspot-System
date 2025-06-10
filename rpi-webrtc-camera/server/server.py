from aiohttp import web
import asyncio
import json
import logging
import uuid
import argparse
import socket
import numpy as np
from av import VideoFrame
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from picamera2 import Picamera2
from libcamera import controls, Transform
from ir_processor import process_ir_image
import fractions  # Add this import at the top of the file

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("webrtc_server")

camera_obj = None
pcs = set()
relay = MediaRelay()

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def init_picamera():
    global camera_obj
    logger.info("Initializing Camera for WebRTC...")
    camera_obj = Picamera2()
    config = camera_obj.create_video_configuration(
        main={"size": (1920, 1080), "format": "RGB888"},    ## Resolution and format
        controls={"FrameRate": 30.0},                       ## Frame rate
        transform=Transform(hflip=0, vflip=0)
    )
    camera_obj.configure(config)
    camera_obj.set_controls({"AfMode": controls.AfModeEnum.Continuous, "LensPosition": 0.0})
    camera_obj.start()
    logger.info("Camera initialized and started (1920x1080 @ 30fps, RGB888)")
    return camera_obj

class Picamera2Track(MediaStreamTrack):
    kind = "video"

    def __init__(self, camera_instance, loop):
        super().__init__()
        self.camera = camera_instance
        self._loop = loop
        self._pts = 0
        self._frame_interval = 1/30
        self._last_frame = None
        self._consecutive_errors = 0
        self._max_errors = 10
        self._recovering = False
        
    async def _attempt_recovery(self):
        """Try to recover the camera if it's not responding"""
        if self._recovering:
            return
            
        self._recovering = True
        logger.warning("Attempting to recover camera connection...")
        
        try:
            # Close and reopen camera
            if self.camera:
                self.camera.stop()
                self.camera.close()
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Reinitialize
            self.camera = Picamera2()
            config = self.camera.create_video_configuration(
                main={"size": (1280, 720), "format": "RGB888"},
                controls={"FrameDurationLimits": (33333, 33333)}  # Force 30fps
            )
            self.camera.configure(config)
            self.camera.start()
            
            logger.info("Camera recovered successfully")
            self._consecutive_errors = 0
        except Exception as e:
            logger.error(f"Camera recovery failed: {e}")
        finally:
            self._recovering = False

    async def recv(self):
        if not self.camera or self._consecutive_errors >= self._max_errors:
            # Camera is unavailable or has too many errors
            if self._consecutive_errors >= self._max_errors and not self._recovering:
                # Try to recover the camera
                asyncio.create_task(self._attempt_recovery())
            
            # Return a placeholder frame
            await asyncio.sleep(self._frame_interval)
            dummy_array = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Add text to indicate camera is offline
            cv2.putText(
                dummy_array,
                "Camera connection lost - attempting to reconnect...",
                (40, 360),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 0, 0),
                2
            )
            
            frame = VideoFrame.from_ndarray(dummy_array, format="rgb24")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)
            self._pts += int(self._frame_interval * 90000)
            return frame

        try:
            # Try to capture a frame
            numpy_frame = await self._loop.run_in_executor(None, self.camera.capture_array, "main")
            
            if numpy_frame is None:
                raise ValueError("Captured None frame")
                
            # Process for IR detection if requested
            processed = False
            try:
                # Process IR image (if module exists)
                ir_processed = process_ir_image(numpy_frame, threshold=200)
                
                # Create a combined visualization with original and IR processed side by side
                if ir_processed is not None:
                    # Make IR visualization 3-channel
                    if len(ir_processed.shape) == 2:
                        ir_color = cv2.cvtColor(ir_processed, cv2.COLOR_GRAY2RGB)
                    else:
                        ir_color = ir_processed
                        
                    # Add a colored highlight to make hot areas more visible
                    # numpy_frame = cv2.addWeighted(numpy_frame, 0.7, cv2.cvtColor(ir_processed, cv2.COLOR_GRAY2RGB), 0.3, 0)
                    processed = True
            except Exception as e:
                logger.warning(f"Error in IR processing: {e}")
                
            # Save the frame
            self._last_frame = numpy_frame
            self._consecutive_errors = 0
            
            # Convert to VideoFrame
            frame = VideoFrame.from_ndarray(numpy_frame, format="rgb24")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)
            self._pts += int(self._frame_interval * 90000)
            return frame
            
        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"Error capturing frame ({self._consecutive_errors}/{self._max_errors}): {e}")
            
            # Use last good frame if available, otherwise black frame
            if self._last_frame is not None and self._consecutive_errors < 5:
                frame_data = self._last_frame
            else:
                # Create a black frame with error text
                frame_data = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(
                    frame_data,
                    f"Camera error: {e}",
                    (40, 360),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    2
                )
            
            frame = VideoFrame.from_ndarray(frame_data, format="rgb24")
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 90000)
            self._pts += int(self._frame_interval * 90000)
            return frame

async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info(f"Created PeerConnection for client {request.remote}")
    
    # Set remote description FIRST - this is the key for proper negotiation
    await pc.setRemoteDescription(offer)
    
    # Handle tracks
    @pc.on("track")
    def on_track(track):
        logger.info(f"Track {track.kind} received")
    
    # Setup video track
    if not camera_obj:
        logger.error("Camera not initialized")
        return web.Response(status=500, text="Camera not initialized")
        
    loop = asyncio.get_event_loop()
    video_track = Picamera2Track(camera_instance=camera_obj, loop=loop)
    
    # Use standard addTrack instead of addTransceiver 
    # The transceiver direction is inferred from the remote description
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

async def on_server_shutdown(app):
    logger.info("Server shutting down...")
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros, return_exceptions=True)
    pcs.clear()
    if camera_obj:
        camera_obj.stop()
        camera_obj.close()
        logger.info("Camera stopped and closed.")

async def run_server(host, port):
    global camera_obj
    camera_obj = init_picamera()
    app = web.Application()
    app.on_shutdown.append(on_server_shutdown)
    app.router.add_post("/offer", handle_offer)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    ip_address = get_ip_address()
    logger.info(f"WebRTC Signaling Server running on http://{ip_address}:{port}")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Raspberry Pi WebRTC Camera Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host for the signaling server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port for the signaling server (default: 8080)")
    args = parser.parse_args()

    try:
        asyncio.run(run_server(host=args.host, port=args.port))
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    finally:
        logger.info("Server process finished.")
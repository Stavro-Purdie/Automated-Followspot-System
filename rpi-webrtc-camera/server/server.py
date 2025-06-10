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
        self.frame_interval = 1/30
        # Make sure to set track settings!
        self._width = 1920
        self._height = 1080

    async def recv(self):
        if not self.camera:
            logger.warning("Picamera2Track: Camera not available.")
            await asyncio.sleep(self.frame_interval)
            dummy_array = np.zeros((1080, 1920, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(dummy_array, format="rgb24")
            frame.pts = self._pts
            frame.time_base = VideoFrame.guess_time_base()
            self._pts += int(self.frame_interval * 90000)
            return frame

        try:
            numpy_frame = await self._loop.run_in_executor(None, self.camera.capture_array, "main")
            if numpy_frame is None:
                logger.warning("Captured None frame.")
                dummy_array = np.zeros((1080, 1920, 3), dtype=np.uint8)
                frame = VideoFrame.from_ndarray(dummy_array, format="rgb24")
            else:
                frame = VideoFrame.from_ndarray(numpy_frame, format="rgb24")
            
            frame.pts = self._pts
            frame.time_base = VideoFrame.guess_time_base()
            self._pts += int(self.frame_interval * 90000)
            return frame

        except Exception as e:
            logger.error(f"Error capturing frame from Camera: {e}")
            dummy_array = np.zeros((1080, 1920, 3), dtype=np.uint8)
            frame = VideoFrame.from_ndarray(dummy_array, format="rgb24")
            frame.pts = self._pts
            frame.time_base = VideoFrame.guess_time_base()
            self._pts += int(self.frame_interval * 90000)
            return frame

async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    logger.info(f"Created PeerConnection for client {request.remote}")

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            logger.debug(f"ICE candidate: {candidate.candidate[:30]}...")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState in ["failed", "closed", "disconnected"]:
            await pc.close()
            pcs.discard(pc)
            logger.info("PeerConnection closed and removed.")

    # Set remote description first, before adding tracks
    try:
        await pc.setRemoteDescription(offer)
    except Exception as e:
        logger.error(f"Error setting remote description: {e}")
        return web.Response(status=500, text=str(e))

    # Add camera track
    try:
        if not camera_obj:
            logger.error("Camera not initialized")
            return web.Response(status=500, text="Camera not initialized")
            
        loop = asyncio.get_event_loop()
        video_track = Picamera2Track(camera_instance=camera_obj, loop=loop)
        pc.addTrack(relay.subscribe(video_track))
        logger.info("Added video track to peer connection")
    except Exception as e:
        logger.error(f"Error adding video track: {e}")
        return web.Response(status=500, text=str(e))

    # Create answer
    try:
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception as e:
        logger.error(f"Error creating/setting answer: {e}")
        return web.Response(status=500, text=str(e))

    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
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
import asyncio
import copy
import json
import logging
import os
import socket
import termios
import time
import fractions
from typing import Any, Dict

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

# Camera profile definitions
DEFAULT_PROFILE = "roof_array"
PROFILE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "roof_array": {
        "main_size": (320, 240),
        "format": "YUV420",
        "frame_rate": 30,
        "capture_stream": "main",
        "video_frame_format": "yuv420p",
        "lores_size": (320, 240),
        "transform": {"hflip": 0, "vflip": 0},
        "camera_controls": {
            "FrameRate": 30,
            "AwbEnable": True,
            "FrameDurationLimits": (33333, 33333),
            "NoiseReductionMode": controls.draft.NoiseReductionModeEnum.Fast,
        },
        "set_controls": {
            "AfMode": controls.AfModeEnum.Continuous,
            "AnalogueGain": 1.0,
            "ExposureTime": 20000,
            "ColourGains": (1.0, 1.0),
        },
        "startup_delay": 2.0,
    },
    "front_truss": {
        "main_size": (1920, 1080),
        "format": "RGB888",
        "frame_rate": 30,
        "capture_stream": "main",
        "video_frame_format": "rgb24",
        "lores_size": None,
        "transform": {"hflip": 0, "vflip": 0},
        "camera_controls": {
            "FrameRate": 30,
            "AwbEnable": True,
            "AeEnable": True,
            "FrameDurationLimits": (33333, 33333),
        },
        "set_controls": {
            "AfMode": controls.AfModeEnum.Manual,
            "AnalogueGain": 1.5,
            "ExposureTime": 16666,
            "ColourGains": (1.2, 1.0),
        },
        "startup_delay": 2.5,
    },
}

active_profile_name = DEFAULT_PROFILE
active_profile_settings: Dict[str, Any] = copy.deepcopy(PROFILE_CONFIGS[DEFAULT_PROFILE])

# Global variables
camera_obj = None
pcs = set()
relay = MediaRelay()

active_tracks = set()
track_lock = asyncio.Lock()


class DMXController:
    """Lighting command bridge for the RS485 HAT."""

    def __init__(self, *, serial_port: str = "/dev/ttyAMA0", baudrate: int = 115200) -> None:
        self.initialized = False
        self.serial_port = serial_port
        self.baudrate = int(baudrate)
        self._serial_handle = None
        self.last_command: Dict[str, Any] | None = None
        self.last_frame: Dict[str, Any] | None = None

    def _baud_constant(self) -> int:
        return getattr(termios, f"B{self.baudrate}", termios.B115200)

    def _open_serial(self):
        if self._serial_handle is not None:
            return self._serial_handle

        if not self.serial_port:
            raise RuntimeError("No serial port configured for RS485 transport")

        handle = open(self.serial_port, "wb", buffering=0)
        fd = handle.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
        attrs[3] = 0
        attrs[4] = self._baud_constant()
        attrs[5] = self._baud_constant()
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._serial_handle = handle
        logger.info("RS485 lighting transport opened on %s @ %s baud", self.serial_port, self.baudrate)
        return handle

    def _normalize_frame(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        command = payload.get("command") if isinstance(payload.get("command"), dict) else payload
        command = command or {}
        frame = {
            "protocol": str(payload.get("protocol", "followspot-lighting")),
            "version": int(payload.get("version", 1)),
            "transport": str(payload.get("transport", "rs485_serial")),
            "timestamp": float(payload.get("timestamp", time.time())),
            "command": {
                "pan_deg": float(command.get("pan_deg", 0.0)),
                "tilt_deg": float(command.get("tilt_deg", 0.0)),
                "brightness_pct": float(command.get("brightness_pct", 100.0)),
                "source": str(command.get("source", payload.get("source", "control"))),
                "target_id": command.get("target_id"),
            },
        }
        return frame

    def _serialize_frame(self, frame: Dict[str, Any]) -> bytes:
        encoded = json.dumps(frame, separators=(",", ":"), sort_keys=True)
        return f"{encoded}\n".encode("utf-8")

    def send_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        frame = self._normalize_frame(payload)
        command = frame["command"]
        transport_mode = str(frame.get("transport", "rs485_serial"))
        self.last_command = command
        self.last_frame = frame

        if transport_mode == "stub":
            logger.info("Stub lighting frame accepted: %s", frame)
            return {"ok": True, "transport": transport_mode, "frame": frame, "written": False}

        try:
            handle = self._open_serial()
            handle.write(self._serialize_frame(frame))
            handle.flush()
            self.initialized = True
            logger.info(
                "Lighting frame sent to RS485 transport: pan=%.2f tilt=%.2f brightness=%.1f",
                command["pan_deg"],
                command["tilt_deg"],
                command["brightness_pct"],
            )
            return {"ok": True, "transport": transport_mode, "frame": frame, "written": True}
        except Exception as exc:
            logger.error("Failed to send lighting command over RS485: %s", exc)
            return {"ok": False, "transport": transport_mode, "frame": frame, "error": str(exc)}

    async def handle_update(self, request: web.Request) -> web.Response:
        """Bridge an incoming lighting command to the RS485 transport."""
        try:
            if request.content_type == "application/json":
                payload = await request.json()
            else:
                form_data = await request.post()
                payload = dict(form_data)

            result = self.send_command(payload)
            status = 200 if result.get("ok") else 502
            return web.json_response(result, status=status)
        except Exception as exc:
            logger.error("Lighting update handler failed: %s", exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

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

def init_picamera(profile_name: str) -> Picamera2 | None:
    """Initialize the Raspberry Pi camera for the requested profile."""
    global camera_obj, active_profile_name, active_profile_settings

    try:
        profile = PROFILE_CONFIGS.get(profile_name)
        if profile is None:
            logger.warning(f"Unknown profile '{profile_name}', falling back to '{DEFAULT_PROFILE}'")
            profile_name = DEFAULT_PROFILE
            profile = PROFILE_CONFIGS[DEFAULT_PROFILE]

        settings = copy.deepcopy(profile)

        logger.info(f"Initializing camera for profile '%s'", profile_name)
        camera_obj = Picamera2()

        camera_info = camera_obj.camera_properties
        logger.info("Detected camera: %s", camera_info.get("Model", "Unknown"))

        config_kwargs: Dict[str, Any] = {
            "main": {"size": settings["main_size"], "format": settings["format"]},
            "controls": settings["camera_controls"],
            "transform": Transform(**settings.get("transform", {"hflip": 0, "vflip": 0})),
        }

        lores_size = settings.get("lores_size")
        if lores_size:
            config_kwargs["lores"] = {"size": lores_size}

        config = camera_obj.create_video_configuration(**config_kwargs)
        camera_obj.configure(config)

        extra_controls = settings.get("set_controls", {})
        if extra_controls:
            try:
                camera_obj.set_controls(extra_controls)
            except Exception as err:
                logger.warning("Unable to apply camera controls: %s", err)

        camera_obj.start()

        startup_delay = float(settings.get("startup_delay", 2.0))
        if startup_delay > 0:
            time.sleep(startup_delay)

        settings["frame_interval"] = 1.0 / float(settings["frame_rate"])
        settings["width"], settings["height"] = settings["main_size"]

        active_profile_name = profile_name
        active_profile_settings = settings

        logger.info(
            "Camera started: %dx%d @ %sfps (%s)",
            settings["width"],
            settings["height"],
            settings["frame_rate"],
            profile_name,
        )
        return camera_obj
    except Exception as e:
        logger.error(f"Camera initialization failed: {e}")
        return None

class Picamera2Track(MediaStreamTrack):
    """Video stream track for sending camera frames"""
    kind = "video"

    def __init__(self, camera_instance, loop: asyncio.AbstractEventLoop, settings: Dict[str, Any]):
        super().__init__()
        self.camera = camera_instance
        self._loop = loop
        self._settings = settings
        self._pts = 0
        self._frame_interval = float(settings.get("frame_interval", 1.0 / max(settings.get("frame_rate", 30), 1)))
        self._capture_stream = settings.get("capture_stream", "main")
        self._video_frame_format = settings.get("video_frame_format", "yuv420p")
        self._frame_width = int(settings.get("width", settings.get("main_size", (320, 240))[0]))
        self._frame_height = int(settings.get("height", settings.get("main_size", (320, 240))[1]))
        self._last_frame = None
        self._consecutive_errors = 0
        self._max_errors = 5
        self._active = True
        self._track_id = f"video-{id(self)}"

        active_tracks.add(self)
        logger.info(f"Created track {self._track_id}, active tracks: {len(active_tracks)}")

    def stop(self) -> None:
        """Stop the track and clean up resources."""
        if not self._active:
            return

        self._active = False

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
            numpy_frame = await self._loop.run_in_executor(None, self.camera.capture_array, self._capture_stream)
            
            if numpy_frame is None:
                raise ValueError("Captured None frame")
            
            # Save the last good frame
            self._last_frame = numpy_frame
            self._consecutive_errors = 0
                
            # Convert to VideoFrame
            frame = VideoFrame.from_ndarray(numpy_frame, format=self._video_frame_format)
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
                dummy_array = np.zeros((self._frame_height, self._frame_width, 3), dtype=np.uint8)
                
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
            frame = VideoFrame.from_ndarray(dummy_array, format=self._video_frame_format)
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
                current_track.stop()
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
    video_track = Picamera2Track(camera_instance=camera_obj, loop=loop, settings=active_profile_settings)
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
            "profile": active_profile_name,
            "output": {
                "resolution": [
                    active_profile_settings.get("width"),
                    active_profile_settings.get("height"),
                ],
                "frame_rate": active_profile_settings.get("frame_rate"),
                "video_format": active_profile_settings.get("video_frame_format"),
            },
        }
        return web.json_response(info)
    except Exception as e:
        logger.error(f"Error getting camera info: {e}")
        return web.Response(status=500, text=f"Error getting camera info: {e}")

async def handle_lighting_status(request):
    """Return the latest lighting transport state."""
    controller: DMXController = request.app["dmx_controller"]
    return web.json_response(
        {
            "transport": "rs485_serial" if controller.initialized else "stub",
            "serial_port": controller.serial_port,
            "baudrate": controller.baudrate,
            "last_command": controller.last_command,
            "last_frame": controller.last_frame,
            "initialized": controller.initialized,
        }
    )

async def on_server_shutdown(app):
    """Cleanup when server shuts down"""
    # Stop all tracks first
    for track in list(active_tracks):
        track.stop()
    
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

async def run_server(host: str, port: int, profile: str, *, dmx_port: str = "/dev/ttyAMA0", dmx_baudrate: int = 115200):
    """Set up and run the web server"""
    # Initialize the camera
    if not init_picamera(profile):
        logger.error("Failed to initialize camera, exiting")
        return
    
    # Set up web server
    app = web.Application()
    app.on_shutdown.append(on_server_shutdown)
    dmx_controller = DMXController(serial_port=dmx_port, baudrate=dmx_baudrate)
    app["dmx_controller"] = dmx_controller
    
    # Define routes
    app.router.add_post("/offer", handle_offer)
    app.router.add_post("/focus", handle_focus)
    app.router.add_get("/camera/info", handle_camera_info)
    app.router.add_post("/dmx", dmx_controller.handle_update)
    app.router.add_get("/dmx/status", handle_lighting_status)
    logger.info("DMX endpoint registered")
    
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
    logger.info(
        "WebRTC Signaling Server running on http://%s:%s (profile=%s)",
        server_ip,
        port,
        active_profile_name,
    )
    
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
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=sorted(PROFILE_CONFIGS.keys()),
        help="Camera profile to use",
    )
    parser.add_argument("--dmx-port", default="/dev/ttyAMA0", help="RS485 serial port for lighting output")
    parser.add_argument("--dmx-baudrate", type=int, default=115200, help="Serial baudrate for lighting output")
    args = parser.parse_args()
    
    try:
        asyncio.run(
            run_server(
                args.host,
                args.port,
                args.profile,
                dmx_port=args.dmx_port,
                dmx_baudrate=args.dmx_baudrate,
            )
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    except Exception as e:
        logger.error(f"Error running server: {e}")
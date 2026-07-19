import asyncio
import copy
import json
import logging
import os
import socket
import termios
import time
import fractions
from pathlib import Path
from typing import Any, Dict

import numpy as np
from aiohttp import web
from av import VideoFrame
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay
from picamera2 import Picamera2
from libcamera import controls, Transform
from aiortc.mediastreams import MediaStreamError

# Local DMX transport
from dmx_transport import create_transport, DMXEncoder, DMXFrame

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


# DMX transport is now handled by dmx_transport module
# DMXController class removed - use create_transport() from dmx_transport


def load_fixture_profile(profile_name: str = None) -> Dict[str, Any]:
    """Load fixture profile from config/fixture_profiles.json."""
    config_path = Path(__file__).parent.parent / "config" / "fixture_profiles.json"
    if not config_path.exists():
        logger.warning("Fixture profile config not found at %s, using defaults", config_path)
        return {
            "pan_coarse": 1,
            "pan_fine": 2,
            "tilt_coarse": 3,
            "tilt_fine": 4,
            "dimmer": 5,
            "pan_scale": 1.0,
            "tilt_scale": 1.0,
            "pan_min_deg": -180.0,
            "pan_max_deg": 180.0,
            "tilt_min_deg": -90.0,
            "tilt_max_deg": 90.0,
            "universe": 1,
        }
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
        default = data.get("default_profile", "generic_moving_head")
        profile_name = profile_name or default
        profile = data["fixture_profiles"].get(profile_name)
        if not profile:
            logger.warning("Profile '%s' not found, using default", profile_name)
            profile = data["fixture_profiles"][default]
        logger.info("Loaded fixture profile: %s", profile.get("name", profile_name))
        return profile
    except Exception as e:
        logger.error("Failed to load fixture profile: %s", e)
        return {}

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
    transport = request.app["dmx_transport"]
    encoder = request.app["dmx_encoder"]
    config = request.app["dmx_config"]
    return web.json_response(
        {
            "transport": config.get("transport", "unknown"),
            "serial_port": config.get("serial_port", ""),
            "universe": config.get("universe", 1),
            "initialized": transport.is_ready,
            "fixture_profile": encoder.profile,
        }
    )


async def handle_dmx_update(request: web.Request) -> web.Response:
    """Bridge an incoming lighting command to the DMX transport."""
    try:
        if request.content_type == "application/json":
            payload = await request.json()
        else:
            form_data = await request.post()
            payload = dict(form_data)

        # Extract command from payload
        command = payload.get("command") if isinstance(payload.get("command"), dict) else payload
        command = command or {}

        pan_deg = float(command.get("pan_deg", 0.0))
        tilt_deg = float(command.get("tilt_deg", 0.0))
        brightness_pct = float(command.get("brightness_pct", 100.0))

        # Encode to DMX frame
        encoder = request.app["dmx_encoder"]
        frame = encoder.encode(pan_deg, tilt_deg, brightness_pct)

        # Send via transport
        transport = request.app["dmx_transport"]
        success = transport.send(frame)

        result = {
            "ok": success,
            "transport": request.app["dmx_config"].get("transport", "unknown"),
            "pan_deg": pan_deg,
            "tilt_deg": tilt_deg,
            "brightness_pct": brightness_pct,
            "dmx_channels": {
                "pan_coarse": frame.data[encoder.pan_coarse],
                "pan_fine": frame.data[encoder.pan_fine],
                "tilt_coarse": frame.data[encoder.tilt_coarse],
                "tilt_fine": frame.data[encoder.tilt_fine],
                "dimmer": frame.data[encoder.dimmer],
            },
        }
        status = 200 if success else 502
        return web.json_response(result, status=status)
    except Exception as exc:
        logger.error("DMX update handler failed: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def handle_health(request):
    """Health check endpoint for monitoring and systemd watchdog.

    Returns JSON with service status, camera status, DMX transport status, and uptime.
    """
    import time
    import psutil
    
    # Check camera status
    camera_status = "unknown"
    if camera_obj:
        try:
            # Try to capture a test frame
            test_frame = camera_obj.capture_array("main")
            if test_frame is not None and test_frame.size > 0:
                camera_status = "ok"
            else:
                camera_status = "no_frame"
        except Exception:
            camera_status = "error"
    else:
        camera_status = "not_initialized"
    
    # Check DMX transport
    dmx_transport_obj = request.app.get("dmx_transport")
    dmx_status = "ok" if dmx_transport_obj and dmx_transport_obj.is_ready else "unavailable"
    
    # Get uptime
    uptime_seconds = time.time() - _start_time if '_start_time' in globals() else 0
    
    # Get system stats
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        system_stats = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available // (1024 * 1024),
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free // (1024 * 1024 * 1024),
        }
    except Exception:
        system_stats = {}
    
    return web.json_response({
        "status": "healthy" if camera_status == "ok" else "degraded",
        "timestamp": time.time(),
        "uptime_seconds": uptime_seconds,
        "camera": camera_status,
        "dmx_transport": dmx_status,
        "system": system_stats,
    })


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

async def run_server(
    host: str, 
    port: int, 
    profile: str, 
    *, 
    dmx_port: str = "/dev/ttyAMA0", 
    dmx_baudrate: int = 115200,
    dmx_transport: str = "rs485_serial",
    dmx_universe: int = 1,
    artnet_ip: str = "2.0.0.1",
    fixture_profile_path: str = ""
):
    """Set up and run the web server."""
    # Initialize camera
    if not init_picamera(profile):
        logger.error("Failed to initialize camera, exiting")
        return

    # Load fixture profile if provided
    fixture_profile = {}
    if fixture_profile_path:
        try:
            with open(fixture_profile_path, 'r') as f:
                fixture_profile = json.load(f)
            logger.info("Loaded fixture profile from %s", fixture_profile_path)
        except Exception as e:
            logger.warning("Failed to load fixture profile: %s", e)

    # Create DMX transport from config
    transport_config = {
        "transport": dmx_transport,
        "serial_port": dmx_port,
        "universe": dmx_universe,
        "artnet_ip": artnet_ip,
        "fixture_profile": fixture_profile,
    }
    
    from dmx_transport import create_transport, DMXEncoder
    dmx_transport_obj = create_transport(transport_config)
    dmx_encoder = DMXEncoder(fixture_profile or RS485Transport._default_profile())

    # Set up web server
    app = web.Application()
    app.on_shutdown.append(on_server_shutdown)
    app["dmx_transport"] = dmx_transport_obj
    app["dmx_encoder"] = dmx_encoder
    app["dmx_config"] = transport_config
    
    # Define routes
    app.router.add_post("/offer", handle_offer)
    app.router.add_post("/focus", handle_focus)
    app.router.add_get("/camera/info", handle_camera_info)
    app.router.add_post("/dmx", handle_dmx_update)
    app.router.add_get("/dmx/status", handle_lighting_status)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_root)
    logger.info("DMX endpoint registered (transport=%s)", dmx_transport)
    
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
    parser.add_argument(
        "--dmx-transport",
        default="rs485_serial",
        choices=["stub", "rs485_serial", "artnet", "sacn"],
        help="DMX transport backend",
    )
    parser.add_argument("--dmx-universe", type=int, default=1, help="DMX universe number")
    parser.add_argument("--artnet-ip", default="2.0.0.1", help="Art-Net target IP address")
    parser.add_argument("--fixture-profile", default="", help="Path to fixture profile JSON (optional)")
    args = parser.parse_args()

    try:
        asyncio.run(
            run_server(
                args.host,
                args.port,
                args.profile,
                dmx_port=args.dmx_port,
                dmx_baudrate=args.dmx_baudrate,
                dmx_transport=args.dmx_transport,
                dmx_universe=args.dmx_universe,
                artnet_ip=args.artnet_ip,
                fixture_profile_path=args.fixture_profile,
            )
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down.")
    except Exception as e:
        logger.error(f"Error running server: {e}")
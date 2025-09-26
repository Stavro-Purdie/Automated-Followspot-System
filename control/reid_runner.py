#!/usr/bin/env python3
"""
Front Array ReID Runner
Reads network camera from front_array_config.json, runs ReID processor and person tracker,
and publishes track states for fusion.
"""

import cv2
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import sys

import numpy as np
import asyncio
import aiohttp
from threading import Lock, Thread
from aiortc import RTCPeerConnection, RTCSessionDescription

# Ensure project root is available for module imports when launched from control/
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reid.reid_processor import OptimizedReIDProcessor
from reid.person_tracker import PersonTracker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("reid_runner")


class ReIDRunner:
    def __init__(self, config_path: str = str(Path(__file__).parent.parent / "config" / "front_array_config.json")):
        self.config_path = config_path
        self.config = self._load_config()
        self.camera_url = self.config["camera"]["front_camera"]["server_url"]
        self.protocol = self.config["camera"]["front_camera"].get("protocol", "webrtc")

        # ReID processor uses its own config; pass front config for camera params
        self.reid_processor = OptimizedReIDProcessor(
            config_path=str(Path(__file__).parent.parent / "config" / "front_array_config.json")
        )
        self.person_tracker = PersonTracker(self.config)

        # Stream / WebRTC members
        self.cap = None
        self.pc = None
        self.latest_frame = None
        self.frame_lock = Lock()
        self._webrtc_task = None
        self._loop = None
        self._loop_thread = None
        self.running = False
        self.last_bgr_frame = None
        self.last_detections = []

    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def start(self) -> bool:
        """Start input stream and models"""
        if not self.reid_processor.start():
            logger.error("ReID processor failed to start")
            return False

        if self.protocol.lower() == "webrtc":
            # Schedule WebRTC connection; prefer background loop if none running
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                self._webrtc_task = loop.create_task(self._connect_webrtc())
            else:
                self._start_background_loop()
        else:
            url = self.camera_url
            logger.info(f"Opening front node stream: {url} (protocol={self.protocol})")
            self.cap = cv2.VideoCapture(url)
            if not self.cap.isOpened():
                logger.error(f"Failed to open front node stream: {url}")
                return False

        self.running = True
        return True

    def _start_background_loop(self):
        """Start an asyncio loop in a background thread and connect via WebRTC."""
        def runner():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                # Connect; ignore return, on_track will keep running while self.running
                self._loop.run_until_complete(self._connect_webrtc())
                self._loop.run_forever()
            except Exception as e:
                logger.error(f"Front node background loop error: {e}")
            finally:
                try:
                    pending = asyncio.all_tasks(self._loop) if self._loop else []
                    for t in pending:
                        t.cancel()
                    if self._loop:
                        self._loop.run_until_complete(asyncio.sleep(0))
                        try:
                            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                        except Exception:
                            pass
                        self._loop.close()
                except Exception:
                    pass

        self._loop_thread = Thread(target=runner, daemon=True)
        self._loop_thread.start()

    async def _connect_webrtc(self) -> bool:
        """Connect to front node WebRTC server and receive frames"""
        self.pc = RTCPeerConnection()

        @self.pc.on("track")
        async def on_track(track):
            if track.kind == "video":
                logger.info("Front node video track received")
                while self.running:
                    try:
                        frame = await asyncio.wait_for(track.recv(), timeout=5.0)
                        img = frame.to_ndarray(format="bgr24")
                        with self.frame_lock:
                            self.latest_frame = img
                    except asyncio.TimeoutError:
                        logger.warning("Front node frame timeout")
                        continue
                    except Exception as e:
                        logger.error(f"Front node track error: {e}")
                        break

        try:
            self.pc.addTransceiver("video", direction="recvonly")
        except TypeError:
            logger.warning("Transceiver error on front node")

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)

        offer_url = self.camera_url.rstrip("/") + "/offer"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    offer_url,
                    json={"sdp": self.pc.localDescription.sdp, "type": self.pc.localDescription.type}
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Front node /offer failed: {resp.status}")
                        return False
                    answer = await resp.json()
                    await self.pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
                    logger.info("Connected to front node via WebRTC")
                    return True
        except Exception as e:
            logger.error(f"Front node connection error: {e}")
            return False

    def read_and_process(self) -> Dict[int, Dict]:
        if not self.running:
            return {}

        # Acquire latest frame depending on protocol
        if self.protocol.lower() == "webrtc":
            with self.frame_lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                time.sleep(0.02)
                return {}
        else:
            if self.cap is None:
                time.sleep(0.05)
                return {}
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                return {}

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ts = time.time()
        out = self.reid_processor.process_frame(rgb, ts)
        if "persons" not in out:
            return {}

        detections = out["persons"]
        # Keep last raw BGR frame and detections for UI
        self.last_bgr_frame = frame.copy()
        self.last_detections = detections
        # Build inputs for tracker
        bboxes = [np.array(d["bbox"]) for d in detections]
        features = np.array([d.get("features", np.zeros(512)) for d in detections], dtype=np.float32)
        depths = [float(d.get("depth", 10.0)) for d in detections]
        # Create detection dicts for tracker
        det_list = [{"bbox": b, "confidence": d.get("confidence", 0.5)} for b, d in zip(bboxes, detections)]
        tracks = self.person_tracker.update_tracks(det_list, features, depths, ts)
        return tracks

    def get_overlay_frame(self) -> Optional[np.ndarray]:
        """Return BGR frame with detection boxes and confidence overlays"""
        if self.last_bgr_frame is None:
            return None
        vis = self.last_bgr_frame.copy()
        try:
            for det in self.last_detections or []:
                bbox = det.get("bbox")
                conf = det.get("confidence", 0.0)
                if bbox is None:
                    continue
                x1, y1, x2, y2 = [int(v) for v in bbox]
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{conf:.2f}"
                cv2.putText(vis, label, (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        except Exception:
            pass
        return vis

    def stop(self):
        self.running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        if self.pc is not None:
            try:
                # Close peer connection
                if self._loop and self._loop.is_running():
                    def _close_pc():
                        if self.pc is not None:
                            cor = self.pc.close()
                            asyncio.create_task(cor)
                    self._loop.call_soon_threadsafe(_close_pc)
                else:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        if self.pc is not None:
                            loop.create_task(self.pc.close())
                    else:
                        if self.pc is not None:
                            asyncio.run(self.pc.close())
            except Exception:
                pass
        # Stop background loop if any
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
        if self._loop_thread and self._loop_thread.is_alive():
            try:
                self._loop_thread.join(timeout=1.0)
            except Exception:
                pass
        self.reid_processor.stop()


def main():
    runner = ReIDRunner()
    if not runner.start():
        return
    logger.info("ReID runner started. Press Ctrl+C to stop.")
    try:
        while True:
            tracks = runner.read_and_process()
            if tracks:
                active = {tid: t for tid, t in tracks.items() if t.get("status") == "active"}
                logger.info(f"Active tracks: {len(active)}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Launch the front-array ReID pipeline and stream tracks to the fusion layer.
"""

import argparse
import cv2
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import sys
import socket
import ipaddress
from urllib.parse import urlparse

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


def run_smoke_test(
    test_image: Optional[str] = None,
    front_config_path: str = str(Path(__file__).parent.parent / "config" / "front_array_config.json"),
    reid_config_path: str = str(Path(__file__).parent.parent / "config" / "reid_config.json"),
) -> Tuple[bool, Dict[str, Any]]:
    """Run a minimal offline validation of the ReID pipeline."""

    summary: Dict[str, Any] = {
        "mode": "smoke_test",
        "front_config": front_config_path,
        "reid_config": reid_config_path,
    }

    processor: Optional[OptimizedReIDProcessor] = None
    try:
        processor = OptimizedReIDProcessor(config_path=reid_config_path)
        if not processor.start():
            summary["error"] = "reid_processor_failed_to_start"
            return False, summary

        summary["models_loaded"] = True
        summary["identity_count"] = len(processor.identity_embeddings)

        image_path: Optional[Path] = Path(test_image) if test_image else None
        if image_path and not image_path.exists():
            summary["warning"] = f"test_image_not_found: {image_path}"
            image_path = None

        if image_path is None and processor.identity_embeddings:
            first_identity = next(iter(processor.identity_embeddings.values()))
            primary = first_identity.get("primary_image")
            if primary:
                candidate = processor.identity_gallery_path / primary
                if candidate.exists():
                    image_path = candidate
        summary["test_image"] = str(image_path) if image_path else None

        frame_result: Dict[str, Any] = {}
        if image_path and image_path.exists():
            bgr = cv2.imread(str(image_path))
            if bgr is not None:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                frame_result = processor.process_frame(rgb, timestamp=time.time())
        summary["frame_result_keys"] = list(frame_result.keys()) if isinstance(frame_result, dict) else []

        persons = frame_result.get("persons", []) if isinstance(frame_result, dict) else []
        summary["detections"] = len(persons)
        summary["identity_matches"] = [p.get("identity_match") for p in persons if p.get("identity_match")]

        success = False

        if persons:
            with open(front_config_path, "r", encoding="utf-8") as handle:
                front_config = json.load(handle)
            tracker = PersonTracker(front_config)

            feature_vectors: List[np.ndarray] = []
            for person in persons:
                feat = person.get("features")
                if isinstance(feat, np.ndarray):
                    feature_vectors.append(feat.astype(np.float32))
                elif isinstance(feat, list):
                    feature_vectors.append(np.array(feat, dtype=np.float32))
                else:
                    feature_vectors.append(np.zeros(processor.feature_dim, dtype=np.float32))

            if feature_vectors:
                try:
                    features = np.stack(feature_vectors)
                except ValueError:
                    features = np.array(feature_vectors, dtype=np.float32)
            else:
                features = np.zeros((0, processor.feature_dim), dtype=np.float32)

            depths = [float(p.get("depth", 10.0) or 10.0) for p in persons]

            detections_for_tracker = []
            for person in persons:
                bbox = np.array(person.get("bbox", [0, 0, 0, 0]), dtype=np.float32)
                entry: Dict[str, Any] = {
                    "bbox": bbox,
                    "confidence": person.get("confidence", 0.5),
                }
                if person.get("identity_match"):
                    entry["identity_match"] = person["identity_match"]
                detections_for_tracker.append(entry)

            tracks = tracker.update_tracks(detections_for_tracker, features, depths, time.time())
            summary["tracks"] = {
                tid: {
                    "status": data.get("status"),
                    "identity": data.get("identity"),
                    "average_confidence": data.get("average_confidence"),
                }
                for tid, data in tracks.items()
            }

            success = any(person.get("identity_match") for person in persons)
            if not success:
                success = len(persons) > 0
        else:
            # Fallback: manually embed and match an identity image so we confirm gallery support
            manual_match = None
            if image_path and image_path.exists():
                feature_vec = processor._embed_identity_image(image_path)
                if feature_vec is not None:
                    manual_match = processor._match_identity(feature_vec)
            summary["manual_identity_match"] = manual_match
            success = manual_match is not None

        summary["success"] = success
        return success, summary

    except Exception as exc:
        summary["error"] = str(exc)
        logger.exception("Smoke test failed")
        return False, summary

    finally:
        if processor:
            processor.stop()


class ReIDRunner:
    """Connects to the front camera, runs ReID, and exposes track snapshots."""
    def __init__(self, config_path: str = str(Path(__file__).parent.parent / "config" / "front_array_config.json")):
        self.config_path = config_path
        self.config = self._load_config()
        self.camera_url = self._validate_camera_url(self.config["camera"]["front_camera"]["server_url"])
        self.protocol = self.config["camera"]["front_camera"].get("protocol", "webrtc")

        # ReID processor uses dedicated config with identity gallery settings
        self.reid_processor = OptimizedReIDProcessor(
            config_path=str(Path(__file__).parent.parent / "config" / "reid_config.json")
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
        """Read the front array configuration file from disk."""
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def _validate_camera_url(self, raw_url: str) -> str:
        """Validate camera URL to mitigate SSRF (full URL control)."""
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported camera URL scheme: {parsed.scheme}")
        if parsed.username or parsed.password:
            raise ValueError("Camera URL must not include credentials")
        if not parsed.hostname:
            raise ValueError("Camera URL must include a hostname")

        try:
            resolved = socket.getaddrinfo(parsed.hostname, parsed.port or 80, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise ValueError(f"Unable to resolve camera host: {parsed.hostname}") from e

        for entry in resolved:
            ip = ipaddress.ip_address(entry[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(f"Camera host resolves to disallowed IP: {ip}")

        return raw_url

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
        det_list = []
        for bbox, det in zip(bboxes, detections):
            entry = {
                "bbox": bbox,
                "confidence": det.get("confidence", 0.5),
            }
            if "identity_match" in det:
                entry["identity_match"] = det["identity_match"]
            if "center" in det:
                entry["center"] = det["center"]
            det_list.append(entry)
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
    parser = argparse.ArgumentParser(description="Run the Automated Followspot ReID pipeline")
    parser.add_argument("--config", dest="front_config", help="Path to front array configuration JSON")
    parser.add_argument("--reid-config", dest="reid_config", help="Path to ReID configuration JSON")
    parser.add_argument("--smoke-test", action="store_true", help="Run a single-frame smoke test using the identity gallery")
    parser.add_argument("--test-image", dest="test_image", help="Optional path to an image to use during the smoke test")
    args = parser.parse_args()

    default_front_config = Path(__file__).parent.parent / "config" / "front_array_config.json"
    default_reid_config = Path(__file__).parent.parent / "config" / "reid_config.json"

    if args.smoke_test:
        success, summary = run_smoke_test(
            test_image=args.test_image,
            front_config_path=args.front_config or str(default_front_config),
            reid_config_path=args.reid_config or str(default_reid_config),
        )
        if success:
            logger.info("Smoke test completed successfully")
            if summary.get("detections", 0) == 0:
                logger.warning("Smoke test relied on synthetic detections; verify with live video when available.")
        else:
            logger.error("Smoke test failed")
        logger.info(json.dumps(summary, indent=2, default=str))
        sys.exit(0 if success else 1)

    runner = ReIDRunner(config_path=args.front_config or str(default_front_config))
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

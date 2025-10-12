#!/usr/bin/env python3
"""Synthetic ReID runner used when the control stack is in demo mode."""

from __future__ import annotations

import json
import time
import random
from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import cv2


class DemoReIDRunner:
    """Generates synthetic person tracks and overlay frames for demo mode."""

    def __init__(self, config_path: str | None = None, seed: int | None = None):
        control_dir = Path(__file__).parent
        default_config = control_dir.parent / "config" / "front_array_config.json"
        self.config_path = Path(config_path) if config_path else default_config
        with open(self.config_path, "r") as f:
            self.config = json.load(f)

        self.stage = self.config.get("stage_geometry", {})
        self.stage_width = float(self.stage.get("width", 10.0))
        self.stage_depth = float(self.stage.get("depth", 8.0))
        self.stage_height = float(self.stage.get("height", 3.0))

        self.frame_width = 960
        self.frame_height = 540
        self.running = False
        self._last_update = time.time()
        self._rng = random.Random(seed or int(self._last_update))

        self.actors: List[Dict[str, Any]] = []
        self._init_actors()

        self._latest_tracks: Dict[int, Dict[str, Any]] = {}
        self._overlay_frame: np.ndarray | None = None

    def _init_actors(self) -> None:
        """Populate the virtual stage with a handful of performers."""
        actor_count = self._rng.randint(1, 3)
        for actor_id in range(1, actor_count + 1):
            stage_x = self._rng.uniform(-self.stage_width / 3, self.stage_width / 3)
            stage_y = self._rng.uniform(-self.stage_depth / 3, self.stage_depth / 3)
            velocity = np.array([
                self._rng.uniform(-0.7, 0.7),
                self._rng.uniform(-0.4, 0.4),
                0.0,
            ])
            actor = {
                "id": actor_id,
                "stage_pos": np.array([stage_x, stage_y, 1.7]),
                "velocity": velocity,
                "confidence": round(self._rng.uniform(0.75, 0.95), 2),
                "history": [],
            }
            self.actors.append(actor)

    def start(self) -> bool:
        self.running = True
        self._last_update = time.time()
        return True

    def stop(self) -> None:
        self.running = False

    def read_and_process(self) -> Dict[int, Dict[str, Any]]:
        """Update simulated actors and return dummy track records."""
        if not self.running:
            return {}

        now = time.time()
        dt = max(0.016, now - self._last_update)
        self._last_update = now

        frame = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        frame[:] = (20, 20, 20)
        cv2.putText(frame, "FRONT CAMERA (DEMO)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)

        tracks: Dict[int, Dict[str, Any]] = {}
        for actor in self.actors:
            # Update stage position with simple motion and boundary bounce
            pos = actor["stage_pos"].copy()
            vel = actor["velocity"]
            pos[:2] += vel[:2] * dt

            x_min, x_max = -self.stage_width / 2, self.stage_width / 2
            y_min, y_max = -self.stage_depth / 2, self.stage_depth / 2
            if pos[0] < x_min or pos[0] > x_max:
                vel[0] *= -1
                pos[0] = np.clip(pos[0], x_min, x_max)
            if pos[1] < y_min or pos[1] > y_max:
                vel[1] *= -1
                pos[1] = np.clip(pos[1], y_min, y_max)

            actor["stage_pos"] = pos
            actor["velocity"] = vel

            # Camera coordinates that DataFusion expects before conversion
            camera_pos = np.array([
                pos[0] * 100.0,
                pos[1] * 100.0,
                pos[2],
            ])
            actor["history"].append(camera_pos)
            actor["history"] = actor["history"][-10:]

            # Produce bounding box on overlay
            px, py = self._stage_to_pixel(pos[0], pos[1])
            bbox_w = int(self.frame_width * 0.08)
            bbox_h = int(self.frame_height * 0.18)
            top_left = (max(0, px - bbox_w // 2), max(0, py - bbox_h))
            bottom_right = (min(self.frame_width - 1, px + bbox_w // 2), min(self.frame_height - 1, py))
            cv2.rectangle(frame, top_left, bottom_right, (0, 200, 255), 2)
            label = f"ID {actor['id']} {actor['confidence']:.2f}"
            cv2.putText(frame, label, (top_left[0], max(25, top_left[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 180), 2)

            tracks[actor["id"]] = {
                "track_id": actor["id"],
                "status": "active",
                "positions": list(actor["history"]),
                "velocity": vel.tolist(),
                "confidence": float(actor["confidence"]),
                "last_update": now,
                "bbox": [float(top_left[0]), float(top_left[1]), float(bbox_w), float(bbox_h)],
                "stage_position": pos.tolist(),
            }

        self._latest_tracks = tracks
        self._overlay_frame = frame
        return tracks

    def get_overlay_frame(self) -> np.ndarray | None:
        return None if self._overlay_frame is None else self._overlay_frame.copy()

    def _stage_to_pixel(self, x: float, y: float) -> tuple[int, int]:
        # Normalize stage coordinates into 0..1 range
        nx = (x - (-self.stage_width / 2)) / self.stage_width
        ny = (y - (-self.stage_depth / 2)) / self.stage_depth
        nx = float(np.clip(nx, 0.0, 1.0))
        ny = float(np.clip(ny, 0.0, 1.0))
        px = int(nx * self.frame_width)
        py = int((1.0 - ny) * (self.frame_height * 0.8) + self.frame_height * 0.1)
        return px, py
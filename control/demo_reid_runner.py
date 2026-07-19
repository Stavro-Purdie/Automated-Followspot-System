#!/usr/bin/env python3
"""Synthetic ReID runner used when the control stack is in demo mode."""

from __future__ import annotations

import json
import time
import random
from pathlib import Path
from typing import Dict, Any, List

import sys
from pathlib import Path

# Ensure project root is on sys.path so package-qualified imports resolve
_proj = Path(__file__).resolve().parent.parent
if str(_proj) not in sys.path:
    sys.path.insert(0, str(_proj))

import numpy as np
import cv2

from control.demo_stage_state import get_demo_stage_state


class DemoReIDRunner:
    """Generates synthetic person tracks and overlay frames for demo mode."""

    def __init__(self, config_path: str | None = None, seed: int | None = None):
        control_dir = Path(__file__).parent
        default_config = control_dir.parent / "config" / "front_array_config.json"
        self.config_path = Path(config_path) if config_path else default_config
        with open(self.config_path, "r") as f:
            self.config = json.load(f)

        stage_cfg = self.config.get("stage_geometry", {}) if isinstance(self.config, dict) else {}
        self.stage_width = float(stage_cfg.get("width", 10.0))
        self.stage_depth = float(stage_cfg.get("depth", 8.0))
        self.stage_height = float(stage_cfg.get("height", 3.0))

        self.frame_width = 960
        self.frame_height = 540
        self.running = False
        self._last_update = time.time()
        self._rng = random.Random(seed or int(self._last_update))

        self.stage_state = get_demo_stage_state(
            width=self.stage_width,
            depth=self.stage_depth,
            height=self.stage_height,
        )
        demo_cfg = self.config.get("demo_mode", {}) if isinstance(self.config, dict) else {}
        subject_count = demo_cfg.get("subject_count")
        if isinstance(subject_count, int) and subject_count > 0:
            self.stage_state.set_subject_count(subject_count)

        self._latest_tracks: Dict[int, Dict[str, Any]] = {}
        self._overlay_frame: np.ndarray | None = None
        self._history: Dict[int, List[np.ndarray]] = {}
        self._smoothed_positions: Dict[int, np.ndarray] = {}
        self._overlay_background = self._build_overlay_background()
        self._hud_color = (220, 220, 220)

    def start(self) -> bool:
        self.running = True
        self._last_update = time.time()
        return True

    def stop(self) -> None:
        self.running = False

    def read_and_process(self) -> Dict[int, Dict[str, Any]]:
        """Update simulated subjects and return dummy track records."""
        if not self.running:
            return self._latest_tracks

        now = time.time()
        self._last_update = now

        snapshots = self.stage_state.latest_snapshot()
        if not snapshots:
            snapshots = self.stage_state.sample_subjects()

        def _sort_key(subject: Dict[str, Any]) -> int:
            raw_id = subject.get("id", 0)
            if isinstance(raw_id, (int, float)):
                return int(raw_id)
            if isinstance(raw_id, str) and raw_id.isdigit():
                return int(raw_id)
            return hash(raw_id) % 10_000

        snapshots.sort(key=_sort_key)
        frame = self._overlay_background.copy()
        cv2.putText(
            frame,
            "FRONT CAMERA (DEMO)",
            (24, 44),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            self._hud_color,
            2,
        )

        tracks: Dict[int, Dict[str, Any]] = {}
        for subject in snapshots:
            raw_id = subject.get("id", 0)
            if isinstance(raw_id, (int, float)):
                subject_id = int(raw_id)
            elif isinstance(raw_id, str) and raw_id.isdigit():
                subject_id = int(raw_id)
            else:
                subject_id = hash(raw_id) % 10_000

            stage_pos = np.asarray(subject.get("stage_pos", np.zeros(3)), dtype=float)
            if stage_pos.size < 3:
                stage_pos = np.pad(stage_pos, (0, 3 - stage_pos.size), constant_values=1.7)
            stage_pos = self._smooth_stage_position(subject_id, stage_pos)

            velocity = np.asarray(subject.get("velocity", np.zeros(3)), dtype=float)
            if velocity.size < 3:
                velocity = np.pad(velocity, (0, 3 - velocity.size), constant_values=0.0)

            raw_conf = subject.get("confidence", 0.85)
            confidence = float(raw_conf) if isinstance(raw_conf, (int, float, str)) else 0.85

            raw_color = subject.get("color")
            if isinstance(raw_color, (list, tuple)) and len(raw_color) >= 3:
                color = tuple(int(raw_color[i]) for i in range(3))
            else:
                color = (80, 200, 255)

            px, py = self._stage_to_pixel(float(stage_pos[0]), float(stage_pos[1]))
            bbox_w = int(self.frame_width * 0.14)
            bbox_h = int(self.frame_height * 0.28)
            top_left = (max(0, px - bbox_w // 2), max(0, py - bbox_h))
            bottom_right = (
                min(self.frame_width - 1, px + bbox_w // 2),
                min(self.frame_height - 1, py),
            )

            cv2.rectangle(frame, top_left, bottom_right, color, 2)
            label = f"ID {subject_id} {confidence:.2f}"
            cv2.putText(
                frame,
                label,
                (top_left[0], max(30, top_left[1] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

            camera_point = np.array([
                float(stage_pos[0]) * 100.0,
                float(stage_pos[1]) * 100.0,
                float(stage_pos[2]),
            ])
            history = self._history.setdefault(subject_id, [])
            history.append(camera_point)
            if len(history) > 12:
                history.pop(0)

            tracks[subject_id] = {
                "track_id": subject_id,
                "status": "active",
                "positions": [pos.copy() for pos in history],
                "velocity": velocity.tolist(),
                "confidence": confidence,
                "last_update": now,
                "bbox": [
                    float(top_left[0]),
                    float(top_left[1]),
                    float(bbox_w),
                    float(bbox_h),
                ],
                "stage_position": stage_pos.tolist(),
            }

        self._latest_tracks = tracks
        self._overlay_frame = frame
        return tracks

    def get_overlay_frame(self) -> np.ndarray | None:
        return None if self._overlay_frame is None else self._overlay_frame.copy()

    def _build_overlay_background(self) -> np.ndarray:
        bg = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        bg[:] = (24, 24, 30)
        stage_margin_x = int(self.frame_width * 0.08)
        stage_margin_y = int(self.frame_height * 0.12)
        stage_rect = (
            stage_margin_x,
            stage_margin_y,
            self.frame_width - 2 * stage_margin_x,
            self.frame_height - stage_margin_y - int(self.frame_height * 0.1),
        )
        cv2.rectangle(
            bg,
            (stage_rect[0], stage_rect[1]),
            (stage_rect[0] + stage_rect[2], stage_rect[1] + stage_rect[3]),
            (38, 38, 50),
            -1,
        )
        cv2.rectangle(
            bg,
            (stage_rect[0], stage_rect[1]),
            (stage_rect[0] + stage_rect[2], stage_rect[1] + stage_rect[3]),
            (70, 70, 95),
            2,
        )

        center_x = stage_rect[0] + stage_rect[2] // 2
        cv2.line(
            bg,
            (center_x, stage_rect[1]),
            (center_x, stage_rect[1] + stage_rect[3]),
            (60, 60, 80),
            1,
        )
        for frac in (0.25, 0.5, 0.75):
            y = int(stage_rect[1] + stage_rect[3] * frac)
            cv2.line(
                bg,
                (stage_rect[0], y),
                (stage_rect[0] + stage_rect[2], y),
                (45, 45, 60),
                1,
                lineType=cv2.LINE_AA,
            )
        return bg

    def _smooth_stage_position(self, subject_id: int, current: np.ndarray) -> np.ndarray:
        if current.size < 3:
            current = np.pad(current, (0, 3 - current.size), constant_values=1.7)
        previous = self._smoothed_positions.get(subject_id)
        if previous is None:
            smoothed = current.copy()
        else:
            alpha = 0.25
            smoothed = previous + alpha * (current - previous)
        self._smoothed_positions[subject_id] = smoothed
        return smoothed.copy()

    def _stage_to_pixel(self, x: float, y: float) -> tuple[int, int]:
        nx = (x - (-self.stage_width / 2.0)) / max(self.stage_width, 1e-3)
        ny = (y - (-self.stage_depth / 2.0)) / max(self.stage_depth, 1e-3)
        nx = float(np.clip(nx, 0.0, 1.0))
        ny = float(np.clip(ny, 0.0, 1.0))
        px = int(nx * (self.frame_width * 0.84) + self.frame_width * 0.08)
        py = int((1.0 - ny) * (self.frame_height * 0.7) + self.frame_height * 0.2)
        return px, py
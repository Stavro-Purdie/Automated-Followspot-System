#!/usr/bin/env python3
"""Synthetic camera feeds used for demos, rehearsals, and test rigs.

glorified bouncing DVD logo at this point
"""

from __future__ import annotations

import cv2
import numpy as np
import time
import math
import random
import threading
import logging
from typing import Dict, List, Tuple, Optional, Any, Callable

from control.demo_stage_state import DemoStageState, get_demo_stage_state  # type: ignore[import-not-found]

logger = logging.getLogger("demo_mode")

class DemoVideoGenerator:
    """Build a stream of frames so operators can practise without cameras."""
    
    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        *,
        stage_state: Optional[DemoStageState] = None,
        camera_id: Optional[str] = None,
        view_bounds: Optional[Tuple[float, float, float, float]] = None,
        subject_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ):
        self.width = width
        self.height = height
        self.frame_count = 0
        self.running = True
        self.trail_length = 24
        self._ambient_phase = random.uniform(0, 2 * math.pi)
        self._base_radius = max(6, min(self.width, self.height) // 18)
        self.stage_state = stage_state if stage_state is not None else get_demo_stage_state()
        self.camera_id = camera_id or "demo"
        self._view_bounds = view_bounds
        self._view_margin_x = 0.0
        self._view_margin_y = 0.0
        self._subject_provider = subject_provider
        if self._view_bounds is not None and self.stage_state is not None:
            bbox_width = self._view_bounds[1] - self._view_bounds[0]
            bbox_height = self._view_bounds[3] - self._view_bounds[2]
            self._view_margin_x = max(0.12 * bbox_width, 0.45)
            self._view_margin_y = max(0.12 * bbox_height, 0.45)
        self._camera_variance = self._compute_camera_variance()
        self._stage_rect = self._calc_stage_rect()
        self._stage_background = self._build_stage_background()
        self._trails: Dict[int, List[Tuple[int, int]]] = {}
        
        # Animation state for smooth transitions
        self.animation_phase = 0.0
        self.animation_speed = 0.02
        self.glow_intensity = 0.35

    def _compute_camera_variance(self) -> float:
        """Derive a deterministic offset per camera to avoid identical renders."""
        seed = sum(ord(ch) for ch in self.camera_id) if self.camera_id else random.randint(0, 10_000)
        rng = random.Random(seed)
        return rng.uniform(-0.12, 0.12)

    def _calc_stage_rect(self) -> Tuple[int, int, int, int]:
        usable_width = int(self.width * 0.82)
        usable_height = int(self.height * 0.78)
        left = max(4, int(self.width * 0.09))
        top = max(4, int(self.height * 0.11))
        usable_width = max(10, min(self.width - 2 * left, usable_width))
        usable_height = max(10, min(self.height - top - int(self.height * 0.1), usable_height))
        return left, top, usable_width, usable_height

    def _build_stage_background(self) -> np.ndarray:
        """Create a static top-down stage map used as the base frame."""
        bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        apron_color = (18, 18, 24)
        stage_color = (28, 28, 35)
        grid_color = (35, 35, 45)
        highlight_color = (60, 60, 80)
        cv2.rectangle(bg, (0, 0), (self.width, self.height), apron_color, -1)

        left, top, rect_w, rect_h = self._stage_rect
        right = left + rect_w
        bottom = top + rect_h

        cv2.rectangle(bg, (left, top), (right, bottom), stage_color, -1)
        cv2.rectangle(bg, (left, top), (right, bottom), (50, 50, 68), 2)

        for frac in (0.25, 0.5, 0.75):
            x = int(left + rect_w * frac)
            y = int(top + rect_h * frac)
            cv2.line(bg, (x, top), (x, bottom), grid_color, 1)
            cv2.line(bg, (left, y), (right, y), grid_color, 1)

        if self._view_bounds is not None and self.stage_state is not None:
            x_min, x_max, y_min, y_max = self._view_bounds
            label = f"X:[{x_min:.1f},{x_max:.1f}] Y:[{y_min:.1f},{y_max:.1f}]"
            cv2.putText(
                bg,
                label,
                (left + 6, max(18, top - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                highlight_color,
                1,
                cv2.LINE_AA,
            )

        return cv2.GaussianBlur(bg, (0, 0), sigmaX=2)

    def _draw_ambient_light(self, frame: np.ndarray) -> None:
        """Overlay slow-moving soft lights to mimic stage ambience."""
        self._ambient_phase += 0.01
        cx = int(self.width * (0.5 + 0.15 * math.sin(self._ambient_phase)))
        cy = int(self.height * (0.5 + 0.2 * math.cos(self._ambient_phase * 0.8)))
        radius = int(min(self.width, self.height) * 0.45)
        gradient = np.zeros_like(frame)
        cv2.circle(gradient, (cx, cy), radius, (40, 40, 55), -1)
        cv2.GaussianBlur(gradient, (0, 0), sigmaX=radius / 6, dst=gradient)
        cv2.add(frame, gradient, frame)

    def _draw_trail(self, frame: np.ndarray, beacon: Dict[str, Any]) -> None:
        """Render the recent path of a beacon for motion context."""
        history = beacon['history'][-self.trail_length :]
        if len(history) < 2:
            return

        for idx in range(1, len(history)):
            alpha = idx / len(history)
            start = history[idx - 1]
            end = history[idx]
            color = tuple(int(c * alpha) for c in beacon['color'])
            cv2.line(frame, start, end, color, 2)
    
    def generate_frame(self) -> np.ndarray:
        """Generate a single demo frame"""
        # Update animation phase for smooth transitions
        self.animation_phase += self.animation_speed
        if self.animation_phase > 2 * math.pi:
            self.animation_phase -= 2 * math.pi
        
        frame = self._stage_background.copy()
        self._draw_ambient_light(frame)

        subjects = self._get_subjects()
        active_ids = set()
        for subject in subjects:
            subject_id = int(subject.get('id', 0))
            center = self._stage_to_frame(subject['stage_pos'])
            brightness = self._compute_subject_brightness(subject)
            radius = self._subject_radius(subject)
            color = subject['color']

            # Draw motion trail for smoother perception
            history = self._trails.setdefault(subject_id, [])
            history.append(center)
            if len(history) > self.trail_length + 2:
                del history[0]

            self._draw_trail(frame, {'history': history, 'color': color})  # type: ignore[arg-type]
            active_ids.add(subject_id)

            # Soft glow base with animated intensity
            glow = np.zeros_like(frame)
            # Smooth pulsing glow using sine wave
            glow_factor = 0.3 + 0.15 * math.sin(self.animation_phase + subject_id * 0.5)
            cv2.circle(glow, center, radius + 12, tuple(int(c * 0.6) for c in color), -1)
            cv2.GaussianBlur(glow, (0, 0), sigmaX=max(radius * 0.6, 1.0), dst=glow)
            cv2.addWeighted(frame, 1.0, glow, glow_factor, 0, frame)

            cv2.circle(frame, center, radius, color, -1)
            cv2.circle(frame, center, max(2, int(radius * 0.6)), (255, 255, 255), -1)
            cv2.circle(frame, center, max(1, radius // 3), (brightness, brightness, brightness), -1)

        # Remove stale trails to avoid ghosts when subject leaves view
        stale_ids = [sid for sid in self._trails.keys() if sid not in active_ids]
        for sid in stale_ids:
            self._trails.pop(sid, None)

        self.frame_count += 1
        return frame

    # ------------------------------------------------------------------
    # Subject helpers
    # ------------------------------------------------------------------
    def _get_subjects(self) -> List[Dict[str, Any]]:
        if self._subject_provider is not None:
            snapshots = self._subject_provider()
        elif self.stage_state is None:
            return []
        else:
            snapshots = self.stage_state.sample_subjects()
        # Attach per-camera jitter without changing shared state
        adjusted: List[Dict[str, Any]] = []
        for subject in snapshots:
            clone = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in subject.items()}
            pos = clone.get('stage_pos')
            if isinstance(pos, np.ndarray):
                if self._view_bounds is not None:
                    if not self._subject_visible(pos):
                        continue
            adjusted.append(clone)
        return adjusted

    def _stage_to_frame(self, stage_pos: np.ndarray) -> Tuple[int, int]:
        if self.stage_state is None:
            return self.width // 2, self.height // 2
        if self._view_bounds is not None:
            x_min, x_max, y_min, y_max = self._view_bounds
        else:
            width, depth, _ = self.stage_state.stage_dimensions()
            x_min, x_max = -width / 2.0, width / 2.0
            y_min, y_max = -depth / 2.0, depth / 2.0

        span_x = max(x_max - x_min, 1e-4)
        span_y = max(y_max - y_min, 1e-4)
        nx = (float(stage_pos[0]) - x_min) / span_x
        ny = (float(stage_pos[1]) - y_min) / span_y
        nx = float(np.clip(nx, 0.0, 1.0))
        ny = float(np.clip(ny, 0.0, 1.0))
        left, top, rect_w, rect_h = self._stage_rect
        px = int(left + nx * rect_w)
        py = int(top + (1.0 - ny) * rect_h)
        return px, py

    def _compute_subject_brightness(self, subject: Dict[str, Any]) -> int:
        base = float(subject.get('confidence', 0.85))
        pulse_phase = float(subject.get('pulse_phase', 0.0)) + self._ambient_phase * 0.2
        pulse = 0.6 + 0.4 * (math.sin(pulse_phase) * 0.5 + 0.5)
        brightness = int(np.clip(180 * base * pulse, 140, 255))
        return brightness

    def _subject_radius(self, subject: Dict[str, Any]) -> int:
        speed = np.linalg.norm(subject.get('velocity', np.zeros(3))[:2])
        radius = self._base_radius * (1.0 + 0.3 * speed)
        return max(6, int(radius))

    def _subject_visible(self, stage_pos: np.ndarray) -> bool:
        if self._view_bounds is None:
            return True
        x_min, x_max, y_min, y_max = self._view_bounds
        return (
            (x_min - self._view_margin_x) <= float(stage_pos[0]) <= (x_max + self._view_margin_x)
            and (y_min - self._view_margin_y) <= float(stage_pos[1]) <= (y_max + self._view_margin_y)
        )

class DemoCameraManager:
    """Manages multiple demo camera feeds"""
    
    def __init__(self, camera_configs: Dict, *, stage_state: Optional[DemoStageState] = None):
        self.camera_configs = camera_configs
        self.generators = {}
        self.latest_frames = {}
        self.frame_lock = threading.Lock()
        self.running = True
        self.stage_state = stage_state if stage_state is not None else get_demo_stage_state()
        self._snapshot_lock = threading.Lock()
        self._latest_snapshot: List[Dict[str, Any]] = []
        self._stage_thread: Optional[threading.Thread] = None
        self._stage_interval = 1.0 / 30.0
        self._camera_view_bounds: Dict[str, Tuple[float, float, float, float]] = {}
        self._grid_cols = 1
        self._grid_rows = 1
        self._subject_target = 0
        self._compute_layout()
        self._align_subject_count()
        self._refresh_stage_snapshot()
        self._start_stage_thread()
        
        # Initialize generators for each camera
        for camera_id, config in camera_configs.items():
            if config.enabled:
                # Use crop dimensions if available, otherwise default
                crop_rect = config.crop_rect
                width = crop_rect[2] if crop_rect[2] > 0 else 640
                height = crop_rect[3] if crop_rect[3] > 0 else 480

                # Extremely small crops create invalid demo beacon ranges; fall back to a minimum size
                min_width, min_height = 120, 120
                if width < min_width or height < min_height:
                    logger.warning(
                        "Camera %s crop %dx%d too small for demo mode, using fallback %dx%d",
                        camera_id,
                        width,
                        height,
                        max(width, min_width),
                        max(height, min_height),
                    )
                    width = max(width, min_width)
                    height = max(height, min_height)

                self.generators[camera_id] = DemoVideoGenerator(
                    width,
                    height,
                    stage_state=self.stage_state,
                    camera_id=camera_id,
                    view_bounds=self._camera_view_bounds.get(camera_id),
                    subject_provider=self._get_stage_snapshot,
                )
        
        # Start generation threads
        self.start_generation_threads()

    def _compute_layout(self) -> None:
        """Map each camera to a slice of stage coordinates for view filtering."""
        self._camera_view_bounds = {}
        if self.stage_state is None or not self.camera_configs:
            return

        width, depth, _ = self.stage_state.stage_dimensions()
        enabled_configs = [cfg for cfg in self.camera_configs.values() if getattr(cfg, "enabled", True)]
        if not enabled_configs:
            return

        max_col = 0
        max_row = 0
        for cfg in enabled_configs:
            grid_pos = getattr(cfg, "position", (0, 0)) or (0, 0)
            try:
                col, row = int(grid_pos[0]), int(grid_pos[1])
            except (TypeError, ValueError, IndexError):
                col, row = 0, 0
            max_col = max(max_col, col)
            max_row = max(max_row, row)

        cols = max(max_col + 1, 1)
        rows = max(max_row + 1, 1)
        self._grid_cols = cols
        self._grid_rows = rows
        x_origin = -width / 2.0
        y_origin = -depth / 2.0
        col_width = width / cols
        row_height = depth / rows

        for cfg in enabled_configs:
            grid_pos = getattr(cfg, "position", (0, 0)) or (0, 0)
            try:
                col, row = int(grid_pos[0]), int(grid_pos[1])
            except (TypeError, ValueError, IndexError):
                col, row = 0, 0
            col = max(0, min(cols - 1, col))
            row = max(0, min(rows - 1, row))

            x_min = x_origin + col * col_width
            x_max = x_min + col_width
            y_min = y_origin + row * row_height
            y_max = y_min + row_height
            self._camera_view_bounds[cfg.camera_id] = (x_min, x_max, y_min, y_max)
    
    def _align_subject_count(self) -> None:
        if self.stage_state is None:
            return
        enabled = [cfg for cfg in self.camera_configs.values() if getattr(cfg, "enabled", True)]
        if not enabled:
            return
        target = max(1, len(enabled))
        self._subject_target = target
        try:
            self.stage_state.set_subject_count(target)
            self.stage_state.sample_subjects(ensure_count=target)
            self.stage_state.redistribute_subjects(self._grid_cols, self._grid_rows)
        except Exception:
            logger.exception("Failed to align demo subject count", exc_info=True)

    def start_generation_threads(self):
        """Start frame generation threads for each camera"""
        for camera_id, generator in self.generators.items():
            thread = threading.Thread(
                target=self.generate_frames_for_camera,
                args=(camera_id, generator),
                daemon=True
            )
            thread.start()
            logger.info(f"Started demo feed for camera {camera_id}")
    
    def generate_frames_for_camera(self, camera_id: str, generator: DemoVideoGenerator):
        """Generate frames for a specific camera"""
        fps = 15  # Reduced FPS for better performance
        frame_time = 1.0 / fps
        
        while self.running:
            start_time = time.time()
            
            # Generate frame
            frame = generator.generate_frame()
            
            # Store frame
            with self.frame_lock:
                self.latest_frames[camera_id] = frame
            
            # Maintain FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_time - elapsed)
            time.sleep(sleep_time)
    
    def get_latest_frames(self) -> Dict[str, np.ndarray]:
        """Get latest frames from all cameras"""
        with self.frame_lock:
            return self.latest_frames.copy()
    
    def stop(self):
        """Stop all generation threads"""
        self.running = False
        if self._stage_thread and self._stage_thread.is_alive():
            self._stage_thread.join(timeout=0.5)
        logger.info("Stopped all demo camera feeds")

    def _refresh_stage_snapshot(self) -> None:
        if self.stage_state is None:
            return
        ensure = self._subject_target if self._subject_target > 0 else None
        snapshots = self.stage_state.sample_subjects(ensure_count=ensure)
        with self._snapshot_lock:
            self._latest_snapshot = [self._clone_subject(snapshot) for snapshot in snapshots]

    def _start_stage_thread(self) -> None:
        if self.stage_state is None:
            return

        def _loop() -> None:
            while self.running:
                start = time.time()
                ensure = self._subject_target if self._subject_target > 0 else None
                snapshots = self.stage_state.sample_subjects(ensure_count=ensure)
                with self._snapshot_lock:
                    self._latest_snapshot = [self._clone_subject(snapshot) for snapshot in snapshots]
                elapsed = time.time() - start
                delay = max(0.0, self._stage_interval - elapsed)
                time.sleep(delay)

        self._stage_thread = threading.Thread(target=_loop, name="demo-stage-updater", daemon=True)
        self._stage_thread.start()

    def _get_stage_snapshot(self) -> List[Dict[str, Any]]:
        with self._snapshot_lock:
            if not self._latest_snapshot:
                return []
            return [self._clone_subject(snapshot) for snapshot in self._latest_snapshot]

    @staticmethod
    def _clone_subject(subject: Dict[str, Any]) -> Dict[str, Any]:
        clone: Dict[str, Any] = {}
        for key, value in subject.items():
            if isinstance(value, np.ndarray):
                clone[key] = value.copy()
            else:
                clone[key] = value
        return clone

if __name__ == "__main__":
    # Test demo mode
    import sys
    import os
    
    # Add parent directory to path to import camera config
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Test with some dummy camera configs
    from dataclasses import dataclass
    
    @dataclass
    class TestCameraConfig:
        server_url: str
        crop_rect: tuple
        position: tuple
        camera_id: str
        enabled: bool = True
    
    # Create test configs
    test_configs = {
        "cam_1": TestCameraConfig("http://test:8080", (0, 0, 640, 480), (0, 0), "cam_1"),
        "cam_2": TestCameraConfig("http://test:8080", (0, 0, 640, 480), (1, 0), "cam_2")
    }
    
    # Start demo
    demo_manager = DemoCameraManager(test_configs)
    
    try:
        print("Demo mode running... Press Ctrl+C to stop")
        time.sleep(5)
        
        # Get some frames
        frames = demo_manager.get_latest_frames()
        print(f"Generated frames for cameras: {list(frames.keys())}")
        
        for camera_id, frame in frames.items():
            print(f"Camera {camera_id}: frame shape {frame.shape}")
            
    except KeyboardInterrupt:
        print("Stopping demo...")
    finally:
        demo_manager.stop()

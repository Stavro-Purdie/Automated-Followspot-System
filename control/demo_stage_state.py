#!/usr/bin/env python3
"""Shared synthetic stage state for demo mode components."""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class _DemoSubject:
    """Mutable internal representation of a demo performer."""

    id: int
    stage_pos: np.ndarray
    velocity: np.ndarray
    confidence: float
    color: Tuple[int, int, int]
    pulse_phase: float
    pulse_speed: float

    def snapshot(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "stage_pos": self.stage_pos.copy(),
            "velocity": self.velocity.copy(),
            "confidence": float(self.confidence),
            "color": self.color,
            "pulse_phase": float(self.pulse_phase),
        }


class DemoStageState:
    """Maintains a shared set of synthetic performers for demo mode."""

    def __init__(
        self,
        width: float = 12.0,
        depth: float = 8.0,
        height: float = 3.5,
        *,
        subject_count: int = 3,
        seed: Optional[int] = None,
    ) -> None:
        self.width = max(1.0, float(width))
        self.depth = max(1.0, float(depth))
        self.height = max(1.0, float(height))
        self._rng = random.Random(seed or int(time.time()))
        self._lock = threading.RLock()
        self._subjects: Dict[int, _DemoSubject] = {}
        self._next_id = 1
        self._last_update = time.time()
        self._last_snapshot: List[Dict[str, object]] = []
        self._ensure_subject_count(subject_count)

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    def configure_stage(
        self,
        *,
        width: Optional[float] = None,
        depth: Optional[float] = None,
        height: Optional[float] = None,
    ) -> None:
        """Update stage dimensions while keeping performers in bounds."""

        with self._lock:
            if width is not None:
                self.width = max(1.0, float(width))
            if depth is not None:
                self.depth = max(1.0, float(depth))
            if height is not None:
                self.height = max(1.0, float(height))

            for subject in self._subjects.values():
                subject.stage_pos[0] = float(
                    np.clip(subject.stage_pos[0], -self.width / 2.0, self.width / 2.0)
                )
                subject.stage_pos[1] = float(
                    np.clip(subject.stage_pos[1], -self.depth / 2.0, self.depth / 2.0)
                )
                subject.stage_pos[2] = float(
                    np.clip(subject.stage_pos[2], 0.5, max(self.height - 0.2, 0.5))
                )

    def set_subject_count(self, count: int) -> None:
        """Grow or shrink the subject pool to the requested size."""

        self._ensure_subject_count(count)

    def redistribute_subjects(self, cols: int, rows: int) -> None:
        """Roughly tile subjects across the stage so each camera sees activity."""

        cols = max(1, int(cols))
        rows = max(1, int(rows))
        with self._lock:
            if not self._subjects:
                return

            step_x = self.width / cols
            step_y = self.depth / rows
            x_min = -self.width / 2.0
            y_min = -self.depth / 2.0

            grid_slots = [
                (col, row)
                for row in range(rows)
                for col in range(cols)
            ]

            # Keep assignment stable by pairing lowest IDs with the first slots
            subject_items = sorted(self._subjects.items(), key=lambda item: item[0])
            for (subject_id, subject), (col, row) in zip(subject_items, grid_slots):
                centre_x = x_min + (col + 0.5) * step_x
                centre_y = y_min + (row + 0.5) * step_y
                subject.stage_pos[0] = float(
                    np.clip(
                        centre_x + self._rng.uniform(-0.25 * step_x, 0.25 * step_x),
                        x_min,
                        x_min + cols * step_x,
                    )
                )
                subject.stage_pos[1] = float(
                    np.clip(
                        centre_y + self._rng.uniform(-0.25 * step_y, 0.25 * step_y),
                        y_min,
                        y_min + rows * step_y,
                    )
                )
                subject.velocity[0] = self._rng.uniform(-0.6, 0.6)
                subject.velocity[1] = self._rng.uniform(-0.4, 0.4)

    def get_subject_count(self) -> int:
        with self._lock:
            return len(self._subjects)

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def sample_subjects(self, *, ensure_count: Optional[int] = None) -> List[Dict[str, object]]:
        """Advance the simulation and return a snapshot of all subjects."""

        with self._lock:
            if ensure_count is not None:
                self._ensure_subject_count(ensure_count)

            now = time.time()
            dt = max(0.016, min(0.08, now - self._last_update))
            self._advance(dt)
            self._last_update = now

            self._last_snapshot = [subject.snapshot() for subject in self._subjects.values()]
            return [snapshot.copy() for snapshot in self._last_snapshot]

    def latest_snapshot(self) -> List[Dict[str, object]]:
        """Return the last produced snapshot without advancing the simulation."""

        with self._lock:
            if not self._last_snapshot:
                return self.sample_subjects()
            return [snapshot.copy() for snapshot in self._last_snapshot]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_subject_count(self, count: int) -> None:
        target = max(1, int(count))
        with self._lock:
            while len(self._subjects) < target:
                subject = self._create_subject(self._next_id)
                self._subjects[self._next_id] = subject
                self._next_id += 1
            while len(self._subjects) > target:
                remove_id = sorted(self._subjects.keys())[-1]
                self._subjects.pop(remove_id)
            if not self._last_snapshot:
                # Seed snapshot so consumers have something immediately
                self._last_snapshot = [subject.snapshot() for subject in self._subjects.values()]

    def _create_subject(self, subject_id: int) -> _DemoSubject:
        stage_x = self._rng.uniform(-self.width * 0.35, self.width * 0.35)
        stage_y = self._rng.uniform(-self.depth * 0.35, self.depth * 0.35)
        stage_z = self._rng.uniform(self.height * 0.45, self.height * 0.7)
        velocity = np.array([
            self._rng.uniform(-0.8, 0.8),
            self._rng.uniform(-0.5, 0.5),
            0.0,
        ], dtype=float)
        confidence = round(self._rng.uniform(0.78, 0.96), 2)
        color: Tuple[int, int, int] = (
            self._rng.randint(110, 235),
            self._rng.randint(110, 235),
            self._rng.randint(110, 235),
        )
        pulse_phase = self._rng.uniform(0.0, math.tau)
        pulse_speed = self._rng.uniform(0.6, 1.3)
        return _DemoSubject(
            id=subject_id,
            stage_pos=np.array([stage_x, stage_y, stage_z], dtype=float),
            velocity=velocity,
            confidence=confidence,
            color=color,
            pulse_phase=pulse_phase,
            pulse_speed=pulse_speed,
        )

    def _advance(self, dt: float) -> None:
        x_min, x_max = -self.width / 2.0, self.width / 2.0
        y_min, y_max = -self.depth / 2.0, self.depth / 2.0

        for subject in self._subjects.values():
            subject.stage_pos[:2] += subject.velocity[:2] * dt

            # Apply gentle noise to keep motion organic
            if self._rng.random() < 0.04:
                subject.velocity[0] += self._rng.uniform(-0.15, 0.15)
                subject.velocity[1] += self._rng.uniform(-0.1, 0.1)

            subject.velocity[0] = float(np.clip(subject.velocity[0], -1.0, 1.0))
            subject.velocity[1] = float(np.clip(subject.velocity[1], -0.7, 0.7))

            if subject.stage_pos[0] < x_min or subject.stage_pos[0] > x_max:
                subject.velocity[0] *= -1.0
                subject.stage_pos[0] = float(np.clip(subject.stage_pos[0], x_min, x_max))
            if subject.stage_pos[1] < y_min or subject.stage_pos[1] > y_max:
                subject.velocity[1] *= -1.0
                subject.stage_pos[1] = float(np.clip(subject.stage_pos[1], y_min, y_max))

            subject.pulse_phase += subject.pulse_speed * dt

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    def stage_dimensions(self) -> tuple[float, float, float]:
        return self.width, self.depth, self.height


_DEMO_STAGE_STATE: Optional[DemoStageState] = None


def get_demo_stage_state(
    *,
    width: Optional[float] = None,
    depth: Optional[float] = None,
    height: Optional[float] = None,
    subject_count: Optional[int] = None,
    seed: Optional[int] = None,
) -> DemoStageState:
    """Return the shared demo stage state instance, configuring if needed."""

    global _DEMO_STAGE_STATE
    if _DEMO_STAGE_STATE is None:
        _DEMO_STAGE_STATE = DemoStageState(
            width=width or 12.0,
            depth=depth or 8.0,
            height=height or 3.5,
            subject_count=subject_count or 3,
            seed=seed,
        )
    else:
        if any(value is not None for value in (width, depth, height)):
            _DEMO_STAGE_STATE.configure_stage(width=width, depth=depth, height=height)
        if subject_count is not None:
            _DEMO_STAGE_STATE.set_subject_count(subject_count)
    return _DEMO_STAGE_STATE

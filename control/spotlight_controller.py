#!/usr/bin/env python3
"""Translate fused performer positions into followspot pan/tilt commands."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("spotlight_controller")


class SpotlightController:

    def __init__(self, config_path: str | Path = Path("config/spotlight_config.json")):
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)

        rig_cfg = self.config.get("rig", {})
        self.fixture_position = np.array(rig_cfg.get("fixture_position_m", [0.0, -5.0, 6.0]), dtype=float)
        self.stage_origin = np.array(rig_cfg.get("stage_origin_m", [0.0, 0.0, 0.0]), dtype=float)
        self.pan_zero = float(rig_cfg.get("pan_zero_angle_deg", 0.0))
        self.tilt_zero = float(rig_cfg.get("tilt_zero_angle_deg", -45.0))
        self.pan_limits = tuple(rig_cfg.get("pan_limits_deg", [-120.0, 120.0]))
        self.tilt_limits = tuple(rig_cfg.get("tilt_limits_deg", [-120.0, 10.0]))

        smoothing_cfg = rig_cfg.get("smoothing", {})
        self.pan_alpha = float(smoothing_cfg.get("pan_alpha", 0.25))
        self.tilt_alpha = float(smoothing_cfg.get("tilt_alpha", 0.25))

        self.dmx_config = self.config.get("dmx", {})

        self.last_pan: Optional[float] = None
        self.last_tilt: Optional[float] = None
        self.last_command: Optional[Dict] = None

        logger.info("SpotlightController initialized at %s", self.config_path)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def update_from_targets(self, targets: List[Dict], timestamp: float) -> Optional[Dict]:
        """Pick the best target and compute a new pan/tilt command."""
        if not targets:
            return None

        target = targets[0]  # Targets already sorted by confidence by DataFusion
        position = np.array([target["x"], target["y"], target["z"]], dtype=float)
        command = self._compute_command(position)
        command.update(
            {
                "target_id": target["id"],
                "target_confidence": target["confidence"],
                "axis_confidence": target.get("axis_confidence", [0.0, 0.0, 0.0]),
                "timestamp": timestamp,
            }
        )

        if self._command_has_changed(command):
            self.last_command = command
            self.last_pan = command["pan_deg"]
            self.last_tilt = command["tilt_deg"]
            self._send_command(command)
        else:
            command = self.last_command

        return command

    def get_last_command(self) -> Optional[Dict]:
        return self.last_command

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_config(self, path: Path) -> Dict:
        if not path.exists():
            logger.warning("Spotlight config %s missing; using defaults", path)
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _compute_command(self, target_position: np.ndarray) -> Dict[str, float]:
        rel = target_position - self.fixture_position
        horizontal_distance = math.hypot(rel[0], rel[1])
        pan_rad = math.atan2(rel[0], rel[1])
        tilt_rad = math.atan2(rel[2], horizontal_distance)

        pan_deg = math.degrees(pan_rad) + self.pan_zero
        tilt_deg = math.degrees(tilt_rad) + self.tilt_zero

        pan_deg = float(np.clip(pan_deg, self.pan_limits[0], self.pan_limits[1]))
        tilt_deg = float(np.clip(tilt_deg, self.tilt_limits[0], self.tilt_limits[1]))

        pan_deg = self._smooth_value(pan_deg, self.last_pan, self.pan_alpha)
        tilt_deg = self._smooth_value(tilt_deg, self.last_tilt, self.tilt_alpha)

        return {
            "pan_deg": pan_deg,
            "tilt_deg": tilt_deg,
            "fixture_position": self.fixture_position.tolist(),
            "target_position": target_position.tolist(),
        }

    @staticmethod
    def _smooth_value(current: float, last: Optional[float], alpha: float) -> float:
        if last is None:
            return current
        return (alpha * current) + ((1 - alpha) * last)

    def _command_has_changed(self, command: Dict) -> bool:
        if self.last_command is None:
            return True
        return (
            abs(command["pan_deg"] - self.last_command["pan_deg"]) > 0.1
            or abs(command["tilt_deg"] - self.last_command["tilt_deg"]) > 0.1
        )

    def _send_command(self, command: Dict) -> None:
        """Placeholder for DMX/Maestro integration."""
        logger.debug(
            "Spotlight command pan=%.2f tilt=%.2f target=%s",
            command["pan_deg"],
            command["tilt_deg"],
            command.get("target_id"),
        )
        # TODO: integrate with actual lighting control transport


__all__ = ["SpotlightController"]

#!/usr/bin/env python3
"""
Tie the roof IR rig and the front ReID camera into one feedback loop.
"""

import asyncio
import time
import logging
from pathlib import Path
from typing import Dict, List
import sys

import numpy as np

# Make sure the project root is on sys.path when launched directly from control/
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from control.camera_aggregator import MultiCameraManager
from control.reid_runner import ReIDRunner
from fusion.data_fusion import DataFusion
from control.spotlight_controller import SpotlightController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fused_main")


class FusedController:
    """Owns the lifecycle of the IR array, the ReID runner, and the fusion engine."""
    def __init__(self,
                 roof_config: str = str(Path(__file__).parent.parent / "config" / "roof_array_config.json"),
                 front_config: str = str(Path(__file__).parent.parent / "config" / "front_array_config.json")):
        self.roof_config = roof_config
        self.front_config = front_config

        # Initialize subsystems
        self.roof_manager = MultiCameraManager(self.roof_config, demo_mode=False)
        self.reid_runner = ReIDRunner(self.front_config)

        # Data fusion uses front config for fusion params
        self.fusion = DataFusion(self.reid_runner.config)

        # Spotlight controller handles pan/tilt computation
        self.spotlight = SpotlightController()

        self.loop_running = False
        self.latest_persons = {}
        self.latest_positions: List[Dict] = []
        self.latest_spotlight_command = None

    async def start(self):
        """Kick off camera connections and the ReID runner before entering the loop."""
        # Start roof connections asynchronously (use existing CLI helpers)
        logger.info("Starting roof camera connections...")
        # Connect cameras
        enabled = [c for c in self.roof_manager.cameras.values() if c.enabled]
        if not enabled:
            logger.error("No roof cameras enabled.")
        else:
            tasks = [asyncio.create_task(self._connect_camera(c)) for c in enabled]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Start ReID runner
        if not self.reid_runner.start():
            logger.warning("ReID runner did not start; proceeding with IR only")

        self.loop_running = True

    async def _connect_camera(self, cfg):
        """Wrapper around the aggregator's connect helper with friendlier logging."""
        from control.camera_aggregator import connect_to_camera
        try:
            await connect_to_camera(cfg, self.roof_manager)
        except Exception as e:
            logger.error(f"Camera connect error: {e}")

    def step(self):
        """One fused step: gather IR beacons from roof composite and ReID tracks, then fuse."""
        # Build composite and detect beacons
        composite = self.roof_manager.create_composite_frame()
        ir_beacons = []
        if composite is not None:
            beacons, _viz = self.roof_manager.detect_ir_beacons_composite(composite)
            # Map to positions; placeholder conversion from pixels to meters
            for i, b in enumerate(beacons):
                cx, cy = b["center"]
                ir_beacons.append({
                    "id": i,
                    "x": float(cx) * 0.01,
                    "y": float(cy) * 0.01,
                    "confidence": 0.8
                })

        # Get ReID tracks
        reid_tracks = self.reid_runner.read_and_process() if self.reid_runner.running else {}

        # Fuse
        now = time.time()
        fused = self.fusion.update_fusion(reid_tracks, ir_beacons, now)
        self.latest_persons = fused
        self.latest_positions = self.fusion.get_person_positions()
        self.latest_spotlight_command = self.spotlight.update_from_targets(self.latest_positions, now)
        return self.latest_positions

    def get_positions(self):
        """Return fused person positions sorted by confidence"""
        if not self.latest_positions:
            self.latest_positions = self.fusion.get_person_positions()
        return self.latest_positions

    def get_spotlight_command(self):
        """Return the most recent pan/tilt command."""
        return self.latest_spotlight_command

    def get_stats(self):
        """Return fusion statistics"""
        return self.fusion.get_fusion_stats()


async def main():
    controller = FusedController()
    await controller.start()
    logger.info("Fused controller started. Press Ctrl+C to stop.")
    try:
        while True:
            positions = controller.step()
            logger.info("Fused persons: %s", len(positions))
            if positions:
                top = positions[0]
                logger.info(
                    "Top target XYZ=(%.2f, %.2f, %.2f) axis_conf=%s",
                    top["x"],
                    top["y"],
                    top["z"],
                    top["axis_confidence"],
                )
            if controller.latest_spotlight_command:
                cmd = controller.latest_spotlight_command
                logger.info("Spotlight pan=%.2f tilt=%.2f", cmd["pan_deg"], cmd["tilt_deg"])
            await asyncio.sleep(0.03)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(main())

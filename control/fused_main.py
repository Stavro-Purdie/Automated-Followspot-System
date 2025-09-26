#!/usr/bin/env python3
"""
Fused control orchestrator
Runs roof IR beacon tracker and front ReID tracker together, fuses outputs,
and provides a single control loop.
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

from camera_aggregator import MultiCameraManager
from reid_runner import ReIDRunner
from fusion.data_fusion import DataFusion

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fused_main")


class FusedController:
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

        self.loop_running = False

    async def start(self):
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
        from camera_aggregator import connect_to_camera
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
        return fused

    def get_positions(self):
        """Return fused person positions sorted by confidence"""
        return self.fusion.get_person_positions()

    def get_stats(self):
        """Return fusion statistics"""
        return self.fusion.get_fusion_stats()


async def main():
    controller = FusedController()
    await controller.start()
    logger.info("Fused controller started. Press Ctrl+C to stop.")
    try:
        while True:
            fused = controller.step()
            # Simple log output: number of persons
            logger.info(f"Fused persons: {len(fused)}")
            await asyncio.sleep(0.03)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Spotlight Alignment Verification Tool.

Verifies that the computed pan/tilt angles from the spotlight controller
match the actual fixture position by comparing against known reference points.

Usage:
    python3 tools/verify_spotlight_alignment.py --config config/spotlight_config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from control.spotlight_controller import SpotlightController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("spotlight_verification")


class SpotlightVerification:
    """Verify spotlight alignment against reference points."""

    def __init__(self, config_path: str):
        """Initialize with spotlight configuration."""
        self.config_path = Path(config_path)
        self.spotlight = SpotlightController(str(config_path))
        self.results: List[Dict[str, Any]] = []

    def run_grid_verification(
        self,
        x_range: Tuple[float, float],
        y_range: Tuple[float, float],
        z: float,
        step: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Run verification on a grid of points.

        Args:
            x_range: (min_x, max_x) in meters
            y_range: (min_y, max_y) in meters
            z: Height in meters
            step: Grid spacing in meters

        Returns:
            List of verification results
        """
        results = []

        x = x_range[0]
        point_id = 0
        while x <= x_range[1]:
            y = y_range[0]
            while y <= y_range[1]:
                point_id += 1
                logger.info(f"Verifying point {point_id}: ({x:.2f}, {y:.2f}, {z:.2f})")

                result = self.verify_point(x, y, z, point_id)
                results.append(result)

                # Log result
                if result["success"]:
                    logger.info(
                        f"  Point {point_id}: pan={result['pan_deg']:.2f}°, "
                        f"tilt={result['tilt_deg']:.2f}°, "
                        f"distance={result['distance_m']:.2f}m"
                    )
                else:
                    logger.warning(f"  Point {point_id}: FAILED - {result['error']}")

                y += step
            x += step

        return results

    def verify_point(self, x: float, y: float, z: float, point_id: int) -> Dict[str, Any]:
        """Verify a single point."""
        target = {"x": x, "y": y, "z": z}
        try:
            command = self.spotlight.update_from_targets([target], time.time())
            if command is None:
                return {
                    "point_id": point_id,
                    "target": target,
                    "success": False,
                    "error": "No command generated",
                }

            # Calculate expected distance
            fixture = np.array(self.spotlight.fixture_position)
            target_pos = np.array([x, y, z])
            distance = np.linalg.norm(target_pos - fixture)

            return {
                "point_id": point_id,
                "target": target,
                "success": True,
                "pan_deg": command["pan_deg"],
                "tilt_deg": command["tilt_deg"],
                "distance_m": distance,
                "fixture_position": fixture.tolist(),
            }
        except Exception as e:
            return {
                "point_id": point_id,
                "target": target,
                "success": False,
                "error": str(e),
            }

    def verify_known_positions(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Verify a list of known positions.

        Args:
            positions: List of {"name": str, "x": float, "y": float, "z": float}

        Returns:
            List of verification results
        """
        results = []
        for pos in positions:
            logger.info(f"Verifying known position: {pos['name']} ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
            result = self.verify_point(pos["x"], pos["y"], pos["z"], pos.get("point_id", 0))
            result["name"] = pos.get("name", f"point_{pos.get('point_id', 0)}")
            results.append(result)
        return results

    def generate_report(self, results: List[Dict[str, Any]], output_path: Optional[Path] = None) -> str:
        """Generate a verification report.

        Args:
            results: List of verification results
            output_path: Optional path to save report

        Returns:
            Report as string
        """
        total = len(results)
        successful = sum(1 for r in results if r.get("success", False))
        failed = total - successful

        lines = [
            "# Spotlight Alignment Verification Report",
            "",
            f"Total points: {total}",
            f"Successful: {successful}",
            f"Failed: {failed}",
            f"Success rate: {100 * successful / total:.1f}%" if total > 0 else "N/A",
            "",
            "## Results",
            "",
        ]

        for r in results:
            if r.get("success", False):
                name = r.get('name', f'Point {r.get("point_id", 0)}')
                target = r['target']
                lines.append(
                    f"- ✅ **{name}** "
                    f"({target['x']:.2f}, {target['y']:.2f}, {target['z']:.2f}): "
                    f"pan={r['pan_deg']:.2f}°, tilt={r['tilt_deg']:.2f}°, "
                    f"distance={r.get('distance_m', 0):.2f}m"
                )
            else:
                name = r.get('name', f'Point {r.get("point_id", 0)}')
                target = r['target']
                lines.append(
                    f"- ❌ **{name}** "
                    f"({target['x']:.2f}, {target['y']:.2f}, {target['z']:.2f}): "
                    f"ERROR: {r.get('error', 'Unknown')}"
                )

        report = "\n".join(lines)

        if output_path:
            output_path.write_text(report)
            logger.info(f"Report saved to {output_path}")

        return report


def main():
    parser = argparse.ArgumentParser(description="Spotlight Alignment Verification Tool")
    parser.add_argument(
        "--config",
        default="config/spotlight_config.json",
        help="Path to spotlight configuration JSON",
    )
    parser.add_argument(
        "--output",
        help="Output file for verification report (Markdown)",
    )
    parser.add_argument(
        "--grid",
        action="store_true",
        help="Run grid verification instead of known positions",
    )
    parser.add_argument(
        "--x-min", type=float, default=-5.0, help="Grid X minimum (meters)"
    )
    parser.add_argument(
        "--x-max", type=float, default=5.0, help="Grid X maximum (meters)"
    )
    parser.add_argument(
        "--y-min", type=float, default=-5.0, help="Grid Y minimum (meters)"
    )
    parser.add_argument(
        "--y-max", type=float, default=5.0, help="Grid Y maximum (meters)"
    )
    parser.add_argument(
        "--z", type=float, default=1.75, help="Height (meters)"
    )
    parser.add_argument(
        "--step", type=float, default=1.0, help="Grid step (meters)"
    )
    parser.add_argument(
        "--positions",
        help="JSON file with known positions to verify",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 1

    verifier = SpotlightVerification(str(config_path))

    try:
        if args.grid:
            logger.info(f"Running grid verification: X=[{args.x_min}, {args.x_max}], Y=[{args.y_min}, {args.y_max}], Z={args.z}, step={args.step}")
            results = verifier.run_grid_verification(
                (args.x_min, args.x_max),
                (args.y_min, args.y_max),
                args.z,
                args.step,
            )
        elif args.positions:
            positions_path = Path(args.positions)
            with open(positions_path) as f:
                positions = json.load(f)
            logger.info(f"Verifying {len(positions)} known positions")
            results = verifier.verify_known_positions(positions)
        else:
            # Default: verify stage corners and center
            logger.info("No positions specified, verifying stage corners and center")
            positions = [
                {"name": "Stage Center", "x": 0.0, "y": 0.0, "z": args.z},
                {"name": "Front Left", "x": -5.0, "y": -4.0, "z": args.z},
                {"name": "Front Right", "x": 5.0, "y": -4.0, "z": args.z},
                {"name": "Back Left", "x": -5.0, "y": 4.0, "z": args.z},
                {"name": "Back Right", "x": 5.0, "y": 4.0, "z": args.z},
            ]
            results = verifier.verify_known_positions(positions)

        # Generate report
        output_path = Path(args.output) if args.output else None
        report = verifier.generate_report(results, output_path)
        print(report)

        # Exit with error code if any failures
        failed = sum(1 for r in results if not r.get("success", False))
        return 1 if failed > 0 else 0

    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
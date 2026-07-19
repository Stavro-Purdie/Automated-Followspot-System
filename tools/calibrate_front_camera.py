#!/usr/bin/env python3
"""
Front Camera Calibration Tool

Uses solvePnP to compute camera extrinsics (rotation_matrix + translation_vector)
from 2D image points (stage corners + reference markers) and known 3D stage positions.

Usage:
    python3 tools/calibrate_front_camera.py --config config/front_array_config.json
    python3 tools/calibrate_front_camera.py --config config/front_array_config.json --verify-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Try to import camera aggregator for live feed
try:
    from control.camera_aggregator import MultiCameraManager
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    logging.warning("Camera aggregator not available; will use static image if provided")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("calibrate_front_camera")


class CalibrationTool:
    """Interactive camera calibration using solvePnP."""

    # Stage corner order: front-left, front-right, back-right, back-left (clockwise from downstage-left)
    STAGE_CORNER_ORDER = [
        "front_left",    # Downstage left (audience left)
        "front_right",   # Downstage right
        "back_right",    # Upstage right
        "back_left",     # Upstage left
    ]

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.camera_manager: Optional[MultiCameraManager] = None
        self.current_frame: Optional[np.ndarray] = None
        self.image_points: List[Tuple[int, int]] = []  # Clicked pixel coordinates
        self.stage_corners_3d: List[Tuple[float, float, float]] = []
        self.reference_points_3d: List[Tuple[float, float, float]] = []
        self.reference_points_2d: List[Tuple[int, int]] = []
        self.current_step = 0  # 0=stage corners, 1=reference points
        self.window_name = "Front Camera Calibration"
        self.scale_factor = 1.0
        self.display_frame: Optional[np.ndarray] = None

    def _load_config(self) -> Dict:
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def _save_config(self) -> None:
        self.config["last_updated"] = datetime.now().isoformat()
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Config saved to {self.config_path}")

    def start_camera(self) -> bool:
        """Initialize camera connection."""
        if not CAMERA_AVAILABLE:
            logger.error("Camera aggregator not available")
            return False

        cam_config = self.config["camera"]["front_camera"]
        server_url = cam_config.get("server_url", "http://192.168.0.50:8000")

        # Create a minimal config for single camera
        temp_config = {
            "grid_config": {"cameras_per_row": 1, "total_cameras": 1, "cell_width": 1280, "cell_height": 960, "auto_arrange": True},
            "cameras": [{
                "server_url": server_url,
                "crop_rect": [0, 0, 0, 0],
                "position": [0, 0],
                "camera_id": "front",
                "enabled": True
            }]
        }

        # Save temp config
        temp_path = "/tmp/front_cam_config.json"
        with open(temp_path, 'w') as f:
            json.dump(temp_config, f)

        try:
            self.camera_manager = MultiCameraManager(temp_config, demo_mode=False)
            self.camera_manager.init_demo_mode = lambda: None  # Disable demo
            logger.info(f"Connecting to camera at {server_url}...")
            return True
        except Exception as e:
            logger.error(f"Failed to start camera: {e}")
            return False

    def get_frame(self) -> Optional[np.ndarray]:
        """Get latest frame from camera."""
        if self.camera_manager:
            composite = self.camera_manager.create_composite_frame()
            if composite is not None:
                return composite
        return None

    def run_calibration(self, use_static_image: str = None) -> bool:
        """Main calibration workflow."""
        # Try to get live frame, fallback to static image
        if use_static_image:
            self.current_frame = cv2.imread(use_static_image)
            if self.current_frame is None:
                logger.error(f"Could not load static image: {use_static_image}")
                return False
            logger.info(f"Loaded static image: {use_static_image}")
        elif self.camera_manager:
            logger.info("Waiting for camera frame...")
            for _ in range(30):
                frame = self.get_frame()
                if frame is not None:
                    self.current_frame = frame
                    break
                time.sleep(0.1)
            if self.current_frame is None:
                logger.error("No frame received from camera")
                return False
        else:
            logger.error("No camera and no static image provided")
            return False

        logger.info(f"Frame shape: {self.current_frame.shape}")

        # Calculate display scale
        h, w = self.current_frame.shape[:2]
        max_display = 1200
        self.scale_factor = min(1.0, max_display / max(w, h))
        display_w = int(w * self.scale_factor)
        display_h = int(h * self.scale_factor)

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, display_w, display_h + 100)  # Extra space for instructions
        cv2.setMouseCallback(self.window_name, self._on_mouse_click)

        self._update_display()
        self._print_instructions()

        # Main loop
        while True:
            key = cv2.waitKey(100) & 0xFF
            if key == ord('q') or key == 27:  # ESC
                logger.info("Calibration cancelled")
                return False
            elif key == ord('u'):  # Undo last point
                self._undo_last_point()
            elif key == ord('r'):  # Reset
                self._reset_calibration()
            elif key == ord('s'):  # Solve
                if self._solve_and_save():
                    return True
            elif key == ord('v'):  # Verify
                self._verify_calibration()

            # Update display periodically
            if self.camera_manager:
                frame = self.get_frame()
                if frame is not None:
                    self.current_frame = frame
                    self._update_display()

        return False

    def _print_instructions(self) -> None:
        print("\n" + "="*60)
        print("FRONT CAMERA CALIBRATION")
        print("="*60)
        print("STEP 1: Click 4 STAGE CORNERS in order:")
        print("  1. Front-Left (Downstage Left - audience left)")
        print("  2. Front-Right (Downstage Right)")
        print("  3. Back-Right (Upstage Right)")
        print("  4. Back-Left (Upstage Left)")
        print()
        print("STEP 2: Click 3+ REFERENCE POINTS (known stage positions)")
        print("  - Click on a visible marker/tape on stage")
        print("  - Enter X,Y,Z in meters when prompted")
        print()
        print("KEYS:")
        print("  u = Undo last point")
        print("  r = Reset all points")
        print("  s = Solve PnP and save calibration")
        print("  v = Verify current calibration (reprojection)")
        print("  q/ESC = Quit without saving")
        print("="*60)

    def _on_mouse_click(self, event: int, x: int, y: int, flags: int, param: Any) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        # Convert display coordinates to original frame coordinates
        orig_x = int(x / self.scale_factor)
        orig_y = int(y / self.scale_factor)

        h, w = self.current_frame.shape[:2]
        orig_x = max(0, min(w - 1, orig_x))
        orig_y = max(0, min(h - 1, orig_y))

        if self.current_step == 0:
            # Stage corners
            if len(self.image_points) < 4:
                self.image_points.append((orig_x, orig_y))
                corner_name = self.STAGE_CORNER_ORDER[len(self.image_points) - 1]
                logger.info(f"Stage corner {len(self.image_points)}/4 ({corner_name}): ({orig_x}, {orig_y})")
                self._update_display()

                if len(self.image_points) == 4:
                    logger.info("All 4 stage corners collected. Now click reference points.")
                    self.current_step = 1
                    self._print_reference_instructions()
        else:
            # Reference points
            self.reference_points_2d.append((orig_x, orig_y))
            idx = len(self.reference_points_2d)
            logger.info(f"Reference point {idx} image coords: ({orig_x}, {orig_y})")

            # Prompt for 3D coordinates
            try:
                coords_str = input(f"  Enter X,Y,Z (meters) for reference point {idx}: ").strip()
                if not coords_str:
                    self.reference_points_2d.pop()
                    return
                x3d, y3d, z3d = map(float, coords_str.replace(',', ' ').split())
                self.reference_points_3d.append((x3d, y3d, z3d))
                logger.info(f"  -> Stage coords: ({x3d:.3f}, {y3d:.3f}, {z3d:.3f})")
            except ValueError:
                logger.error("Invalid format. Use: X Y Z or X,Y,Z")
                self.reference_points_2d.pop()
            except EOFError:
                logger.error("Input cancelled")
                self.reference_points_2d.pop()

            self._update_display()

    def _print_reference_instructions(self) -> None:
        print("\n" + "-"*60)
        print("STEP 2: Click REFERENCE POINTS (minimum 3, more is better)")
        print("  - Click on visible markers/spike tape on stage")
        print("  - Enter X,Y,Z in meters when prompted")
        print("  - Stage origin (0,0,0) is typically front-center or front-left")
        print("-"*60)

    def _update_display(self) -> None:
        if self.current_frame is None:
            return

        display = self.current_frame.copy()

        # Draw stage corners
        for i, pt in enumerate(self.image_points):
            disp_pt = (int(pt[0] * self.scale_factor), int(pt[1] * self.scale_factor))
            cv2.circle(display, disp_pt, 8, (0, 255, 255), -1)
            cv2.circle(display, disp_pt, 10, (0, 0, 0), 2)
            label = f"{i+1}:{self.STAGE_CORNER_ORDER[i][:2].upper()}"
            cv2.putText(display, label, (disp_pt[0] + 12, disp_pt[1] - 12),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Draw lines between stage corners
        if len(self.image_points) >= 2:
            for i in range(len(self.image_points) - 1):
                pt1 = (int(self.image_points[i][0] * self.scale_factor), int(self.image_points[i][1] * self.scale_factor))
                pt2 = (int(self.image_points[i+1][0] * self.scale_factor), int(self.image_points[i+1][1] * self.scale_factor))
                cv2.line(display, pt1, pt2, (0, 255, 255), 2)
            # Close the rectangle
            if len(self.image_points) == 4:
                pt1 = (int(self.image_points[3][0] * self.scale_factor), int(self.image_points[3][1] * self.scale_factor))
                pt2 = (int(self.image_points[0][0] * self.scale_factor), int(self.image_points[0][1] * self.scale_factor))
                cv2.line(display, pt1, pt2, (0, 255, 255), 2)

        # Draw reference points
        for i, pt in enumerate(self.reference_points_2d):
            disp_pt = (int(pt[0] * self.scale_factor), int(pt[1] * self.scale_factor))
            cv2.circle(display, disp_pt, 8, (255, 0, 255), -1)
            cv2.circle(display, disp_pt, 10, (0, 0, 0), 2)
            cv2.putText(display, f"R{i+1}", (disp_pt[0] + 12, disp_pt[1] - 12),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

        # Add status bar
        status_h = 60
        status_bar = np.zeros((status_h, display.shape[1], 3), dtype=np.uint8)
        if self.current_step == 0:
            msg = f"STEP 1: Click stage corner {len(self.image_points)+1}/4 ({self.STAGE_CORNER_ORDER[len(self.image_points)] if len(self.image_points) < 4 else 'DONE'})"
            color = (0, 255, 255)
        else:
            msg = f"STEP 2: Reference point {len(self.reference_points_2d)+1} (need >=3) | Total: {len(self.reference_points_2d)}"
            color = (255, 0, 255)

        cv2.putText(status_bar, msg, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(status_bar, "Keys: u=undo  r=reset  s=solve  v=verify  q=quit", (10, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        combined = np.vstack([display, status_bar])
        self.display_frame = combined
        cv2.imshow(self.window_name, combined)

    def _undo_last_point(self) -> None:
        if self.current_step == 0 and self.image_points:
            removed = self.image_points.pop()
            logger.info(f"Removed stage corner: {removed}")
        elif self.current_step == 1 and self.reference_points_2d:
            removed_2d = self.reference_points_2d.pop()
            removed_3d = self.reference_points_3d.pop()
            logger.info(f"Removed reference point: {removed_2d} -> {removed_3d}")
        self._update_display()

    def _reset_calibration(self) -> None:
        self.image_points.clear()
        self.reference_points_2d.clear()
        self.reference_points_3d.clear()
        self.current_step = 0
        logger.info("Calibration reset")
        self._update_display()
        self._print_instructions()

    def _solve_and_save(self) -> bool:
        """Run solvePnP and save calibration to config."""
        # Build 3D stage corner points
        stage = self.config["stage_geometry"]
        w = stage["width"]
        d = stage["depth"]
        origin = stage["origin"]

        # Stage corners in stage coordinates (clockwise from front-left)
        # Front-left, Front-right, Back-right, Back-left
        self.stage_corners_3d = [
            [-w/2, -d/2, 0.0],  # Front-left
            [w/2, -d/2, 0.0],   # Front-right
            [w/2, d/2, 0.0],    # Back-right
            [-w/2, d/2, 0.0],   # Back-left
        ]

        # Combine all points for solvePnP
        object_points = np.array(self.stage_corners_3d + self.reference_points_3d, dtype=np.float32)
        image_points = np.array(self.image_points + self.reference_points_2d, dtype=np.float32)

        if len(object_points) < 6:
            logger.error(f"Need at least 6 points total (4 corners + 2 refs), got {len(object_points)}")
            return False

        # Camera matrix and distortion
        cam_cfg = self.config["camera"]["front_camera"]
        camera_matrix = np.array(cam_cfg["calibration_matrix"], dtype=np.float32)
        dist_coeffs = np.array(cam_cfg["distortion_coeffs"], dtype=np.float32)

        logger.info(f"Running solvePnP with {len(object_points)} points...")
        logger.info(f"Camera matrix:\n{camera_matrix}")
        logger.info(f"Distortion coeffs: {dist_coeffs}")

        success, rvec, tvec = cv2.solvePnP(
            object_points, image_points,
            camera_matrix, dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            logger.error("solvePnP failed")
            return False

        # Convert rotation vector to rotation matrix
        rotation_matrix, _ = cv2.Rodrigues(rvec)
        translation_vector = tvec.flatten()

        logger.info(f"Rotation vector (deg): {np.degrees(rvec.flatten())}")
        logger.info(f"Translation vector (m): {translation_vector}")
        logger.info(f"Rotation matrix:\n{rotation_matrix}")

        # Calculate reprojection error
        projected_points, _ = cv2.projectPoints(
            object_points, rvec, tvec, camera_matrix, dist_coeffs
        )
        projected_points = projected_points.reshape(-1, 2)
        errors = np.linalg.norm(projected_points - image_points, axis=1)
        mean_error = np.mean(errors)
        max_error = np.max(errors)

        logger.info(f"Reprojection errors: mean={mean_error:.2f}px, max={max_error:.2f}px")
        for i, err in enumerate(errors):
            pt_type = "corner" if i < 4 else f"ref_{i-3}"
            logger.info(f"  {pt_type}: {err:.2f}px")

        if max_error > 5.0:
            logger.warning(f"Max reprojection error {max_error:.2f}px > 5px. Calibration may be inaccurate.")

        # Update config
        cam_cfg["extrinsics"]["rotation_matrix"] = rotation_matrix.tolist()
        cam_cfg["extrinsics"]["translation_vector"] = translation_vector.tolist()
        cam_cfg["extrinsics"]["calibrated"] = True
        cam_cfg["extrinsics"]["calibration_date"] = datetime.now().isoformat()
        cam_cfg["extrinsics"]["reprojection_error_mean_px"] = float(mean_error)
        cam_cfg["extrinsics"]["reprojection_error_max_px"] = float(max_error)

        # Also update calibration section
        self.config["calibration"]["stage_corners"] = [list(p) for p in self.image_points]
        self.config["calibration"]["reference_points_2d"] = [list(p) for p in self.reference_points_2d]
        self.config["calibration"]["reference_points_3d"] = [list(p) for p in self.reference_points_3d]
        self.config["calibration"]["calibrated"] = True
        self.config["calibration"]["calibration_date"] = datetime.now().isoformat()

        self._save_config()
        logger.info("Calibration saved successfully!")
        return True

    def _verify_calibration(self) -> None:
        """Verify current calibration by projecting known points."""
        cam_cfg = self.config["camera"]["front_camera"]
        extrinsics = cam_cfg.get("extrinsics", {})

        if not extrinsics.get("calibrated", False):
            logger.warning("No calibration found in config")
            return

        rotation_matrix = np.array(extrinsics["rotation_matrix"], dtype=np.float32)
        translation_vector = np.array(extrinsics["translation_vector"], dtype=np.float32)
        camera_matrix = np.array(cam_cfg["calibration_matrix"], dtype=np.float32)
        dist_coeffs = np.array(cam_cfg["distortion_coeffs"], dtype=np.float32)

        # Convert back to rvec for projectPoints
        rvec, _ = cv2.Rodrigues(rotation_matrix)
        tvec = translation_vector.reshape(3, 1)

        # Project stage corners
        stage = self.config["stage_geometry"]
        w, d = stage["width"], stage["depth"]
        corners_3d = np.array([
            [-w/2, -d/2, 0.0],
            [w/2, -d/2, 0.0],
            [w/2, d/2, 0.0],
            [-w/2, d/2, 0.0],
        ], dtype=np.float32)

        projected, _ = cv2.projectPoints(corners_3d, rvec, tvec, camera_matrix, dist_coeffs)
        projected = projected.reshape(-1, 2)

        logger.info("Calibration verification - projected stage corners:")
        for i, pt in enumerate(projected):
            logger.info(f"  Corner {i}: ({pt[0]:.1f}, {pt[1]:.1f})")

        # Draw on current frame
        if self.current_frame is not None:
            vis = self.current_frame.copy()
            for i, pt in enumerate(projected):
                cv2.circle(vis, (int(pt[0]), int(pt[1])), 10, (0, 255, 0), 2)
                cv2.putText(vis, f"C{i}", (int(pt[0])+15, int(pt[1])-15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            # Also draw detected corners if any
            for i, pt in enumerate(self.image_points):
                cv2.circle(vis, pt, 5, (0, 0, 255), -1)
            cv2.imshow("Verification", vis)
            cv2.waitKey(0)
            cv2.destroyWindow("Verification")


def main():
    parser = argparse.ArgumentParser(description="Front Camera Calibration Tool")
    parser.add_argument("--config", default="config/front_array_config.json",
                       help="Path to front_array_config.json")
    parser.add_argument("--static-image", help="Use static image instead of live camera")
    parser.add_argument("--verify-only", action="store_true",
                       help="Only verify existing calibration")
    parser.add_argument("--camera-url", help="Camera server URL (overrides config)")

    args = parser.parse_args()

    tool = CalibrationTool(args.config)

    if args.camera_url:
        tool.config["camera"]["front_camera"]["server_url"] = args.camera_url

    if args.verify_only:
        # Load existing calibration and verify
        cam_cfg = tool.config["camera"]["front_camera"]
        if not cam_cfg.get("extrinsics", {}).get("calibrated", False):
            logger.error("No calibration found to verify")
            return 1
        # Need a frame to verify against
        if args.static_image:
            tool.current_frame = cv2.imread(args.static_image)
            tool._verify_calibration()
            return 0
        else:
            logger.error("--verify-only requires --static-image")
            return 1

    if not tool.start_camera() and not args.static_image:
        logger.warning("Could not start camera, will try static image if provided")

    success = tool.run_calibration(use_static_image=args.static_image)

    cv2.destroyAllWindows()

    if success:
        logger.info("Calibration complete!")
        return 0
    else:
        logger.info("Calibration cancelled or failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
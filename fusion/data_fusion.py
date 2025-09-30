#!/usr/bin/env python3
"""
Data fusion helpers for blending vision tracking with beacon telemetry.

This file glues together two very different data sources, the computer-vision
ReID pipeline that recognises people and the hardware IR beacon network that is
great at spotting precise stage positions.
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Optional, Set
import time
import json
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("data_fusion")

class TrackingSource(Enum):
    """Labels that explain where a position estimate was born."""
    IR_BEACON = "ir_beacon"
    REID_CAMERA = "reid_camera"
    FUSED = "fused"

@dataclass
class Position3D:
    """Describes a point in space and remembers how trustworthy it is."""
    x: float
    y: float
    z: float
    confidence: float
    timestamp: float
    source: TrackingSource
    axis_confidence: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    
    def distance_to(self, other: 'Position3D') -> float:
        """Quick helper for measuring person-to-person separation in metres."""
        return np.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)

@dataclass
class Person:
    """Snapshot of a performer that stitches together camera and beacon clues."""
    id: int
    reid_track_id: Optional[int]
    ir_beacon_id: Optional[int]
    position: Position3D
    velocity: np.ndarray
    reid_confidence: float
    ir_confidence: float
    last_updated: float
    fusion_confidence: float
    axis_confidence: np.ndarray = field(default_factory=lambda: np.ones(3))

class DataFusion:
    """Orchestrates the reconciliation between camera tracks and IR beacons."""
    
    def __init__(self, config: Dict):
        """Load knobs from config and set the stage for fusion to run.

        Args:
            config: Reid configuration dictionary. We expect this to contain a
                ``data_fusion`` section (tuning thresholds and blending weights)
                and ``stage_geometry`` (how big the playable area is). Passing
                the whole config keeps the call-site simple and mirrors how the
                rest of the control stack loads settings.
        """
        self.fusion_config = config["data_fusion"]
        self.stage_config = config["stage_geometry"]
        camera_cfg = config.get("camera", {}).get("front_camera", {})
        extrinsics_cfg = camera_cfg.get("extrinsics", {})
        depth_cfg = camera_cfg.get("depth", {})

        # Camera calibration parameters
        self.camera_intrinsics = np.array(
            camera_cfg.get("calibration_matrix", np.eye(3)), dtype=float
        )
        try:
            self.camera_intrinsics_inv = np.linalg.inv(self.camera_intrinsics)
        except np.linalg.LinAlgError:
            logger.warning("Camera intrinsics not invertible; using identity transform")
            self.camera_intrinsics = np.eye(3)
            self.camera_intrinsics_inv = np.eye(3)

        self.camera_rotation = np.array(
            extrinsics_cfg.get("rotation_matrix", np.eye(3)), dtype=float
        )
        self.camera_translation = np.array(
            extrinsics_cfg.get("translation_vector", [0.0, 0.0, 0.0]), dtype=float
        )
        self.camera_reference_frame = extrinsics_cfg.get("reference_frame", "stage")
        self.camera_calibrated = bool(extrinsics_cfg.get("calibrated", False))

        # Depth handling parameters
        self.depth_enabled = bool(depth_cfg.get("enabled", True))
        self.depth_confidence_floor = float(depth_cfg.get("confidence_floor", 0.4))
        self.depth_fallback_height = float(depth_cfg.get("fallback_height", 1.75))
        self.depth_smoothing_window = int(depth_cfg.get("smoothing_window", 5))
        self._depth_history: Dict[int, List[float]] = {}
        
        # Fusion parameters
        self.position_match_threshold = self.fusion_config["position_match_threshold"]
        self.time_sync_tolerance = self.fusion_config["time_sync_tolerance"]
        self.reid_weight = self.fusion_config["reid_weight"]
        self.ir_weight = self.fusion_config["ir_weight"]
        self.fusion_memory_time = self.fusion_config["fusion_memory_time"]
        
        # Stage bounds for validation
        # A friendly guard-rail that stops us from reporting ghosts far outside
        # the actual stage. The values are mirrored around the centre of the
        # stage so we can validate positions with one compact helper later on.
        self.stage_bounds = {
            "x_min": -self.stage_config["width"] / 2,
            "x_max": self.stage_config["width"] / 2,
            "y_min": -self.stage_config["depth"] / 2,
            "y_max": self.stage_config["depth"] / 2,
            "z_min": 0.0,
            "z_max": 3.0  # Maximum person height
        }
        
        # Fused persons storage
        self.persons: Dict[int, Person] = {}
        self.next_person_id = 1
        
        # Matching history
        self.reid_ir_associations: Dict[int, int] = {}  # reid_track_id -> ir_beacon_id
        self.ir_reid_associations: Dict[int, int] = {}  # ir_beacon_id -> reid_track_id
        
        # Performance tracking
        self.fusion_stats = {
            "total_fusions": 0,
            "reid_only_persons": 0,
            "ir_only_persons": 0,
            "fused_persons": 0,
            "position_matches": 0,
            "position_mismatches": 0
        }
        
        logger.info("DataFusion initialized")
    
    def update_fusion(self, reid_tracks: Dict[int, Dict], ir_beacons: List[Dict],
                      current_timestamp: float) -> Dict[int, Person]:
        """Blend the latest ReID and IR observations into unified person records.

        The flow looks like this:

        1. Normalise both input streams into the shared :class:`Position3D`
           representation so downstream code does not worry about origin format.
        2. Pair up ReID tracks with nearby beacons (when available) using a
           simple distance matrix. Think of this as speed-dating for sensors.
        3. Update or create :class:`Person` objects with fused coordinates,
           keeping velocity estimates fresh and pruning stale entries.

        Args:
            reid_tracks: Raw ReID tracker output keyed by track id.
            ir_beacons: List of IR beacon detections in stage space.
            current_timestamp: Wall-clock timestamp used to age the tracks.

        Returns:
            Dictionary ``person_id -> Person`` describing everyone we currently
            believe is on stage.
        """
        start_time = time.time()
        
        # Convert inputs to standardized format
        reid_positions = self._extract_reid_positions(reid_tracks, current_timestamp)
        ir_positions = self._extract_ir_positions(ir_beacons, current_timestamp)
        
        # Match ReID tracks to IR beacons
        matches = self._match_reid_to_ir(reid_positions, ir_positions)
        
        # Update existing persons and create new ones
        self._update_persons(reid_positions, ir_positions, matches, current_timestamp)
        
        # Clean up old persons
        self._cleanup_old_persons(current_timestamp)
        
        # Update statistics
        self._update_fusion_stats()
        
        processing_time = time.time() - start_time
        logger.debug(f"Data fusion update took {processing_time*1000:.1f}ms")
        
        return dict(self.persons)
    
    def _extract_reid_positions(self, reid_tracks: Dict[int, Dict],
                                timestamp: float) -> Dict[int, Position3D]:
        """Translate raw ReID tracker output into stage-aware positions.

        The ReID subsystem reports pixel-space positions and a confidence score
        for each active track. We convert those into stage coordinates (meters)
        via :meth:`_camera_to_stage_coordinates` so they can be compared against
        the IR data. Tracks flagged as inactive or missing positional history are
        skipped gracefully.
        """
        positions = {}
        
        for track_id, track in reid_tracks.items():
            if track["status"] != "active" or not track["positions"]:
                continue
                
            # Get latest position
            latest_pos = track["positions"][-1]  # [x, y, z] in camera coordinates
            
            # Convert to stage coordinates (this would need calibration in real system)
            stage_pos = self._camera_to_stage_coordinates(latest_pos)
            depth_history = self._depth_history.setdefault(track_id, [])
            depth_history.append(float(stage_pos[2]))
            if len(depth_history) > self.depth_smoothing_window:
                depth_history.pop(0)
            stage_pos[2] = float(np.mean(depth_history))

            axis_confidence = (
                float(np.clip(track.get("confidence", 0.5) * 0.5, self.depth_confidence_floor, 1.0)),
                float(np.clip(track.get("confidence", 0.5) * 0.5, self.depth_confidence_floor, 1.0)),
                float(np.clip(track.get("confidence", 0.5), self.depth_confidence_floor, 1.0))
            )
            
            positions[track_id] = Position3D(
                x=stage_pos[0],
                y=stage_pos[1], 
                z=stage_pos[2],
                confidence=track["confidence"],
                timestamp=track["last_update"],
                source=TrackingSource.REID_CAMERA,
                axis_confidence=axis_confidence
            )
        
        # Clean up depth history for retired tracks
        for track_id in list(self._depth_history.keys()):
            if track_id not in positions:
                del self._depth_history[track_id]
        
        return positions
    
    def _extract_ir_positions(self, ir_beacons: List[Dict],
                              timestamp: float) -> Dict[int, Position3D]:
        """Wrap IR telemetry in :class:`Position3D` objects for consistency.

        IR beacons already speak the stage's language (``x`` and ``y`` in
        metres), but they usually cannot measure height. We keep things simple
        by borrowing a sensible default height unless the beacon payload says
        otherwise. Each beacon is tagged with the acquisition timestamp so we
        can reason about staleness later while pruning tracks.
        """
        positions = {}
        
        for i, beacon in enumerate(ir_beacons):
            beacon_id = beacon.get("id", i)
            
            # IR system provides accurate X, Y but needs Z from ReID
            positions[beacon_id] = Position3D(
                x=beacon["x"],
                y=beacon["y"],
                z=beacon.get("z", 1.75),  # Default person height if not available
                confidence=beacon.get("confidence", 0.9),  # IR typically high confidence
                timestamp=timestamp,
                source=TrackingSource.IR_BEACON,
                axis_confidence=(
                    float(np.clip(beacon.get("confidence", 0.9), 0.0, 1.0)),
                    float(np.clip(beacon.get("confidence", 0.9), 0.0, 1.0)),
                    0.2
                )
            )
        
        return positions
    
    def _camera_to_stage_coordinates(self, camera_pos: np.ndarray) -> np.ndarray:
        """Project a ReID track from camera space into stage coordinates."""

        if camera_pos is None or len(camera_pos) < 3:
            return np.array([0.0, 0.0, self.depth_fallback_height])

        x_px, y_px, depth = float(camera_pos[0]), float(camera_pos[1]), float(camera_pos[2])

        if depth <= 0 or not np.isfinite(depth):
            depth = self.depth_fallback_height

        if self.camera_calibrated:
            pixel_h = np.array([x_px, y_px, 1.0], dtype=float)
            camera_point = depth * (self.camera_intrinsics_inv @ pixel_h)
            stage_point = self.camera_rotation @ camera_point + self.camera_translation
            stage_point[2] = np.clip(stage_point[2], self.stage_bounds["z_min"], self.stage_bounds["z_max"])
            stage_point[0] = np.clip(stage_point[0], self.stage_bounds["x_min"], self.stage_bounds["x_max"])
            stage_point[1] = np.clip(stage_point[1], self.stage_bounds["y_min"], self.stage_bounds["y_max"])
            return stage_point

        # Fallback heuristic scaling if calibration is unavailable
        stage_x = np.clip(x_px * 0.01, self.stage_bounds["x_min"], self.stage_bounds["x_max"])
        stage_y = np.clip(y_px * 0.01, self.stage_bounds["y_min"], self.stage_bounds["y_max"])
        stage_z = np.clip(depth, self.stage_bounds["z_min"], self.stage_bounds["z_max"])
        return np.array([stage_x, stage_y, stage_z])
    
    def _match_reid_to_ir(self, reid_positions: Dict[int, Position3D],
                          ir_positions: Dict[int, Position3D]) -> List[Tuple[int, int]]:
        """Pair up ReID tracks with IR beacons by looking for the closest dance partner.

        We build a tiny distance matrix of X/Y deltas, then greedily pick the
        smallest remaining pair until everyone is either matched or outside the
        configured proximity threshold. It is deliberately simple so we can
        debug by eye—when this needs to scale to dozens of performers we can
        swap in the Hungarian algorithm without touching the rest of the code.

        Returns:
            A list of ``(reid_track_id, ir_beacon_id)`` tuples describing the
            best matches seen in this frame.
        """
        matches = []
        
        if not reid_positions or not ir_positions:
            return matches
        
        # Build distance matrix so we can compare every ReID track against every
        # beacon in one go. This remains tiny in the current theatre setup.
        reid_ids = list(reid_positions.keys())
        ir_ids = list(ir_positions.keys())
        
        distance_matrix = np.zeros((len(reid_ids), len(ir_ids)))
        
        for i, reid_id in enumerate(reid_ids):
            for j, ir_id in enumerate(ir_ids):
                reid_pos = reid_positions[reid_id]
                ir_pos = ir_positions[ir_id]
                
                # Only consider X, Y distance for matching (Z comes from ReID)
                distance = np.sqrt((reid_pos.x - ir_pos.x)**2 + (reid_pos.y - ir_pos.y)**2)
                distance_matrix[i, j] = distance
        
        # Greedy matching - closest pairs first
        used_reid = set()
        used_ir = set()
        
        while True:
            min_distance = float('inf')
            best_reid_idx, best_ir_idx = -1, -1
            
            for i, reid_id in enumerate(reid_ids):
                if reid_id in used_reid:
                    continue
                for j, ir_id in enumerate(ir_ids):
                    if ir_id in used_ir:
                        continue
                        
                    if distance_matrix[i, j] < min_distance:
                        min_distance = distance_matrix[i, j]
                        best_reid_idx, best_ir_idx = i, j
            
            # Check if match is good enough
            if min_distance > self.position_match_threshold:
                break
                
            # Add match
            reid_id = reid_ids[best_reid_idx]
            ir_id = ir_ids[best_ir_idx]
            matches.append((reid_id, ir_id))
            
            used_reid.add(reid_id)
            used_ir.add(ir_id)
            
            # Update associations
            self.reid_ir_associations[reid_id] = ir_id
            self.ir_reid_associations[ir_id] = reid_id
        
        return matches
    
    def _update_persons(self, reid_positions: Dict[int, Position3D],
                        ir_positions: Dict[int, Position3D],
                        matches: List[Tuple[int, int]], timestamp: float):
        """Refresh :class:`Person` objects with the latest sensor inputs.

        This routine updates three buckets:

        * "Fused" people where both systems agree on who is who.
        * ReID-only tracks still waiting for an IR confirmation.
        * IR-only hits that have yet to be associated with a visual identity.

        Keeping the logic in one place stops subtle drift bugs where one bucket
        forgets to update velocity or timestamps.
        """
        
        # Update matched persons (fused data)
        matched_reid_ids = set()
        matched_ir_ids = set()
        
        for reid_id, ir_id in matches:
            matched_reid_ids.add(reid_id)
            matched_ir_ids.add(ir_id)
            
            reid_pos = reid_positions[reid_id]
            ir_pos = ir_positions[ir_id]
            
            # Find existing person or create new one
            person = self._find_or_create_person(reid_id, ir_id)
            
            # Fuse positions using weighted average
            weight_sum = (self.reid_weight + self.ir_weight)
            fused_x = (reid_pos.x * self.reid_weight + ir_pos.x * self.ir_weight) / weight_sum
            fused_y = (reid_pos.y * self.reid_weight + ir_pos.y * self.ir_weight) / weight_sum
            fused_z = reid_pos.z  # ReID provides Z, IR typically doesn't
            
            # Combined confidence gives us a legible number to sort and filter on
            fusion_confidence = (reid_pos.confidence * self.reid_weight + 
                               ir_pos.confidence * self.ir_weight) / weight_sum

            fused_axis_conf = np.array([
                (reid_pos.axis_confidence[0] * self.reid_weight + ir_pos.axis_confidence[0] * self.ir_weight) / weight_sum,
                (reid_pos.axis_confidence[1] * self.reid_weight + ir_pos.axis_confidence[1] * self.ir_weight) / weight_sum,
                reid_pos.axis_confidence[2]
            ])
            fused_axis_conf = np.clip(fused_axis_conf, 0.0, 1.0)
            
            # Update person
            old_pos = np.array([person.position.x, person.position.y, person.position.z])
            new_pos = np.array([fused_x, fused_y, fused_z])
            
            # Calculate velocity
            dt = timestamp - person.last_updated
            if dt > 0:
                person.velocity = (new_pos - old_pos) / dt
            
            person.position = Position3D(
                x=fused_x, y=fused_y, z=fused_z,
                confidence=fusion_confidence,
                timestamp=timestamp,
                source=TrackingSource.FUSED,
                axis_confidence=tuple(fused_axis_conf.tolist())
            )
            person.reid_confidence = reid_pos.confidence
            person.ir_confidence = ir_pos.confidence
            person.fusion_confidence = fusion_confidence
            person.last_updated = timestamp
            person.axis_confidence = fused_axis_conf
        
        # Update ReID-only persons
        for reid_id, reid_pos in reid_positions.items():
            if reid_id not in matched_reid_ids:
                person = self._find_or_create_person(reid_id, None)
                
                old_pos = np.array([person.position.x, person.position.y, person.position.z])
                new_pos = np.array([reid_pos.x, reid_pos.y, reid_pos.z])
                
                dt = timestamp - person.last_updated
                if dt > 0:
                    person.velocity = (new_pos - old_pos) / dt
                
                person.position = reid_pos
                person.reid_confidence = reid_pos.confidence
                person.fusion_confidence = reid_pos.confidence * 0.7  # Lower confidence without IR
                person.last_updated = timestamp
                person.axis_confidence = np.array(reid_pos.axis_confidence)
        
        # Update IR-only persons  
        for ir_id, ir_pos in ir_positions.items():
            if ir_id not in matched_ir_ids:
                person = self._find_or_create_person(None, ir_id)
                
                old_pos = np.array([person.position.x, person.position.y, person.position.z])
                new_pos = np.array([ir_pos.x, ir_pos.y, ir_pos.z])
                
                dt = timestamp - person.last_updated
                if dt > 0:
                    person.velocity = (new_pos - old_pos) / dt
                
                person.position = ir_pos
                person.ir_confidence = ir_pos.confidence
                person.fusion_confidence = ir_pos.confidence * 0.8  # Good X,Y but no Z
                person.last_updated = timestamp
                person.axis_confidence = np.array(ir_pos.axis_confidence)
    
    def _find_or_create_person(self, reid_id: Optional[int], ir_id: Optional[int]) -> Person:
        """Reuse an existing :class:`Person` if possible or spin up a fresh one.

        Re-using objects preserves velocity and confidence so performers do not
        jitter between identities when sensors briefly disagree. The lookup is
        intentionally linear—our performer counts are tiny and this keeps the
        code easy to reason about.
        """
        
        # Look for existing person with these IDs
        for person in self.persons.values():
            if (reid_id is not None and person.reid_track_id == reid_id) or \
               (ir_id is not None and person.ir_beacon_id == ir_id):
                # Update IDs if needed
                if reid_id is not None:
                    person.reid_track_id = reid_id
                if ir_id is not None:
                    person.ir_beacon_id = ir_id
                return person
        
    # Create new person with placeholders so the caller can populate the
    # meaningful data in one predictable place.
        person_id = self.next_person_id
        self.next_person_id += 1
        
        person = Person(
            id=person_id,
            reid_track_id=reid_id,
            ir_beacon_id=ir_id,
            position=Position3D(0, 0, 0, 0, 0, TrackingSource.FUSED, (0.0, 0.0, 0.0)),
            velocity=np.zeros(3),
            reid_confidence=0.0,
            ir_confidence=0.0,
            last_updated=0.0,
            fusion_confidence=0.0,
            axis_confidence=np.zeros(3)
        )
        
        self.persons[person_id] = person
        return person
    
    def _cleanup_old_persons(self, current_timestamp: float):
        """Prune tracks that have gone stale to avoid following ghosts."""
        persons_to_remove = []
        
        for person_id, person in self.persons.items():
            if current_timestamp - person.last_updated > self.fusion_memory_time:
                persons_to_remove.append(person_id)
        
        for person_id in persons_to_remove:
            del self.persons[person_id]
            logger.debug(f"Removed old person {person_id}")
    
    def _update_fusion_stats(self):
        """Keep counters up to date for dashboards and debugging overlays."""
        self.fusion_stats["total_fusions"] = len(self.persons)
        
        reid_only = sum(1 for p in self.persons.values() 
                       if p.reid_track_id is not None and p.ir_beacon_id is None)
        ir_only = sum(1 for p in self.persons.values() 
                     if p.ir_beacon_id is not None and p.reid_track_id is None)
        fused = sum(1 for p in self.persons.values() 
                   if p.reid_track_id is not None and p.ir_beacon_id is not None)
        
        self.fusion_stats["reid_only_persons"] = reid_only
        self.fusion_stats["ir_only_persons"] = ir_only
        self.fusion_stats["fused_persons"] = fused
    
    def get_person_positions(self) -> List[Dict]:
        """Return a tidy list of people ready to feed the followspot logic.

        We validate positions against stage bounds to avoid reporting junk data
        and sort by confidence so callers can trivially pick the most reliable
        performer when they only need one spotlight.
        """
        positions = []
        
        for person in self.persons.values():
            # Validate position is within stage bounds
            if not self._is_position_valid(person.position):
                continue
                
            positions.append({
                "id": person.id,
                "x": person.position.x,
                "y": person.position.y,
                "z": person.position.z,
                "confidence": person.fusion_confidence,
                "axis_confidence": list(person.position.axis_confidence),
                "velocity": person.velocity.tolist(),
                "reid_id": person.reid_track_id,
                "ir_id": person.ir_beacon_id,
                "source": person.position.source.value,
                "timestamp": person.position.timestamp,
                "updated_at": person.last_updated
            })
        
        # Sort by confidence (highest first)
        positions.sort(key=lambda x: x["confidence"], reverse=True)
        return positions
    
    def _is_position_valid(self, position: Position3D) -> bool:
        """Double-check a position lives within the expected stage envelope."""
        return (self.stage_bounds["x_min"] <= position.x <= self.stage_bounds["x_max"] and
                self.stage_bounds["y_min"] <= position.y <= self.stage_bounds["y_max"] and
                self.stage_bounds["z_min"] <= position.z <= self.stage_bounds["z_max"])
    
    def get_fusion_stats(self) -> Dict:
        """Expose our running counters for UI panels and logging."""
        return dict(self.fusion_stats)
    
    def calibrate_coordinate_systems(self, calibration_points: List[Dict]):
        """Placeholder for the future calibration workflow.

        In production we will map camera pixels to stage metres using measured
        correspondences. For now we log the intent so integrators can see when
        calibration would have been triggered.
        """
        # This would implement camera calibration in a real system. Leaving a
        # breadcrumb here helps me understand why nothing happens
        # yet instead of assuming the call silently failed.
        logger.info(f"Coordinate system calibration requested with {len(calibration_points)} points")
        pass


# Test function
def test_data_fusion():
    """Quick smoke-test that narrates how the fusion logic behaves."""
    print("🧪 Testing Data Fusion...")
    
    # Load config
    with open("config/reid_config.json", 'r') as f:
        config = json.load(f)
    
    fusion = DataFusion(config)
    
    # Create mock ReID tracks
    reid_tracks = {
        1: {
            "status": "active",
            "positions": [np.array([100, 200, 5.0])],  # Camera coordinates
            "confidence": 0.85,
            "last_update": 1.0
        },
        2: {
            "status": "active", 
            "positions": [np.array([300, 400, 8.0])],
            "confidence": 0.90,
            "last_update": 1.0
        }
    }
    
    # Create mock IR beacons (stage coordinates)
    ir_beacons = [
        {"id": 10, "x": 1.0, "y": 2.0, "confidence": 0.95},
        {"id": 11, "x": 3.5, "y": 4.2, "confidence": 0.92}
    ]
    
    # Test fusion
    fused_persons = fusion.update_fusion(reid_tracks, ir_beacons, 1.0)
    
    print(f"Fused persons: {len(fused_persons)}")
    
    # Get position data
    positions = fusion.get_person_positions()
    print(f"\nPerson positions:")
    for pos in positions:
        print(f"  Person {pos['id']}: ({pos['x']:.1f}, {pos['y']:.1f}, {pos['z']:.1f}) "
             f"conf={pos['confidence']:.2f} source={pos['source']}")
    
    # Get statistics
    stats = fusion.get_fusion_stats()
    print(f"\nFusion stats: {stats}")
    
    print("✅ Data fusion test completed")


if __name__ == "__main__":
    test_data_fusion()

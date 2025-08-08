#!/usr/bin/env python3
"""
Data Fusion Module for combining ReID tracking with IR beacon tracking
Merges person tracking with existing IR beacon system for complete 3D coordinates
"""

import numpy as np
import logging
from typing import Dict, List, Tuple, Optional, Set
import time
import json
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("data_fusion")

class TrackingSource(Enum):
    """Source of tracking data"""
    IR_BEACON = "ir_beacon"
    REID_CAMERA = "reid_camera"
    FUSED = "fused"

@dataclass
class Position3D:
    """3D position with metadata"""
    x: float
    y: float
    z: float
    confidence: float
    timestamp: float
    source: TrackingSource
    
    def distance_to(self, other: 'Position3D') -> float:
        """Calculate 3D distance to another position"""
        return np.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)

@dataclass
class Person:
    """Unified person representation"""
    id: int
    reid_track_id: Optional[int]
    ir_beacon_id: Optional[int]
    position: Position3D
    velocity: np.ndarray
    reid_confidence: float
    ir_confidence: float
    last_updated: float
    fusion_confidence: float

class DataFusion:
    """
    Fuses ReID person tracking with IR beacon tracking
    """
    
    def __init__(self, config: Dict):
        """
        Initialize data fusion system
        
        Args:
            config: Reid configuration dictionary
        """
        self.fusion_config = config["data_fusion"]
        self.stage_config = config["stage_geometry"]
        
        # Fusion parameters
        self.position_match_threshold = self.fusion_config["position_match_threshold"]
        self.time_sync_tolerance = self.fusion_config["time_sync_tolerance"]
        self.reid_weight = self.fusion_config["reid_weight"]
        self.ir_weight = self.fusion_config["ir_weight"]
        self.fusion_memory_time = self.fusion_config["fusion_memory_time"]
        
        # Stage bounds for validation
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
        """
        Update fused person tracking with new ReID and IR data
        
        Args:
            reid_tracks: Dictionary of ReID track data
            ir_beacons: List of IR beacon detections with positions
            current_timestamp: Current timestamp
            
        Returns:
            Dictionary of fused person data
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
        """Extract 3D positions from ReID tracks"""
        positions = {}
        
        for track_id, track in reid_tracks.items():
            if track["status"] != "active" or not track["positions"]:
                continue
                
            # Get latest position
            latest_pos = track["positions"][-1]  # [x, y, z] in camera coordinates
            
            # Convert to stage coordinates (this would need calibration in real system)
            stage_pos = self._camera_to_stage_coordinates(latest_pos)
            
            positions[track_id] = Position3D(
                x=stage_pos[0],
                y=stage_pos[1], 
                z=stage_pos[2],
                confidence=track["confidence"],
                timestamp=track["last_update"],
                source=TrackingSource.REID_CAMERA
            )
        
        return positions
    
    def _extract_ir_positions(self, ir_beacons: List[Dict], 
                             timestamp: float) -> Dict[int, Position3D]:
        """Extract 3D positions from IR beacon data"""
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
                source=TrackingSource.IR_BEACON
            )
        
        return positions
    
    def _camera_to_stage_coordinates(self, camera_pos: np.ndarray) -> np.ndarray:
        """
        Convert camera coordinates to stage coordinates
        This would need proper camera calibration in a real system
        """
        # Simplified conversion - in reality this needs camera calibration matrix
        # For now, assume camera is looking down at stage center
        stage_x = camera_pos[0] * 0.01  # Scale camera pixels to meters
        stage_y = camera_pos[1] * 0.01
        stage_z = max(0.0, min(3.0, camera_pos[2]))  # Clamp Z to reasonable range
        
        return np.array([stage_x, stage_y, stage_z])
    
    def _match_reid_to_ir(self, reid_positions: Dict[int, Position3D], 
                         ir_positions: Dict[int, Position3D]) -> List[Tuple[int, int]]:
        """
        Match ReID tracks to IR beacons based on position proximity
        
        Returns:
            List of (reid_track_id, ir_beacon_id) matches
        """
        matches = []
        
        if not reid_positions or not ir_positions:
            return matches
        
        # Build distance matrix
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
        """Update fused person data"""
        
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
            fused_x = (reid_pos.x * self.reid_weight + ir_pos.x * self.ir_weight) / (self.reid_weight + self.ir_weight)
            fused_y = (reid_pos.y * self.reid_weight + ir_pos.y * self.ir_weight) / (self.reid_weight + self.ir_weight)
            fused_z = reid_pos.z  # ReID provides Z, IR typically doesn't
            
            # Combined confidence
            fusion_confidence = (reid_pos.confidence * self.reid_weight + 
                               ir_pos.confidence * self.ir_weight) / (self.reid_weight + self.ir_weight)
            
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
                source=TrackingSource.FUSED
            )
            person.reid_confidence = reid_pos.confidence
            person.ir_confidence = ir_pos.confidence
            person.fusion_confidence = fusion_confidence
            person.last_updated = timestamp
        
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
    
    def _find_or_create_person(self, reid_id: Optional[int], ir_id: Optional[int]) -> Person:
        """Find existing person or create new one"""
        
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
        
        # Create new person
        person_id = self.next_person_id
        self.next_person_id += 1
        
        person = Person(
            id=person_id,
            reid_track_id=reid_id,
            ir_beacon_id=ir_id,
            position=Position3D(0, 0, 0, 0, 0, TrackingSource.FUSED),
            velocity=np.zeros(3),
            reid_confidence=0.0,
            ir_confidence=0.0,
            last_updated=0.0,
            fusion_confidence=0.0
        )
        
        self.persons[person_id] = person
        return person
    
    def _cleanup_old_persons(self, current_timestamp: float):
        """Remove persons not updated recently"""
        persons_to_remove = []
        
        for person_id, person in self.persons.items():
            if current_timestamp - person.last_updated > self.fusion_memory_time:
                persons_to_remove.append(person_id)
        
        for person_id in persons_to_remove:
            del self.persons[person_id]
            logger.debug(f"Removed old person {person_id}")
    
    def _update_fusion_stats(self):
        """Update fusion statistics"""
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
        """Get all person positions in standard format for followspot system"""
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
                "velocity": person.velocity.tolist(),
                "reid_id": person.reid_track_id,
                "ir_id": person.ir_beacon_id,
                "source": person.position.source.value,
                "timestamp": person.position.timestamp
            })
        
        # Sort by confidence (highest first)
        positions.sort(key=lambda x: x["confidence"], reverse=True)
        return positions
    
    def _is_position_valid(self, position: Position3D) -> bool:
        """Check if position is within valid stage bounds"""
        return (self.stage_bounds["x_min"] <= position.x <= self.stage_bounds["x_max"] and
                self.stage_bounds["y_min"] <= position.y <= self.stage_bounds["y_max"] and
                self.stage_bounds["z_min"] <= position.z <= self.stage_bounds["z_max"])
    
    def get_fusion_stats(self) -> Dict:
        """Get fusion statistics"""
        return dict(self.fusion_stats)
    
    def calibrate_coordinate_systems(self, calibration_points: List[Dict]):
        """
        Calibrate coordinate system mapping between cameras and IR system
        This would be called during system setup
        """
        # This would implement camera calibration in a real system
        # For now, just log the calibration request
        logger.info(f"Coordinate system calibration requested with {len(calibration_points)} points")
        pass


# Test function
def test_data_fusion():
    """Test data fusion functionality"""
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

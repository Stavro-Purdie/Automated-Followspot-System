#!/usr/bin/env python3
"""Unit tests for data fusion module."""

import sys
from pathlib import Path
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fusion.data_fusion import DataFusion, Position3D, Person, TrackingSource


class TestPosition3D:
    """Test Position3D dataclass."""
    
    def test_distance_calculation(self):
        """Test 3D distance between positions."""
        pos1 = Position3D(0, 0, 0, 1.0, 0, TrackingSource.FUSED)
        pos2 = Position3D(3, 4, 0, 1.0, 0, TrackingSource.FUSED)
        assert pos1.distance_to(pos2) == 5.0  # 3-4-5 triangle
    
    def test_distance_3d(self):
        """Test 3D distance with Z component."""
        pos1 = Position3D(0, 0, 0, 1.0, 0, TrackingSource.FUSED)
        pos2 = Position3D(1, 1, 1, 1.0, 0, TrackingSource.FUSED)
        expected = np.sqrt(3)
        assert abs(pos1.distance_to(pos2) - expected) < 1e-6


class TestDataFusion:
    """Test DataFusion fusion logic."""
    
    def create_fusion(self):
        """Create DataFusion instance with test config."""
        config = {
            "data_fusion": {
                "position_match_threshold": 1.0,
                "time_sync_tolerance": 0.1,
                "reid_weight": 0.4,
                "ir_weight": 0.6,
                "fusion_memory_time": 3.0,
            },
            "stage_geometry": {
                "width": 10,
                "depth": 8,
                "height": 3,
                "origin": [0, 0, 0]
            },
            "camera": {
                "front_camera": {
                    "calibration_matrix": [[1000, 0, 960], [0, 1000, 540], [0, 0, 1]],
                    "extrinsics": {
                        "rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                        "translation_vector": [0, 0, 0],
                        "reference_frame": "stage",
                        "calibrated": True
                    },
                    "depth": {
                        "enabled": True,
                        "confidence_floor": 0.4,
                        "fallback_height": 1.75,
                        "smoothing_window": 5
                    }
                }
            }
        }
        return DataFusion(config)
    
    def test_reid_only_person(self):
        """Test fusion with ReID track only (no IR)."""
        fusion = self.create_fusion()
        
        reid_tracks = {
            1: {
                "status": "active",
                "positions": [np.array([100, 200, 5.0])],
                "confidence": 0.85,
                "last_update": 1.0
            }
        }
        ir_beacons = []
        
        result = fusion.update_fusion(reid_tracks, ir_beacons, 1.0)
        persons = fusion.get_person_positions()
        
        assert len(persons) == 1
        assert persons[0]["reid_id"] == 1
        assert persons[0]["ir_id"] is None
        assert persons[0]["source"] == "reid_camera"
    
    def test_ir_only_person(self):
        """Test fusion with IR beacon only (no ReID)."""
        fusion = self.create_fusion()
        
        reid_tracks = {}
        ir_beacons = [
            {"id": 10, "x": 1.0, "y": 2.0, "confidence": 0.9}
        ]
        
        result = fusion.update_fusion(reid_tracks, ir_beacons, 1.0)
        persons = fusion.get_person_positions()
        
        assert len(persons) == 1
        assert persons[0]["ir_id"] == 10
        assert persons[0]["reid_id"] is None
        assert persons[0]["source"] == "ir_beacon"
    
    def test_fused_person(self):
        """Test fusion matching ReID track with IR beacon."""
        fusion = self.create_fusion()
        
        # Camera intrinsics: fx=1000, fy=1000, cx=960, cy=540
        # At depth=5m: pixel_x = stage_x * 200 + 960, pixel_y = stage_y * 200 + 540
        # For stage_x=1, stage_y=2: pixel_x=1160, pixel_y=940
        reid_tracks = {
            1: {
                "status": "active",
                "positions": [np.array([1160.0, 940.0, 5.0])],  # Maps to stage ~1m, 2m
                "confidence": 0.85,
                "last_update": 1.0
            }
        }
        ir_beacons = [
            {"id": 10, "x": 1.0, "y": 2.0, "confidence": 0.95}
        ]
        
        result = fusion.update_fusion(reid_tracks, ir_beacons, 1.0)
        persons = fusion.get_person_positions()
        
        assert len(persons) == 1
        assert persons[0]["reid_id"] == 1
        assert persons[0]["ir_id"] == 10
        assert persons[0]["source"] == "fused"
        # Fused position should be weighted average
        assert 0.9 < persons[0]["x"] < 1.1
        assert 1.9 < persons[0]["y"] < 2.1

    def test_position_validation(self):
        """Test stage bounds validation - positions outside bounds should be clamped."""
        fusion = self.create_fusion()
        
        # Person at pixel coords that map to stage position beyond bounds
        # With fx=1000, depth=5: pixel_x = stage_x*200 + 960
        # For stage_x > 5 (max): pixel_x > 5*200 + 960 = 1960
        # Use 10000px -> stage_x = (10000-960)*5/1000 = 45.2m -> clamped to 5m
        reid_tracks = {
            1: {
                "status": "active",
                "positions": [np.array([10000.0, 10000.0, 5.0])],  # Maps to 45m, clamped to 5m
                "confidence": 0.85,
                "last_update": 1.0
            }
        }
        
        result = fusion.update_fusion(reid_tracks, [], 1.0)
        persons = fusion.get_person_positions()
        
        # Should be clamped to stage bounds (5, 4) not rejected
        assert len(persons) == 1
        assert abs(persons[0]["x"] - 5.0) < 0.01
        assert abs(persons[0]["y"] - 4.0) < 0.01
    
    def test_old_person_cleanup(self):
        """Test cleanup of stale persons."""
        fusion = self.create_fusion()
        
        reid_tracks = {
            1: {
                "status": "active",
                "positions": [np.array([1160.0, 940.0, 5.0])],
                "confidence": 0.85,
                "last_update": 1.0
            }
        }
        
        fusion.update_fusion(reid_tracks, [], 1.0)
        assert len(fusion.get_person_positions()) == 1
        
        # Advance time beyond fusion_memory_time (3s)
        fusion.update_fusion({}, [], 5.0)
        assert len(fusion.get_person_positions()) == 0
    
    def test_fusion_weights(self):
        """Test ReID/IR weight blending."""
        fusion = self.create_fusion()
        
        # Create track and beacon at close positions (within match threshold)
        reid_tracks = {
            1: {
                "status": "active",
                "positions": [np.array([1160.0, 940.0, 5.0])],  # Stage ~1.0, 2.0
                "confidence": 0.8,
                "last_update": 1.0
            }
        }
        ir_beacons = [
            {"id": 10, "x": 1.2, "y": 2.2, "confidence": 0.9}  # Close to ReID
        ]
        
        result = fusion.update_fusion(reid_tracks, ir_beacons, 1.0)
        persons = fusion.get_person_positions()
        
        # With reid_weight=0.4, ir_weight=0.6, fused should be closer to IR
        person = persons[0]
        # ReID at 1.0, 2.0; IR at 1.2, 2.2
        # Weighted: 0.4*1.0 + 0.6*1.2 = 1.12, 0.4*2.0 + 0.6*2.2 = 2.12
        assert 1.05 < person["x"] < 1.2
        assert 2.05 < person["y"] < 2.2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
#!/usr/bin/env python3
"""Test configuration and fixtures for automated followspot system."""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line("markers", "slow: mark test as slow")


# Common test constants
MOCK_CAMERA_CONFIG = {
    "grid_config": {
        "cameras_per_row": 2,
        "total_cameras": 4,
        "cell_width": 320,
        "cell_height": 240,
        "auto_arrange": True
    },
    "cameras": [
        {
            "server_url": "http://192.168.1.100:8080",
            "crop_rect": [0, 0, 320, 240],
            "position": [0, 0],
            "camera_id": "cam_1",
            "enabled": True
        },
        {
            "server_url": "http://192.168.1.100:8080",
            "crop_rect": [0, 0, 320, 240],
            "position": [1, 0],
            "camera_id": "cam_2",
            "enabled": True
        }
    ]
}

MOCK_REID_CONFIG = {
    "performance": {
        "target_fps": 15,
        "input_resolution": [1920, 1080],
        "detection_resolution": [1280, 720],
        "max_persons": 10,
        "confidence_threshold": 0.6,
        "nms_threshold": 0.4
    },
    "models": {
        "detector": {
            "name": "yolov8n",
            "device": "cpu",
            "batch_size": 1,
            "model_path": "reid/models/yolov8n.pt"
        },
        "reid": {
            "name": "osnet_x0_5",
            "feature_dim": 512,
            "device": "cpu",
            "model_path": "reid/models/osnet_x0_5_market1501.pth"
        }
    },
    "identities": {
        "gallery_path": "identity_gallery",
        "manifest_path": "identity_gallery/manifest.json",
        "match_threshold": 0.58,
        "reload_interval_sec": 5.0
    },
    "optimization": {
        "use_half_precision": False,
        "tensorrt_optimization": False,
        "detection_interval": 1,
        "reid_interval": 1,
        "max_tracking_age": 30,
        "coreml_reid_enabled": False,
        "coreml_model_path": "",
        "coreml_compute_unit": "ALL",
        "coreml_skip_torch": False
    },
    "camera": {
        "front_camera": {
            "position": [0, 0, 2.5],
            "angle": 0,
            "fov": 60,
            "focal_length": 1000,
            "resolution": [1920, 1080],
            "extrinsics": {
                "rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "translation_vector": [0, 0, 0],
                "reference_frame": "stage",
                "calibrated": False,
                "calibration_date": None
            },
            "depth": {
                "enabled": True,
                "confidence_floor": 0.4,
                "fallback_height": 1.75,
                "smoothing_window": 5
            },
            "calibration_matrix": [[1000, 0, 960], [0, 1000, 540], [0, 0, 1]],
            "distortion_coeffs": [0, 0, 0, 0, 0]
        }
    },
    "stage_geometry": {
        "width": 10,
        "depth": 8,
        "height": 3,
        "origin": [0, 0, 0]
    },
    "tracking": {
        "max_disappeared": 10,
        "max_distance": 100,
        "reid_threshold": 0.7,
        "depth_estimation_method": "geometric",
        "feature_similarity_threshold": 0.6,
        "max_tracking_distance": 2.0,
        "track_memory_frames": 30,
        "new_track_confidence_threshold": 0.5
    },
    "fusion": {
        "ir_reid_max_distance": 0.5,
        "temporal_window": 5,
        "confidence_weights": {
            "ir_tracking": 0.7,
            "reid_matching": 0.3
        }
    },
    "data_fusion": {
        "position_match_threshold": 1.0,
        "time_sync_tolerance": 0.1,
        "reid_weight": 0.4,
        "ir_weight": 0.6,
        "fusion_memory_time": 3.0
    }
}

MOCK_SPOTLIGHT_CONFIG = {
    "rig": {
        "fixture_position_m": [0.0, -5.0, 6.5],
        "stage_origin_m": [0.0, 0.0, 0.0],
        "pan_zero_angle_deg": 0.0,
        "tilt_zero_angle_deg": -35.0,
        "pan_limits_deg": [-120.0, 120.0],
        "tilt_limits_deg": [-120.0, 10.0],
        "smoothing": {
            "pan_alpha": 0.2,
            "tilt_alpha": 0.25
        }
    },
    "dmx": {
        "universe": 1,
        "pan_address": 1,
        "tilt_address": 3,
        "pan_scale": 1.0,
        "tilt_scale": 1.0,
        "transport": "stub",
        "endpoint_url": "http://127.0.0.1:8080/dmx",
        "serial_port": "/dev/ttyAMA0",
        "baud_rate": 115200
    }
}
"""Focused tests for bounded occlusion handling and beacon coordination."""

import numpy as np

from control.beacon_coordinator import BeaconCoordinator
from reid.person_tracker import PersonTracker


def tracker_config():
    return {
        "performance": {"target_fps": 15},
        "tracking": {
            "feature_similarity_threshold": 0.6,
            "max_tracking_distance": 2.0,
            "track_memory_frames": 30,
            "new_track_confidence_threshold": 0.5,
            "max_occlusion_frames": 3,
            "prediction_confidence_floor": 0.2,
        },
    }


def test_tracker_keeps_predicted_track_for_configured_misses():
    tracker = PersonTracker(tracker_config())
    feature = np.ones((1, 4), dtype=np.float32)
    detection = {"bbox": np.array([10.0, 10.0, 20.0, 20.0]), "confidence": 0.9}

    tracker.update_tracks([detection], feature, [4.0], 1.0)
    tracker.update_tracks([], np.empty((0, 4)), [], 1.1)
    track = tracker.tracks[1]

    assert track["status"] == "active"
    assert track["tracking_state"] == "predicted"
    assert track["consecutive_misses"] == 1
    assert track["confidence"] < 0.9

    tracker.update_tracks([], np.empty((0, 4)), [], 1.2)
    tracker.update_tracks([], np.empty((0, 4)), [], 1.3)
    assert tracker.tracks[1]["status"] == "active"

    tracker.update_tracks([], np.empty((0, 4)), [], 1.4)
    assert tracker.tracks[1]["status"] == "lost"


def test_coordinator_ignores_invalid_static_addresses_and_assigns_slots():
    coordinator = BeaconCoordinator({
        "beacons": {
            "good": {"beacon_id": "good", "ip_address": "192.168.1.20"},
            "bad": {"beacon_id": "bad", "ip_address": "192.168.1."},
        }
    })

    assert list(coordinator.nodes) == ["good"]
    assert coordinator.nodes["good"].slot == 0
    assert coordinator.export_config()["good"]["ip_address"] == "192.168.1.20"

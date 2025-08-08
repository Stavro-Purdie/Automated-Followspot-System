#!/usr/bin/env python3
"""
Person Tracking Module for temporal person association
Handles person Re-identification and tracking across frames
"""

import numpy as np
import cv2
import logging
from typing import Dict, List, Tuple, Optional, Set
import time
from collections import defaultdict
import json

logger = logging.getLogger("person_tracker")

class PersonTracker:
    """
    Tracks persons across frames using ReID features and geometric constraints
    """
    
    def __init__(self, config: Dict):
        """
        Initialize person tracker with configuration
        
        Args:
            config: Reid configuration dictionary
        """
        self.tracking_config = config["tracking"]
        self.performance_config = config["performance"]
        
        # Tracking parameters
        self.feature_similarity_threshold = self.tracking_config["feature_similarity_threshold"]
        self.max_tracking_distance = self.tracking_config["max_tracking_distance"]
        self.track_memory_frames = self.tracking_config["track_memory_frames"]
        self.new_track_confidence_threshold = self.tracking_config["new_track_confidence_threshold"]
        
        # Active tracks storage
        self.tracks: Dict[int, Dict] = {}
        self.next_track_id = 1
        self.frame_count = 0
        
        # Performance tracking
        self.processing_times = []
        target_fps = self.performance_config.get("target_fps", 15)
        self.max_processing_time = 1.0 / target_fps  # Target frame time
        
        # Track statistics
        self.track_stats = {
            "total_tracks_created": 0,
            "total_tracks_lost": 0,
            "average_track_length": 0.0,
            "active_tracks": 0
        }
        
        logger.info("PersonTracker initialized")
    
    def update_tracks(self, detections: List[Dict], reid_features: np.ndarray, 
                     depths: List[float], frame_timestamp: float) -> Dict[int, Dict]:
        """
        Update person tracks with new detections
        
        Args:
            detections: List of person detection dictionaries
            reid_features: ReID features for each detection (N x feature_dim)
            depths: Estimated depths for each detection
            frame_timestamp: Current frame timestamp
            
        Returns:
            Dictionary of active tracks with their data
        """
        start_time = time.time()
        self.frame_count += 1
        
        # Match detections to existing tracks
        matched_tracks, unmatched_detections, unmatched_tracks = self._match_detections_to_tracks(
            detections, reid_features, depths, frame_timestamp
        )
        
        # Update matched tracks
        for track_id, detection_idx in matched_tracks:
            self._update_track(track_id, detections[detection_idx], 
                             reid_features[detection_idx], depths[detection_idx], frame_timestamp)
        
        # Create new tracks for unmatched high-confidence detections
        for detection_idx in unmatched_detections:
            detection = detections[detection_idx]
            if detection.get("confidence", 0) >= self.new_track_confidence_threshold:
                self._create_new_track(detection, reid_features[detection_idx], 
                                     depths[detection_idx], frame_timestamp)
        
        # Mark unmatched tracks as lost
        for track_id in unmatched_tracks:
            self._mark_track_lost(track_id, frame_timestamp)
        
        # Clean up old tracks
        self._cleanup_old_tracks(frame_timestamp)
        
        # Update statistics
        self._update_statistics()
        
        # Performance tracking
        processing_time = time.time() - start_time
        self.processing_times.append(processing_time)
        if len(self.processing_times) > 100:
            self.processing_times = self.processing_times[-50:]
        
        return dict(self.tracks)
    
    def _match_detections_to_tracks(self, detections: List[Dict], reid_features: np.ndarray,
                                  depths: List[float], frame_timestamp: float) -> Tuple[List[Tuple], List[int], List[int]]:
        """
        Match current detections to existing tracks using ReID features and geometry
        
        Returns:
            Tuple of (matched_pairs, unmatched_detection_indices, unmatched_track_ids)
        """
        if not detections or len(self.tracks) == 0:
            return [], list(range(len(detections))), []
        
        # Build similarity matrix
        active_track_ids = [tid for tid, track in self.tracks.items() 
                           if track["status"] == "active"]
        
        if not active_track_ids:
            return [], list(range(len(detections))), []
        
        similarity_matrix = np.zeros((len(detections), len(active_track_ids)))
        
        for det_idx, (detection, feature, depth) in enumerate(zip(detections, reid_features, depths)):
            for track_idx, track_id in enumerate(active_track_ids):
                track = self.tracks[track_id]
                
                # Feature similarity
                feature_sim = self._calculate_feature_similarity(feature, track["reid_features"][-1])
                
                # Geometric similarity
                geometric_sim = self._calculate_geometric_similarity(detection, depth, track)
                
                # Temporal consistency
                temporal_sim = self._calculate_temporal_consistency(track, frame_timestamp)
                
                # Combined similarity
                combined_sim = (0.6 * feature_sim + 0.3 * geometric_sim + 0.1 * temporal_sim)
                similarity_matrix[det_idx, track_idx] = combined_sim
        
        # Hungarian assignment (simplified greedy approach for performance)
        matched_pairs = []
        unmatched_detections = set(range(len(detections)))
        unmatched_tracks = set(active_track_ids)
        
        # Greedy matching - highest similarity first
        while True:
            max_sim = 0
            best_det, best_track_idx = -1, -1
            
            for det_idx in unmatched_detections:
                for track_idx, track_id in enumerate(active_track_ids):
                    if track_id in unmatched_tracks and similarity_matrix[det_idx, track_idx] > max_sim:
                        max_sim = similarity_matrix[det_idx, track_idx]
                        best_det, best_track_idx = det_idx, track_idx
            
            if max_sim < self.feature_similarity_threshold:
                break
                
            # Match found
            best_track_id = active_track_ids[best_track_idx]
            matched_pairs.append((best_track_id, best_det))
            unmatched_detections.remove(best_det)
            unmatched_tracks.remove(best_track_id)
        
        return matched_pairs, list(unmatched_detections), list(unmatched_tracks)
    
    def _calculate_feature_similarity(self, feature1: np.ndarray, feature2: np.ndarray) -> float:
        """Calculate cosine similarity between ReID features"""
        if feature1.size == 0 or feature2.size == 0:
            return 0.0
            
        # Normalize features
        feature1_norm = feature1 / (np.linalg.norm(feature1) + 1e-8)
        feature2_norm = feature2 / (np.linalg.norm(feature2) + 1e-8)
        
        # Cosine similarity
        similarity = np.dot(feature1_norm, feature2_norm)
        return max(0.0, float(similarity))
    
    def _calculate_geometric_similarity(self, detection: Dict, depth: float, track: Dict) -> float:
        """Calculate geometric similarity based on position and movement"""
        if not track["positions"]:
            return 0.5  # Neutral similarity for new tracks
            
        # Current detection position
        bbox = detection["bbox"]
        current_pos = np.array([
            (bbox[0] + bbox[2]) / 2,  # center_x
            (bbox[1] + bbox[3]) / 2,  # center_y
            depth                      # depth
        ])
        
        # Last known track position
        last_pos = track["positions"][-1]
        
        # Calculate distance
        distance = np.linalg.norm(current_pos - last_pos)
        
        # Convert to similarity (closer = higher similarity)
        max_distance = self.max_tracking_distance
        if distance > max_distance:
            return 0.0
            
        similarity = 1.0 - (distance / max_distance)
        return max(0.0, min(1.0, similarity))
    
    def _calculate_temporal_consistency(self, track: Dict, current_timestamp: float) -> float:
        """Calculate temporal consistency score"""
        time_since_update = current_timestamp - track["last_update"]
        
        # Prefer recently updated tracks
        max_time_gap = 1.0  # 1 second
        if time_since_update > max_time_gap:
            return 0.0
            
        consistency = 1.0 - (time_since_update / max_time_gap)
        return max(0.0, min(1.0, consistency))
    
    def _create_new_track(self, detection: Dict, reid_feature: np.ndarray, 
                         depth: float, timestamp: float) -> int:
        """Create a new person track"""
        track_id = self.next_track_id
        self.next_track_id += 1
        
        bbox = detection["bbox"]
        position = np.array([
            (bbox[0] + bbox[2]) / 2,  # center_x
            (bbox[1] + bbox[3]) / 2,  # center_y
            depth                      # depth
        ])
        
        track = {
            "id": track_id,
            "status": "active",
            "confidence": detection.get("confidence", 0.5),
            "created_at": timestamp,
            "last_update": timestamp,
            "age": 1,
            "consecutive_misses": 0,
            
            # History storage
            "positions": [position.copy()],
            "bboxes": [bbox.copy()],
            "reid_features": [reid_feature.copy()],
            "depths": [depth],
            "timestamps": [timestamp],
            
            # Motion estimation
            "velocity": np.zeros(3),
            "velocity_history": [],
            
            # Track quality metrics
            "average_confidence": detection.get("confidence", 0.5),
            "max_confidence": detection.get("confidence", 0.5),
            "feature_consistency": 1.0
        }
        
        self.tracks[track_id] = track
        self.track_stats["total_tracks_created"] += 1
        
        logger.debug(f"Created new track {track_id}")
        return track_id
    
    def _update_track(self, track_id: int, detection: Dict, reid_feature: np.ndarray,
                     depth: float, timestamp: float):
        """Update existing track with new detection"""
        track = self.tracks[track_id]
        
        bbox = detection["bbox"]
        position = np.array([
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2,
            depth
        ])
        
        # Update basic info
        track["last_update"] = timestamp
        track["age"] += 1
        track["consecutive_misses"] = 0
        track["status"] = "active"
        
        # Update history
        track["positions"].append(position.copy())
        track["bboxes"].append(bbox.copy())
        track["reid_features"].append(reid_feature.copy())
        track["depths"].append(depth)
        track["timestamps"].append(timestamp)
        
        # Limit history size for memory management
        max_history = self.track_memory_frames
        if len(track["positions"]) > max_history:
            track["positions"] = track["positions"][-max_history:]
            track["bboxes"] = track["bboxes"][-max_history:]
            track["reid_features"] = track["reid_features"][-max_history:]
            track["depths"] = track["depths"][-max_history:]
            track["timestamps"] = track["timestamps"][-max_history:]
        
        # Update velocity estimation
        if len(track["positions"]) >= 2:
            dt = timestamp - track["timestamps"][-2]
            if dt > 0:
                velocity = (position - track["positions"][-2]) / dt
                track["velocity"] = velocity
                track["velocity_history"].append(velocity.copy())
                
                if len(track["velocity_history"]) > 10:
                    track["velocity_history"] = track["velocity_history"][-10:]
        
        # Update quality metrics
        current_conf = detection.get("confidence", 0.5)
        track["confidence"] = current_conf
        track["max_confidence"] = max(track["max_confidence"], current_conf)
        
        # Update average confidence
        all_confidences = [detection.get("confidence", 0.5) for _ in track["timestamps"]]
        track["average_confidence"] = float(np.mean(all_confidences))
        
        # Feature consistency (similarity with track's average feature)
        if len(track["reid_features"]) > 1:
            avg_feature = np.mean(track["reid_features"], axis=0)
            consistency = self._calculate_feature_similarity(reid_feature, avg_feature)
            track["feature_consistency"] = consistency
    
    def _mark_track_lost(self, track_id: int, timestamp: float):
        """Mark track as lost (not matched in current frame)"""
        track = self.tracks[track_id]
        track["consecutive_misses"] += 1
        track["last_update"] = timestamp
        
        # If too many consecutive misses, mark as lost
        if track["consecutive_misses"] >= 5:
            track["status"] = "lost"
            self.track_stats["total_tracks_lost"] += 1
            logger.debug(f"Track {track_id} marked as lost")
    
    def _cleanup_old_tracks(self, current_timestamp: float):
        """Remove very old tracks to free memory"""
        tracks_to_remove = []
        
        for track_id, track in self.tracks.items():
            # Remove lost tracks after some time
            if track["status"] == "lost":
                time_since_lost = current_timestamp - track["last_update"]
                if time_since_lost > 5.0:  # 5 seconds
                    tracks_to_remove.append(track_id)
            
            # Remove very old inactive tracks
            elif track["consecutive_misses"] > 10:
                tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.tracks[track_id]
            logger.debug(f"Removed old track {track_id}")
    
    def _update_statistics(self):
        """Update tracking statistics"""
        active_tracks = sum(1 for track in self.tracks.values() if track["status"] == "active")
        self.track_stats["active_tracks"] = active_tracks
        
        if self.tracks:
            track_lengths = [track["age"] for track in self.tracks.values()]
            self.track_stats["average_track_length"] = float(np.mean(track_lengths))
    
    def get_active_tracks(self) -> Dict[int, Dict]:
        """Get all currently active tracks"""
        return {tid: track for tid, track in self.tracks.items() 
                if track["status"] == "active"}
    
    def get_track_predictions(self, timestamp: float) -> Dict[int, Dict]:
        """Get predicted positions for all active tracks"""
        predictions = {}
        
        for track_id, track in self.tracks.items():
            if track["status"] != "active" or not track["positions"]:
                continue
                
            # Simple linear prediction based on velocity
            dt = timestamp - track["last_update"]
            if dt > 0 and len(track["velocity_history"]) > 0:
                # Use average velocity for prediction
                avg_velocity = np.mean(track["velocity_history"], axis=0)
                predicted_pos = track["positions"][-1] + avg_velocity * dt
                
                predictions[track_id] = {
                    "predicted_position": predicted_pos,
                    "confidence": track["confidence"] * max(0.1, 1.0 - dt),  # Decay with time
                    "velocity": avg_velocity
                }
        
        return predictions
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        if not self.processing_times:
            return {"avg_processing_time_ms": 0, "max_processing_time_ms": 0}
            
        avg_time = float(np.mean(self.processing_times) * 1000)
        max_time = float(np.max(self.processing_times) * 1000)
        
        return {
            "avg_processing_time_ms": avg_time,
            "max_processing_time_ms": max_time,
            "frames_processed": self.frame_count,
            "tracking_stats": dict(self.track_stats)
        }
    
    def reset_tracks(self):
        """Reset all tracks (useful for testing or reinitialization)"""
        self.tracks.clear()
        self.next_track_id = 1
        self.frame_count = 0
        self.processing_times.clear()
        self.track_stats = {
            "total_tracks_created": 0,
            "total_tracks_lost": 0,
            "average_track_length": 0.0,
            "active_tracks": 0
        }
        logger.info("All tracks reset")


# Test function
def test_person_tracker():
    """Test person tracker functionality"""
    print("🧪 Testing Person Tracker...")
    
    # Load config
    with open("config/reid_config.json", 'r') as f:
        config = json.load(f)
    
    tracker = PersonTracker(config)
    
    # Create simulated detections across multiple frames
    np.random.seed(42)  # For reproducible tests
    
    feature_dim = 512  # Typical ReID feature dimension
    
    # Frame 1: 2 persons detected
    detections_1 = [
        {"bbox": np.array([400, 200, 600, 800]), "confidence": 0.9},
        {"bbox": np.array([800, 300, 1000, 700]), "confidence": 0.8}
    ]
    features_1 = np.random.randn(2, feature_dim)
    depths_1 = [5.0, 8.0]
    
    tracks_1 = tracker.update_tracks(detections_1, features_1, depths_1, 1.0)
    print(f"Frame 1: {len(tracks_1)} tracks")
    
    # Frame 2: Same persons moved slightly + 1 new person
    detections_2 = [
        {"bbox": np.array([450, 220, 650, 820]), "confidence": 0.85},  # Person 1 moved
        {"bbox": np.array([850, 320, 1050, 720]), "confidence": 0.82}, # Person 2 moved
        {"bbox": np.array([200, 400, 350, 750]), "confidence": 0.75}   # New person
    ]
    # Keep similar features for same persons, new feature for new person
    features_2 = np.vstack([
        features_1[0] + np.random.randn(feature_dim) * 0.1,  # Similar to person 1
        features_1[1] + np.random.randn(feature_dim) * 0.1,  # Similar to person 2
        np.random.randn(feature_dim)                         # New person
    ])
    depths_2 = [5.2, 8.1, 4.5]
    
    tracks_2 = tracker.update_tracks(detections_2, features_2, depths_2, 2.0)
    print(f"Frame 2: {len(tracks_2)} tracks")
    
    # Frame 3: One person leaves, others continue
    detections_3 = [
        {"bbox": np.array([500, 240, 700, 840]), "confidence": 0.88},  # Person 1
        {"bbox": np.array([180, 420, 330, 770]), "confidence": 0.70}   # New person continues
    ]
    features_3 = np.vstack([
        features_1[0] + np.random.randn(feature_dim) * 0.15,  # Person 1
        features_2[2] + np.random.randn(feature_dim) * 0.1    # New person
    ])
    depths_3 = [5.5, 4.3]
    
    tracks_3 = tracker.update_tracks(detections_3, features_3, depths_3, 3.0)
    print(f"Frame 3: {len(tracks_3)} tracks")
    
    # Display tracking results
    print(f"\nTracking Summary:")
    for track_id, track in tracks_3.items():
        print(f"  Track {track_id}: status={track['status']}, age={track['age']}, "
             f"conf={track['confidence']:.2f}, misses={track['consecutive_misses']}")
    
    # Test predictions
    predictions = tracker.get_track_predictions(3.5)
    print(f"\nPredictions for t=3.5s:")
    for track_id, pred in predictions.items():
        pos = pred["predicted_position"]
        print(f"  Track {track_id}: predicted pos=({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")
    
    # Performance stats
    perf_stats = tracker.get_performance_stats()
    print(f"\nPerformance Stats:")
    print(f"  Avg processing time: {perf_stats['avg_processing_time_ms']:.1f}ms")
    print(f"  Tracks created: {perf_stats['tracking_stats']['total_tracks_created']}")
    print(f"  Tracks lost: {perf_stats['tracking_stats']['total_tracks_lost']}")
    print(f"  Active tracks: {perf_stats['tracking_stats']['active_tracks']}")
    
    print("✅ Person tracker test completed")


if __name__ == "__main__":
    test_person_tracker()

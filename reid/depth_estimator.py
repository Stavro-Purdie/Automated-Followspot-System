#!/usr/bin/env python3
"""
Depth Estimation Module for Z-coordinate calculation
Provides multiple methods for estimating depth from 2D person detections
"""

import numpy as np
import cv2
import logging
from typing import Dict, List, Tuple, Optional
import json

logger = logging.getLogger("depth_estimator")

class DepthEstimator:
    """
    Estimates Z-coordinates (depth) for detected persons using various methods
    """
    
    def __init__(self, config: Dict):
        """
        Initialize depth estimator with camera configuration
        
        Args:
            config: Reid configuration dictionary
        """
        self.camera_config = config["camera"]["front_camera"]
        self.stage_config = config["stage_geometry"]
        self.method = config["tracking"]["depth_estimation_method"]
        
        # Camera parameters
        self.camera_height = self.camera_config["position"][2]  # meters above stage
        self.camera_angle = self.camera_config["angle"]  # degrees from horizontal
        self.focal_length = self.camera_config["focal_length"]  # pixels
        self.fov = self.camera_config["fov"]  # degrees
        
        # Stage parameters
        self.stage_width = self.stage_config["width"]
        self.stage_depth = self.stage_config["depth"]
        
        # Person assumptions
        self.average_person_height = 1.75  # meters
        self.min_person_height = 1.5      # meters
        self.max_person_height = 2.0      # meters
        
        logger.info(f"DepthEstimator initialized - method: {self.method}")
    
    def estimate_depths(self, persons: List[Dict], frame_shape: Tuple[int, int]) -> List[float]:
        """
        Estimate depths for all detected persons
        
        Args:
            persons: List of person detection dictionaries
            frame_shape: (height, width) of the frame
            
        Returns:
            List of estimated depths in meters
        """
        depths = []
        
        for person in persons:
            if self.method == "geometric":
                depth = self._geometric_depth(person, frame_shape)
            elif self.method == "height_based":
                depth = self._height_based_depth(person)
            elif self.method == "hybrid":
                depth = self._hybrid_depth(person, frame_shape)
            else:
                depth = self._simple_depth(person)
                
            depths.append(depth)
        
        return depths
    
    def _simple_depth(self, person: Dict) -> float:
        """
        Simple depth estimation based on person height in pixels
        
        Args:
            person: Person detection dictionary
            
        Returns:
            Estimated depth in meters
        """
        bbox = person["bbox"]
        person_height_pixels = bbox[3] - bbox[1]  # y2 - y1
        
        if person_height_pixels <= 0:
            return 10.0  # Default depth
            
        # Simple pinhole camera model: depth = (real_height * focal_length) / pixel_height
        depth = (self.average_person_height * self.focal_length) / person_height_pixels
        
        # Clamp to reasonable range
        return max(1.0, min(20.0, depth))
    
    def _height_based_depth(self, person: Dict) -> float:
        """
        Height-based depth estimation with person height variation consideration
        
        Args:
            person: Person detection dictionary
            
        Returns:
            Estimated depth in meters
        """
        bbox = person["bbox"]
        person_height_pixels = bbox[3] - bbox[1]
        
        if person_height_pixels <= 0:
            return 10.0
            
        # Estimate depth for average height
        depth_avg = (self.average_person_height * self.focal_length) / person_height_pixels
        
        # Consider height variations (shorter people appear closer, taller appear farther)
        # This is a rough approximation - in reality we'd need person-specific height data
        confidence = person.get("confidence", 0.5)
        
        # Higher confidence detections get less height variation adjustment
        variation_factor = 1.0 - (confidence - 0.5) * 0.2  # Reduce variation for high confidence
        
        # Apply small random variation to account for height differences
        height_variation = np.random.uniform(0.9, 1.1) * variation_factor
        adjusted_depth = depth_avg * height_variation
        
        return max(1.0, min(20.0, adjusted_depth))
    
    def _geometric_depth(self, person: Dict, frame_shape: Tuple[int, int]) -> float:
        """
        Geometric depth estimation using ground plane projection
        
        Args:
            person: Person detection dictionary
            frame_shape: (height, width) of the frame
            
        Returns:
            Estimated depth in meters
        """
        bbox = person["bbox"]
        
        # Use bottom center of bounding box (feet position)
        foot_x = (bbox[0] + bbox[2]) / 2
        foot_y = bbox[3]  # Bottom of bounding box
        
        frame_height, frame_width = frame_shape
        
        # Convert pixel coordinates to normalized coordinates (-1 to 1)
        norm_x = (foot_x / frame_width) * 2 - 1
        norm_y = (foot_y / frame_height) * 2 - 1
        
        # Calculate angle from camera center to foot position
        half_fov_rad = np.radians(self.fov / 2)
        
        # Vertical angle from camera optical axis
        vertical_angle = norm_y * half_fov_rad
        
        # Horizontal angle from camera optical axis  
        horizontal_angle = norm_x * half_fov_rad
        
        # Ground plane intersection
        # Assuming camera is looking horizontally (angle = 0)
        if abs(vertical_angle) < 0.001:  # Prevent division by zero
            vertical_angle = 0.001
            
        # Distance to ground intersection point
        # height / tan(angle) gives horizontal distance
        camera_tilt = np.radians(self.camera_angle)
        total_vertical_angle = camera_tilt + vertical_angle
        
        if abs(total_vertical_angle) < 0.001:
            total_vertical_angle = 0.001
            
        depth = self.camera_height / np.tan(abs(total_vertical_angle))
        
        # Adjust for horizontal displacement
        depth = depth / np.cos(horizontal_angle)
        
        return max(1.0, min(20.0, depth))
    
    def _hybrid_depth(self, person: Dict, frame_shape: Tuple[int, int]) -> float:
        """
        Hybrid depth estimation combining geometric and height-based methods
        
        Args:
            person: Person detection dictionary
            frame_shape: (height, width) of the frame
            
        Returns:
            Estimated depth in meters
        """
        # Get both estimates
        geometric_depth = self._geometric_depth(person, frame_shape)
        height_depth = self._height_based_depth(person)
        
        # Weight based on person detection confidence
        confidence = person.get("confidence", 0.5)
        
        # Higher confidence -> trust height-based more (more reliable person detection)
        # Lower confidence -> trust geometric more (ground plane is more reliable)
        height_weight = confidence * 0.7 + 0.3  # Range: 0.3 to 1.0
        geometric_weight = 1.0 - height_weight
        
        combined_depth = (height_depth * height_weight + 
                         geometric_depth * geometric_weight)
        
        return max(1.0, min(20.0, combined_depth))
    
    def estimate_3d_position(self, person: Dict, frame_shape: Tuple[int, int]) -> Dict[str, float]:
        """
        Estimate full 3D position (X, Y, Z) for a person
        Note: This assumes IR tracking provides X, Y. This method provides Z.
        
        Args:
            person: Person detection dictionary
            frame_shape: (height, width) of the frame
            
        Returns:
            Dictionary with estimated 3D position
        """
        # Estimate depth (Z coordinate)
        depth = self.estimate_depths([person], frame_shape)[0]
        
        # Calculate X, Y from pixel position and depth
        bbox = person["bbox"]
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        
        frame_height, frame_width = frame_shape
        
        # Convert to normalized coordinates
        norm_x = (center_x / frame_width) * 2 - 1
        norm_y = (center_y / frame_height) * 2 - 1
        
        # Calculate field of view in world coordinates at this depth
        half_fov_rad = np.radians(self.fov / 2)
        width_at_depth = 2 * depth * np.tan(half_fov_rad)
        height_at_depth = width_at_depth * (frame_height / frame_width)
        
        # World coordinates (camera-relative)
        world_x = norm_x * (width_at_depth / 2)
        world_y = -norm_y * (height_at_depth / 2)  # Negative because image Y is flipped
        world_z = depth
        
        return {
            "x": world_x,
            "y": world_y, 
            "z": world_z,
            "confidence": person.get("confidence", 0.5)
        }
    
    def calibrate_camera_height(self, known_positions: List[Tuple[Dict, float]]) -> float:
        """
        Calibrate camera height using known person positions
        
        Args:
            known_positions: List of (person_detection, actual_depth) tuples
            
        Returns:
            Calibrated camera height
        """
        if not known_positions:
            return self.camera_height
            
        height_estimates = []
        
        for person, actual_depth in known_positions:
            bbox = person["bbox"]
            person_height_pixels = bbox[3] - bbox[1]
            
            if person_height_pixels > 0:
                # Reverse calculate camera height
                implied_height = (actual_depth * person_height_pixels) / self.focal_length
                height_estimates.append(implied_height)
        
        if height_estimates:
            calibrated_height = np.median(height_estimates)
            logger.info(f"Camera height calibrated: {self.camera_height:.2f}m -> {calibrated_height:.2f}m")
            return float(calibrated_height)
        
        return self.camera_height
    
    def get_depth_confidence(self, person: Dict, estimated_depth: float) -> float:
        """
        Calculate confidence score for depth estimation
        
        Args:
            person: Person detection dictionary
            estimated_depth: Estimated depth value
            
        Returns:
            Confidence score between 0 and 1
        """
        confidence_factors = []
        
        # Factor 1: Person detection confidence
        detection_conf = person.get("confidence", 0.5)
        confidence_factors.append(detection_conf)
        
        # Factor 2: Bounding box quality (aspect ratio)
        bbox = person["bbox"]
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        
        if height > 0:
            aspect_ratio = width / height
            # Typical person aspect ratio is around 0.4-0.6
            aspect_conf = 1.0 - abs(aspect_ratio - 0.5) * 2
            aspect_conf = max(0, min(1, aspect_conf))
            confidence_factors.append(aspect_conf)
        
        # Factor 3: Depth reasonableness (1-20m range)
        if 2.0 <= estimated_depth <= 15.0:
            depth_conf = 1.0
        elif 1.0 <= estimated_depth < 2.0:
            depth_conf = (estimated_depth - 1.0) / 1.0
        elif 15.0 < estimated_depth <= 20.0:
            depth_conf = (20.0 - estimated_depth) / 5.0
        else:
            depth_conf = 0.1
            
        confidence_factors.append(depth_conf)
        
        # Combine confidence factors
        overall_confidence = np.mean(confidence_factors)
        
        return max(0.0, min(1.0, float(overall_confidence)))


# Test function
def test_depth_estimator():
    """Test depth estimator functionality"""
    print("🧪 Testing Depth Estimator...")
    
    # Load config
    with open("config/reid_config.json", 'r') as f:
        config = json.load(f)
    
    estimator = DepthEstimator(config)
    
    # Create test persons at different positions
    test_persons = [
        {
            "bbox": np.array([400, 200, 600, 800]),  # Close person (large)
            "confidence": 0.9
        },
        {
            "bbox": np.array([800, 400, 900, 700]),  # Medium distance
            "confidence": 0.7
        },
        {
            "bbox": np.array([1200, 500, 1280, 650]), # Far person (small)
            "confidence": 0.6
        }
    ]
    
    frame_shape = (1080, 1920)
    
    # Test different methods
    methods = ["simple", "height_based", "geometric", "hybrid"]
    
    for method in methods:
        if method in ["simple", "height_based", "geometric", "hybrid"]:
            config["tracking"]["depth_estimation_method"] = method
            estimator.method = method
            
            depths = estimator.estimate_depths(test_persons, frame_shape)
            
            print(f"\n{method.title()} Method Results:")
            for i, (person, depth) in enumerate(zip(test_persons, depths)):
                bbox = person["bbox"]
                height_px = bbox[3] - bbox[1]
                conf = person["confidence"]
                depth_conf = estimator.get_depth_confidence(person, depth)
                
                print(f"  Person {i+1}: {depth:.1f}m "
                     f"(height: {height_px}px, conf: {conf:.2f}, depth_conf: {depth_conf:.2f})")
    
    # Test 3D position estimation
    print(f"\n3D Position Estimation:")
    pos_3d = estimator.estimate_3d_position(test_persons[0], frame_shape)
    print(f"  Person 1: X={pos_3d['x']:.1f}m, Y={pos_3d['y']:.1f}m, Z={pos_3d['z']:.1f}m")
    
    print("✅ Depth estimator test completed")


if __name__ == "__main__":
    test_depth_estimator()

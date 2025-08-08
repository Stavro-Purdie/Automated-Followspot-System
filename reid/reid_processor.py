#!/usr/bin/env python3
"""
Optimized Person Re-Identification Processor
Designed for 15fps @ 1080p real-time performance
"""

import cv2
import torch
import torchvision.transforms as T
import numpy as np
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reid_processor")

class OptimizedReIDProcessor:
    """
    High-performance ReID processor optimized for 15fps @ 1080p
    Target processing time: <55ms per frame
    """
    
    def __init__(self, config_path: str = "../config/reid_config.json"):
        """Initialize the ReID processor with configuration"""
        self.config = self._load_config(config_path)
        self.device = self._setup_device()
        
        # Performance tracking
        self.target_fps = self.config["performance"]["target_fps"]
        self.frame_interval = 1.0 / self.target_fps
        self.last_process_time = 0
        self.processing_times = []
        
        # Model placeholders - will be loaded in start()
        self.person_detector = None
        self.reid_model = None
        self.transforms = None
        
        # Status tracking
        self.is_initialized = False
        self.frame_count = 0
        
        logger.info(f"ReID Processor initialized - Target: {self.target_fps}fps @ {self.config['performance']['input_resolution']}")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load ReID configuration"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded ReID config from {config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise
    
    def _setup_device(self) -> torch.device:
        """Setup optimal device (CUDA/CPU)"""
        if self.config["models"]["detector"]["device"] == "auto":
            if torch.cuda.is_available():
                device = torch.device("cuda")
                logger.info(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
            else:
                device = torch.device("cpu")
                logger.info("Using CPU device")
        else:
            device = torch.device(self.config["models"]["detector"]["device"])
            
        return device
    
    def start(self) -> bool:
        """Initialize and load all models"""
        try:
            logger.info("Starting ReID processor - loading models...")
            start_time = time.time()
            
            # Load person detector
            self.person_detector = self._load_person_detector()
            
            # Load ReID model
            self.reid_model = self._load_reid_model()
            
            # Setup image transforms
            self.transforms = self._setup_transforms()
            
            # Mark as initialized
            self.is_initialized = True
            
            load_time = time.time() - start_time
            logger.info(f"ReID processor started successfully in {load_time:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start ReID processor: {e}")
            return False
    
    def _load_person_detector(self):
        """Load optimized person detector (YOLOv8n)"""
        try:
            # Try to load YOLOv8 via ultralytics
            from ultralytics import YOLO
            
            model_name = self.config["models"]["detector"]["name"]
            model = YOLO(model_name + ".pt")  # Will auto-download if needed
            
            # Move to device and set to eval mode
            model.to(self.device)
            
            logger.info(f"Loaded person detector: {model_name}")
            return model
            
        except ImportError:
            logger.warning("ultralytics not available, falling back to torchvision")
            # Fallback to torchvision detection
            import torchvision.models as models
            model = models.detection.fasterrcnn_mobilenet_v3_large_fpn(pretrained=True)
            model.to(self.device)
            model.eval()
            return model
        
        except Exception as e:
            logger.error(f"Failed to load person detector: {e}")
            raise
    
    def _load_reid_model(self):
        """Load ReID model (OSNet or fallback)"""
        try:
            # Try to load torchreid OSNet
            import torchreid
            
            model_name = self.config["models"]["reid"]["name"]
            model = torchreid.models.build_model(
                name=model_name,
                num_classes=1000,  # Market1501 classes
                loss='softmax',
                pretrained=True
            )
            
            model.to(self.device)
            model.eval()
            
            logger.info(f"Loaded ReID model: {model_name}")
            return model
            
        except ImportError:
            logger.warning("torchreid not available, using fallback ReID model")
            # Simple fallback - ResNet feature extractor
            import torchvision.models as models
            model = models.resnet50(pretrained=True)
            model.fc = torch.nn.Identity()  # Remove classification layer
            model.to(self.device)
            model.eval()
            return model
            
        except Exception as e:
            logger.error(f"Failed to load ReID model: {e}")
            raise
    
    def _setup_transforms(self):
        """Setup image preprocessing transforms"""
        # Standard ReID preprocessing
        transforms = T.Compose([
            T.ToPILImage(),
            T.Resize((256, 128)),  # Standard ReID input size
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        logger.info("Image transforms configured")
        return transforms
    
    def process_frame(self, rgb_frame: np.ndarray, timestamp: float = None) -> Dict[str, Any]:
        """
        Main frame processing pipeline
        Target: <55ms processing time
        
        Args:
            rgb_frame: Input RGB frame (1080p)
            timestamp: Frame timestamp
            
        Returns:
            Dict containing detected persons with features and depths
        """
        if not self.is_initialized:
            logger.error("ReID processor not initialized. Call start() first.")
            return {"error": "not_initialized"}
        
        if timestamp is None:
            timestamp = time.time()
            
        start_time = time.time()
        
        # Frame rate control
        if start_time - self.last_process_time < self.frame_interval:
            return {"skipped": True, "reason": "frame_rate_limit"}
        
        try:
            # Step 1: Detect persons (~25ms target)
            persons = self._detect_persons(rgb_frame)
            
            # Step 2: Extract ReID features (~15ms target)  
            person_features = self._extract_reid_features(rgb_frame, persons)
            
            # Step 3: Estimate depths (~5ms target)
            person_depths = self._estimate_depths(persons, rgb_frame.shape)
            
            # Combine results
            results = []
            for i, person in enumerate(persons):
                results.append({
                    "person_id": i,  # Temporary ID, tracking will assign persistent IDs
                    "bbox": person["bbox"],
                    "center": person["center"],
                    "confidence": person["confidence"],
                    "features": person_features[i] if i < len(person_features) else None,
                    "depth": person_depths[i] if i < len(person_depths) else None,
                    "timestamp": timestamp
                })
            
            processing_time = time.time() - start_time
            self.processing_times.append(processing_time)
            self.last_process_time = start_time
            self.frame_count += 1
            
            # Log performance every 30 frames
            if self.frame_count % 30 == 0:
                avg_time = np.mean(self.processing_times[-30:])
                logger.info(f"ReID processing: {avg_time*1000:.1f}ms avg, "
                           f"{1/avg_time:.1f}fps, {len(persons)} persons")
            
            return {
                "persons": results,
                "processing_time": processing_time,
                "timestamp": timestamp,
                "frame_count": self.frame_count
            }
            
        except Exception as e:
            logger.error(f"Error in ReID processing: {e}")
            return {"error": str(e)}
    
    def _detect_persons(self, frame: np.ndarray) -> List[Dict]:
        """Detect persons in frame (target: <25ms)"""
        persons = []
        
        try:
            # Resize for detection if needed (speed optimization)
            detect_frame = frame
            scale = 1.0
            
            target_height = self.config["performance"]["detection_resolution"][1]
            if frame.shape[0] > target_height:
                scale = target_height / frame.shape[0]
                new_width = int(frame.shape[1] * scale)
                detect_frame = cv2.resize(frame, (new_width, target_height))
            
            # Run detection
            with torch.no_grad():
                if hasattr(self.person_detector, 'predict'):  # YOLOv8
                    results = self.person_detector.predict(detect_frame, verbose=False)
                    
                    # Process YOLOv8 results
                    for result in results:
                        boxes = result.boxes
                        if boxes is not None:
                            for box in boxes:
                                # Check if it's a person (class 0)
                                if int(box.cls) == 0:
                                    conf = float(box.conf)
                                    if conf > self.config["performance"]["confidence_threshold"]:
                                        # Scale back to original size
                                        bbox = box.xyxy[0].cpu().numpy() / scale
                                        
                                        persons.append({
                                            "bbox": bbox,
                                            "confidence": conf,
                                            "center": [(bbox[0] + bbox[2])/2, (bbox[1] + bbox[3])/2]
                                        })
                else:
                    # Fallback detection method
                    logger.warning("Using fallback detection method")
            
        except Exception as e:
            logger.error(f"Person detection failed: {e}")
        
        return persons
    
    def _extract_reid_features(self, frame: np.ndarray, persons: List[Dict]) -> List[np.ndarray]:
        """Extract ReID features from detected persons (target: <15ms)"""
        features = []
        
        try:
            for person in persons:
                # Crop person from frame
                bbox = person["bbox"].astype(int)
                x1, y1, x2, y2 = bbox
                
                # Ensure coordinates are within frame bounds
                h, w = frame.shape[:2]
                x1, x2 = max(0, x1), min(w, x2)
                y1, y2 = max(0, y1), min(h, y2)
                
                if x2 > x1 and y2 > y1:
                    person_crop = frame[y1:y2, x1:x2]
                    
                    # Preprocess for ReID model
                    if self.transforms:
                        input_tensor = self.transforms(person_crop).unsqueeze(0).to(self.device)
                        
                        # Extract features
                        with torch.no_grad():
                            feature_vector = self.reid_model(input_tensor)
                            feature_vector = feature_vector.cpu().numpy().flatten()
                            features.append(feature_vector)
                    else:
                        # Fallback: simple histogram features
                        hist = cv2.calcHist([person_crop], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                        features.append(hist.flatten())
                else:
                    features.append(np.zeros(512))  # Dummy features for invalid crops
                    
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
        
        return features
    
    def _estimate_depths(self, persons: List[Dict], frame_shape: Tuple[int, int]) -> List[float]:
        """Estimate depth/Z-coordinates for detected persons (target: <5ms)"""
        depths = []
        
        try:
            camera_config = self.config["camera"]["front_camera"]
            camera_height = camera_config["position"][2]  # meters
            focal_length = camera_config["focal_length"]   # pixels
            
            for person in persons:
                bbox = person["bbox"]
                person_height_pixels = bbox[3] - bbox[1]  # y2 - y1
                
                # Geometric depth estimation based on assumed person height
                assumed_height_meters = 1.75  # Average person height
                
                if person_height_pixels > 10:  # Avoid division by very small numbers
                    # Simple pinhole camera model
                    depth = (assumed_height_meters * focal_length) / person_height_pixels
                    
                    # Clamp to reasonable range (1-20 meters)
                    depth = max(1.0, min(20.0, depth))
                else:
                    depth = 10.0  # Default depth for very small detections
                
                depths.append(depth)
                
        except Exception as e:
            logger.error(f"Depth estimation failed: {e}")
            # Return default depths
            depths = [10.0] * len(persons)
        
        return depths
    
    def get_performance_stats(self) -> Dict[str, float]:
        """Get performance statistics"""
        if not self.processing_times:
            return {"error": "No processing data available"}
        
        recent_times = self.processing_times[-30:] if len(self.processing_times) >= 30 else self.processing_times
        
        return {
            "avg_processing_time_ms": np.mean(recent_times) * 1000,
            "max_processing_time_ms": np.max(recent_times) * 1000,
            "min_processing_time_ms": np.min(recent_times) * 1000,
            "avg_fps": 1.0 / np.mean(recent_times),
            "frames_processed": self.frame_count,
            "target_fps": self.target_fps
        }
    
    def stop(self):
        """Stop the ReID processor and cleanup"""
        self.is_initialized = False
        logger.info("ReID processor stopped")


# Test function for development
def test_reid_processor():
    """Test the ReID processor with a dummy frame"""
    print("🧪 Testing ReID Processor...")
    
    # Create dummy RGB frame (1080p)
    test_frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    
    # Initialize processor with correct path
    config_path = "config/reid_config.json" if Path("config/reid_config.json").exists() else "../config/reid_config.json"
    processor = OptimizedReIDProcessor(config_path)
    
    if processor.start():
        # Process test frame
        result = processor.process_frame(test_frame)
        print(f"✅ Test result: {result}")
        
        # Show performance stats
        stats = processor.get_performance_stats()
        print(f"📊 Performance: {stats}")
        
        processor.stop()
        return True
    else:
        print("❌ Failed to start ReID processor")
        return False


if __name__ == "__main__":
    test_reid_processor()

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

from PIL import Image

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
        self.project_root = Path(__file__).resolve().parent.parent
        self.feature_dim = int(self.config.get("models", {}).get("reid", {}).get("feature_dim", 512))

        # Identity gallery integration
        self.identity_config = self.config.get("identities", {})
        self.identity_gallery_path = self._resolve_path(self.identity_config.get("gallery_path", "identity_gallery"))
        manifest_default = self.identity_gallery_path / "manifest.json"
        self.identity_manifest_path = self._resolve_path(self.identity_config.get("manifest_path", manifest_default))
        self.identity_match_threshold = float(self.identity_config.get("match_threshold", 0.55))
        self.identity_reload_interval = float(self.identity_config.get("reload_interval_sec", 5.0))
        self.identity_embeddings: Dict[str, Dict[str, Any]] = {}
        self.identity_manifest_mtime: Optional[float] = None
        self._last_identity_refresh = 0.0
        
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

    def _resolve_path(self, path_value: Any) -> Path:
        """Resolve a path relative to the project root."""
        if isinstance(path_value, Path):
            path = path_value
        else:
            path = Path(path_value)
        if not path.is_absolute():
            path = (self.project_root / path).resolve()
        return path
    
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

            # Load identity gallery embeddings
            self._build_identity_index(force=True)
            self._last_identity_refresh = time.time()
            
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
            try:
                model = models.resnet50(weights=None)
            except TypeError:
                model = models.resnet50(pretrained=False)
            model.fc = torch.nn.Identity()  # type: ignore[assignment]
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

    def _build_identity_index(self, force: bool = False) -> None:
        """Load identity manifest and pre-compute embeddings."""
        manifest_path = self.identity_manifest_path
        if not manifest_path.exists():
            if force:
                logger.warning(f"Identity manifest not found at {manifest_path}")
            self.identity_embeddings = {}
            self.identity_manifest_mtime = None
            return

        try:
            mtime = manifest_path.stat().st_mtime
        except OSError as exc:
            logger.error(f"Unable to stat identity manifest: {exc}")
            return

        if not force and self.identity_manifest_mtime is not None and mtime <= self.identity_manifest_mtime:
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except Exception as exc:
            logger.error(f"Failed to load identity manifest: {exc}")
            return

        identities = manifest.get("identities", [])
        new_embeddings: Dict[str, Dict[str, Any]] = {}
        total_refs = 0

        if not self.transforms or self.reid_model is None:
            logger.warning("Cannot build identity index before models are initialized")
            return

        for identity in identities:
            identity_id = identity.get("id")
            if not identity_id:
                continue

            vectors: List[np.ndarray] = []
            image_paths = identity.get("images", [])
            if not image_paths and identity.get("primary_image"):
                image_paths = [identity["primary_image"]]

            for rel_path in image_paths:
                img_path = self.identity_gallery_path / rel_path
                if not img_path.exists():
                    logger.debug(f"Identity image missing: {img_path}")
                    continue
                feature = self._embed_identity_image(img_path)
                if feature is not None:
                    vectors.append(feature)

            if not vectors:
                continue

            try:
                feature_matrix = np.vstack(vectors).astype(np.float32)
            except ValueError:
                feature_matrix = np.array(vectors, dtype=np.float32)

            new_embeddings[identity_id] = {
                "name": identity.get("name", identity_id),
                "code": identity.get("code"),
                "primary_image": identity.get("primary_image"),
                "features": feature_matrix,
                "updated_at": identity.get("updated_at"),
                "created_at": identity.get("created_at"),
            }
            total_refs += feature_matrix.shape[0]

        self.identity_embeddings = new_embeddings
        self.identity_manifest_mtime = mtime
        logger.info(f"Identity gallery loaded: {len(new_embeddings)} identities, {total_refs} reference photos")
        self._last_identity_refresh = time.time()

    def _embed_identity_image(self, image_path: Path) -> Optional[np.ndarray]:
        """Compute a normalized feature vector for an identity reference image."""
        try:
            with Image.open(image_path) as img:
                rgb = img.convert("RGB")
                np_img = np.array(rgb)
        except Exception as exc:
            logger.warning(f"Failed to load identity image {image_path}: {exc}")
            return None

        if self.transforms is None or self.reid_model is None:
            return None

        transformed = self.transforms(np_img)
        if isinstance(transformed, torch.Tensor):
            input_tensor = transformed.unsqueeze(0)
        else:
            input_tensor = torch.as_tensor(transformed).unsqueeze(0)
        input_tensor = input_tensor.to(self.device)

        try:
            with torch.no_grad():
                feature_tensor = self.reid_model(input_tensor)
        except Exception as exc:
            logger.error(f"Failed to compute identity embedding for {image_path}: {exc}")
            return None

        if isinstance(feature_tensor, (tuple, list)):
            feature_tensor = feature_tensor[0]

        feature_vector = feature_tensor.detach().cpu().numpy().flatten()
        if feature_vector.size == 0:
            return None

        self.feature_dim = feature_vector.size
        norm = np.linalg.norm(feature_vector)
        if norm == 0:
            return None

        return (feature_vector / norm).astype(np.float32)

    def _maybe_refresh_identity_index(self) -> None:
        if self.identity_reload_interval <= 0:
            return
        now = time.time()
        if now - self._last_identity_refresh >= self.identity_reload_interval:
            self._build_identity_index()
            self._last_identity_refresh = now

    def _match_identity(self, feature_vector: np.ndarray) -> Optional[Dict[str, Any]]:
        if feature_vector is None or feature_vector.size == 0:
            return None
        if not self.identity_embeddings:
            return None

        norm = np.linalg.norm(feature_vector)
        if norm == 0:
            return None
        normalized = feature_vector / norm

        best_id = None
        best_score = -1.0
        best_entry: Optional[Dict[str, Any]] = None

        for identity_id, entry in self.identity_embeddings.items():
            vectors = entry.get("features")
            if vectors is None or len(vectors) == 0:
                continue
            scores = np.dot(vectors, normalized)
            score = float(np.max(scores))
            if score > best_score:
                best_score = score
                best_id = identity_id
                best_entry = entry

        if best_entry is None or best_score < self.identity_match_threshold:
            return None

        return {
            "id": best_id,
            "name": best_entry.get("name") or best_id,
            "code": best_entry.get("code"),
            "primary_image": best_entry.get("primary_image"),
            "score": best_score,
        }
    
    def process_frame(self, rgb_frame: np.ndarray, timestamp: Optional[float] = None) -> Dict[str, Any]:
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

        self._maybe_refresh_identity_index()

        try:
            # Step 1: Detect persons (~25ms target)
            persons = self._detect_persons(rgb_frame)

            # Step 2: Extract ReID features (~15ms target)
            person_features = self._extract_reid_features(rgb_frame, persons)

            # Step 3: Estimate depths (~5ms target)
            person_depths = self._estimate_depths(persons, rgb_frame.shape)

            # Step 4: Match identities
            identity_matches = [self._match_identity(f) if isinstance(f, np.ndarray) else None for f in person_features]

            # Combine results
            results = []
            for i, person in enumerate(persons):
                feature_vec = person_features[i] if i < len(person_features) else None
                match_info = identity_matches[i] if i < len(identity_matches) else None
                result_entry = {
                    "person_id": i,
                    "bbox": person["bbox"],
                    "center": person["center"],
                    "confidence": person["confidence"],
                    "features": feature_vec,
                    "depth": person_depths[i] if i < len(person_depths) else None,
                    "timestamp": timestamp,
                }
                if match_info:
                    result_entry["identity_match"] = match_info
                results.append(result_entry)
            
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
                    results = self.person_detector.predict(detect_frame, verbose=False)  # type: ignore[attr-defined]
                    
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
        features: List[np.ndarray] = []

        try:
            for person in persons:
                bbox = np.array(person["bbox"]).astype(int)
                x1, y1, x2, y2 = bbox

                h, w = frame.shape[:2]
                x1, x2 = max(0, x1), min(w, x2)
                y1, y2 = max(0, y1), min(h, y2)

                if x2 <= x1 or y2 <= y1:
                    features.append(np.zeros(self.feature_dim, dtype=np.float32))
                    continue

                person_crop = frame[y1:y2, x1:x2]

                if self.transforms and self.reid_model is not None:
                    transformed = self.transforms(person_crop)
                    if isinstance(transformed, torch.Tensor):
                        input_tensor = transformed.unsqueeze(0)
                    else:
                        input_tensor = torch.as_tensor(transformed).unsqueeze(0)
                    input_tensor = input_tensor.to(self.device)

                    with torch.no_grad():
                        feature_tensor = self.reid_model(input_tensor)

                    if isinstance(feature_tensor, (tuple, list)):
                        feature_tensor = feature_tensor[0]

                    feature_vector = feature_tensor.detach().cpu().numpy().flatten()
                    if feature_vector.size == 0:
                        feature_vector = np.zeros(self.feature_dim, dtype=np.float32)
                    else:
                        self.feature_dim = feature_vector.size
                        norm = np.linalg.norm(feature_vector)
                        if norm > 0:
                            feature_vector = (feature_vector / norm).astype(np.float32)
                        else:
                            feature_vector = np.zeros(self.feature_dim, dtype=np.float32)
                    features.append(feature_vector)
                else:
                    hist = cv2.calcHist([person_crop], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                    vec = hist.flatten().astype(np.float32)
                    if vec.size != self.feature_dim:
                        self.feature_dim = vec.size
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    features.append(vec)

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
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.processing_times:
            return {"error": "No processing data available"}
        
        recent_times = self.processing_times[-30:] if len(self.processing_times) >= 30 else self.processing_times
        
        return {
            "avg_processing_time_ms": float(np.mean(recent_times) * 1000),
            "max_processing_time_ms": float(np.max(recent_times) * 1000),
            "min_processing_time_ms": float(np.min(recent_times) * 1000),
            "avg_fps": float(1.0 / np.mean(recent_times)),
            "frames_processed": int(self.frame_count),
            "target_fps": float(self.target_fps),
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

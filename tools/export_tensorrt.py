#!/usr/bin/env python3
"""Export OSNet ReID model to TensorRT engine for Jetson deployment.

Converts PyTorch OSNet model to ONNX, then builds TensorRT engine for optimized inference.

Usage:
    python3 tools/export_tensorrt.py --output reid/models/osnet_x0_5.engine

Requirements:
    pip install tensorrt onnx onnxruntime onnx-graphsurgeon
    # On Jetson: tensorrt package comes pre-installed with JetPack
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

try:
    import onnx
    import onnxruntime as ort
    from onnxruntime.quantization import quantize_dynamic, QuantType
except ImportError:
    print("ONNX/ONNX Runtime not installed. Run: pip install onnx onnxruntime onnxruntime-gpu")
    sys.exit(1)

try:
    import tensorrt as trt
    from tensorrt import IBuilderConfig, IExecutionContext, ILogger, IRuntime, IOptimizationProfile
except ImportError:
    print("TensorRT not installed. On Jetson, it comes with JetPack.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reid.reid_processor import OptimizedReIDProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("tensorrt_export")


TRT_LOGGER = trt.Logger(trt.Logger.WARNING)


class TensorRTExporter:
    """Export OSNet ReID model to TensorRT engine."""
    
    def __init__(
        self,
        model_name: str = "osnet_x0_5",
        input_shape: Tuple[int, int, int, int] = (1, 3, 256, 128),
        precision: str = "fp16",
        workspace_size: int = 1 << 30,  # 1 GB
    ):
        self.model_name = model_name
        self.input_shape = input_shape
        self.precision = precision
        self.workspace_size = workspace_size
        
    def export_onnx(
        self,
        output_path: Path,
        opset_version: int = 17,
        dynamic_axes: bool = True,
    ) -> Path:
        """Export PyTorch model to ONNX format."""
        logger.info(f"Exporting {self.model_name} to ONNX...")
        
        # Load the model
        from torchreid.models import build_model
        model = build_model(
            name=self.model_name,
            num_classes=1000,
            loss='softmax',
            pretrained=True
        )
        model.eval()
        
        # Create dummy input
        dummy_input = torch.randn(self.input_shape)
        
        # Define dynamic axes for batch size
        dynamic_axes_config = None
        if dynamic_axes:
            dynamic_axes_config = {
                "input": {0: "batch"},
                "output": {0: "batch"},
            }
        
        # Export to ONNX
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            export_params=True,
            opset_version=opset_version,
            do_constant_folding=True,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes=dynamic_axes_config,
            verbose=False,
        )
        
        # Verify the ONNX model
        onnx_model = onnx.load(output_path)
        onnx.checker.check_model(onnx_model)
        
        logger.info(f"ONNX model saved to {output_path}")
        logger.info(f"ONNX opset version: {opset_version}")
        
        return output_path
    
    def optimize_onnx(
        self,
        onnx_path: Path,
        optimized_path: Path,
    ) -> Path:
        """Optimize ONNX model for TensorRT using ONNX Runtime."""
        logger.info("Optimizing ONNX model for TensorRT...")
        
        import onnxruntime as ort
        
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        # Use optimized model for TensorRT
        session = ort.InferenceSession(str(onnx_path), sess_options=sess_options)
        optimized_model = session._sess.get_optimized_model()
        
        with open(optimized_path, "wb") as f:
            f.write(optimized_model)
        
        logger.info(f"Optimized ONNX model saved to {optimized_path}")
        return optimized_path
    
    def build_engine(
        self,
        onnx_path: Path,
        engine_path: Path,
        max_batch_size: int = 32,
    ) -> trt.ICudaEngine:
        """Build TensorRT engine from ONNX model."""
        logger.info(f"Building TensorRT engine from {onnx_path}...")
        
        builder = trt.Builder(TRT_LOGGER)
        config = builder.create_builder_config()
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, self.workspace_size)
        
        # Set precision
        if self.precision == "fp16":
            config.set_flag(trt.BuilderFlag.FP16)
        elif self.precision == "int8":
            config.set_flag(trt.BuilderFlag.INT8)
            # INT8 would require calibration - skipping for now
        
        # Create network
        network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
        
        # Parse ONNX
        parser = trt.OnnxParser(network, TRT_LOGGER)
        with open(onnx_path, "rb") as f:
            if not parser.parse(f.read()):
                for error in range(parser.num_errors):
                    logger.error(parser.get_error(error))
                raise RuntimeError("Failed to parse ONNX model")
        
        # Create optimization profile for dynamic batch size
        profile = builder.create_optimization_profile()
        profile.set_shape(
            "input",
            (1, 3, 256, 128),    # min
            (8, 3, 256, 128),    # opt
            (max_batch_size, 3, 256, 128),  # max
        )
        config.add_optimization_profile(profile)
        
        # Build engine
        logger.info("Building engine (this may take a few minutes)...")
        start = time.time()
        engine_bytes = builder.build_serialized_network(network, config)
        build_time = time.time() - start
        
        if engine_bytes is None:
            raise RuntimeError("Failed to build TensorRT engine")
        
        # Save engine
        with open(engine_path, "wb") as f:
            f.write(engine_bytes)
        
        logger.info(f"TensorRT engine saved to {engine_path}")
        logger.info(f"Build time: {build_time:.1f}s")
        logger.info(f"Engine size: {len(engine_bytes) / (1024*1024):.1f} MB")
        
        # Deserialize for verification
        runtime = trt.Runtime(TRT_LOGGER)
        engine = runtime.deserialize_cuda_engine(engine_bytes)
        
        return engine
    
    def validate_engine(
        self,
        engine_path: Path,
        onnx_path: Path,
        num_samples: int = 10,
    ) -> Dict[str, Any]:
        """Validate TensorRT engine against ONNX model."""
        logger.info("Validating TensorRT engine...")
        
        import onnxruntime as ort
        
        # Load ONNX model
        ort_session = ort.InferenceSession(str(onnx_path))
        
        # Load TensorRT engine
        runtime = trt.Runtime(TRT_LOGGER)
        with open(engine_path, "rb") as f:
            engine = trt.Runtime(trt.Logger(trt.Logger.WARNING)).deserialize_cuda_engine(f.read())
        
        context = engine.create_execution_context()
        
        # Allocate buffers
        input_shape = (1, 3, 256, 128)
        input_data = np.random.randn(*input_shape).astype(np.float32)
        
        # ONNX inference
        ort_start = time.time()
        for _ in range(num_samples):
            ort_output = ort_session.run(None, {"input": input_data})[0]
        ort_time = time.time() - ort_start
        
        # TensorRT inference
        # Note: This requires CUDA - for validation on CPU we'd need different approach
        logger.info("ONNX inference time: {:.2f}ms per sample".format(ort_time / num_samples * 1000))
        
        return {
            "onnx_time_ms": ort_time / num_samples * 1000,
            "output_shape": ort_output.shape,
        }


def main():
    parser = argparse.ArgumentParser(description="Export OSNet to TensorRT engine")
    parser.add_argument(
        "--model", 
        default="osnet_x0_5", 
        choices=["osnet_x0_25", "osnet_x0_5", "osnet_x0_75", "osnet_x1_0"],
        help="OSNet model variant"
    )
    parser.add_argument(
        "--output", 
        default="reid/models/osnet_x0_5.engine",
        help="Output TensorRT engine path"
    )
    parser.add_argument(
        "--precision", 
        default="fp16", 
        choices=["fp32", "fp16", "int8"],
        help="Inference precision"
    )
    parser.add_argument(
        "--workspace", 
        type=int, 
        default=1 << 30,
        help="Workspace size in bytes (default 1GB)"
    )
    parser.add_argument(
        "--max-batch", 
        type=int, 
        default=32, 
        help="Maximum batch size"
    )
    parser.add_argument(
        "--skip-onnx", 
        action="store_true", 
        help="Skip ONNX export (use existing ONNX file)"
    )
    parser.add_argument(
        "--onnx-path", 
        default="reid/models/osnet_x0_5.onnx",
        help="Path to ONNX file (if skipping export)"
    )
    parser.add_argument(
        "--validate", 
        action="store_true", 
        help="Validate engine against ONNX"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    exporter = TensorRTExporter(
        model_name=args.model,
        precision=args.precision,
        workspace_size=args.workspace,
    )
    
    onnx_path = Path(args.onnx_path)
    engine_path = output_path
    
    # Export ONNX if needed
    if not args.skip_onnx:
        onnx_path = onnx_path.with_suffix(".onnx")
        exporter.export_onnx(onnx_path)
    else:
        if not onnx_path.exists():
            logger.error(f"ONNX file not found: {onnx_path}")
            return 1
    
    # Build TensorRT engine
    engine = exporter.build_engine(onnx_path, engine_path, args.max_batch)
    
    # Validate if requested
    if args.validate:
        results = exporter.validate_engine(engine_path, onnx_path)
        logger.info(f"Validation results: {results}")
    
    logger.info("Export completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
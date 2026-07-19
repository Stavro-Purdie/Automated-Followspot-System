#!/usr/bin/env python3
"""Convert torchreid OSNet model to CoreML for Apple Neural Engine acceleration.

Usage:
    python3 tools/convert_osnet_coreml.py --output reid/models/osnet_x0_5.mlpackage

Requirements:
    pip install torch torchreid coremltools
"""

import argparse
import sys
from pathlib import Path

import torch
import torch.nn as nn

try:
    import coremltools as ct
    COREML_AVAILABLE = True
except ImportError:
    COREML_AVAILABLE = False

try:
    import torchreid
    TORCHREID_AVAILABLE = True
except ImportError:
    TORCHREID_AVAILABLE = False


def build_osnet_model(model_name: str = "osnet_x0_5", num_classes: int = 1000) -> nn.Module:
    """Build OSNet model using torchreid."""
    if not TORCHREID_AVAILABLE:
        raise RuntimeError("torchreid not installed. Install with: pip install torchreid")

    print(f"Building {model_name} via torchreid...")
    model = torchreid.models.build_model(
        name=model_name,
        num_classes=num_classes,
        loss="softmax",
        pretrained=True
    )
    model.eval()
    return model


def convert_to_coreml(
    model: nn.Module,
    output_path: str,
    input_shape: tuple = (1, 3, 256, 128),
    compute_unit: str = "CPU_AND_NE",
    minimum_deployment_target: str = "macos13",
    quantize: bool = False,
) -> ct.models.MLModel:
    """Convert PyTorch model to CoreML format."""
    if not COREML_AVAILABLE:
        raise RuntimeError("coremltools not installed. Install with: pip install coremltools>=6.4")

    print(f"Converting to CoreML with compute_unit={compute_unit}...")
    print(f"Input shape: {input_shape}")

    # Create dummy input for tracing
    dummy_input = torch.randn(input_shape)

    # Trace the model
    with torch.no_grad():
        traced_model = torch.jit.trace(model, dummy_input)

    # Convert to CoreML
    # Note: Use TensorType for explicit input specification
    coreml_input = ct.TensorType(
        name="input",
        shape=input_shape,
        dtype=torch.float32
    )

    # Map compute unit string to enum
    compute_unit_map = {
        "CPU_ONLY": ct.ComputeUnit.CPU_ONLY,
        "CPU_AND_GPU": ct.ComputeUnit.CPU_AND_GPU,
        "CPU_AND_NE": ct.ComputeUnit.CPU_AND_NE,
        "ALL": ct.ComputeUnit.ALL,
    }
    cu = compute_unit_map.get(compute_unit, ct.ComputeUnit.CPU_AND_NE)

    # Perform conversion
    mlmodel = ct.convert(
        traced_model,
        inputs=[coreml_input],
        minimum_deployment_target=getattr(ct.target, minimum_deployment_target),
        compute_units=cu,
        convert_to="mlprogram",  # Use MLProgram format (iOS 15+/macOS 12+)
    )

    # Optional: Quantize to FP16 for smaller size and faster inference on ANE
    if quantize:
        print("Quantizing to FP16...")
        from coremltools.optimize.coreml import quantize_weights
        mlmodel = quantize_weights(mlmodel, nbits=16)

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mlmodel.save(str(output_path))
    print(f"✅ Saved CoreML model to: {output_path}")

    return mlmodel


def validate_model(mlmodel: ct.models.MLModel, input_shape: tuple = (1, 3, 256, 128)) -> None:
    """Validate CoreML model with a test input."""
    import numpy as np

    print("Validating model...")
    test_input = np.random.randn(*input_shape).astype(np.float32)

    # Get predictions
    predictions = mlmodel.predict({"input": test_input})

    # Find output tensor name
    output_names = list(predictions.keys())
    print(f"Output names: {output_names}")

    # Get the feature vector
    output_key = output_names[0]
    features = predictions[output_key]
    print(f"Output shape: {features.shape}")
    print(f"Output range: [{features.min():.4f}, {features.max():.4f}]")
    print(f"Output mean: {features.mean():.4f}, std: {features.std():.4f}")

    # Verify it's roughly normalized (OSNet outputs L2-normalized features)
    if features.ndim == 2:
        norms = np.linalg.norm(features, axis=1)
        print(f"Feature norms: {norms}")
        if np.allclose(norms, 1.0, atol=1.0):  # Allow some tolerance
            print("✅ Features appear to be L2-normalized")
        else:
            print("⚠️  Features may not be normalized (expected for some OSNet variants)")


def compare_pytorch_vs_coreml(
    pytorch_model: nn.Module,
    coreml_model: ct.models.MLModel,
    input_shape: tuple = (1, 3, 256, 128),
    num_tests: int = 10,
) -> None:
    """Compare PyTorch and CoreML outputs for numerical parity."""
    import numpy as np

    print(f"\nComparing PyTorch vs CoreML ({num_tests} random inputs)...")
    pytorch_model.eval()

    max_diff = 0.0
    max_cos_diff = 0.0

    for i in range(num_tests):
        test_input = torch.randn(input_shape)
        np_input = test_input.numpy().astype(np.float32)

        # PyTorch inference
        with torch.no_grad():
            pt_output = pytorch_model(test_input)
            if isinstance(pt_output, (tuple, list)):
                pt_output = pt_output[0]
            pt_features = pt_output.numpy().flatten()

        # CoreML inference
        cm_predictions = coreml_model.predict({"input": np_input})
        output_key = list(cm_predictions.keys())[0]
        cm_features = cm_predictions[output_key].flatten()

        # Compare
        diff = np.abs(pt_features - cm_features).max()
        max_diff = max(max_diff, diff)

        # Cosine similarity
        pt_norm = np.linalg.norm(pt_features)
        cm_norm = np.linalg.norm(cm_features)
        if pt_norm > 0 and cm_norm > 0:
            cos_sim = np.dot(pt_features, cm_features) / (pt_norm * cm_norm)
            cos_diff = 1.0 - cos_sim
            max_cos_diff = max(max_cos_diff, cos_diff)

        if i < 3:
            print(f"  Test {i+1}: max_abs_diff={diff:.6f}, cos_sim={cos_sim:.6f}")

    print(f"\n📊 Summary over {num_tests} tests:")
    print(f"  Max absolute difference: {max_diff:.6f}")
    print(f"  Max cosine distance: {max_cos_diff:.6f}")

    if max_cos_diff < 1e-4:
        print("✅ Excellent numerical parity!")
    elif max_cos_diff < 1e-3:
        print("✅ Good numerical parity")
    elif max_cos_diff < 1e-2:
        print("⚠️  Acceptable but noticeable difference")
    else:
        print("❌ Significant numerical difference - investigate!")


def main():
    parser = argparse.ArgumentParser(description="Convert OSNet to CoreML")
    parser.add_argument("--model", default="osnet_x0_5", help="OSNet variant (osnet_x0_5, osnet_x1_0, etc.)")
    parser.add_argument("--output", default="reid/models/osnet_x0_5.mlpackage", help="Output .mlpackage path")
    parser.add_argument("--input-shape", default="1,3,256,128", help="Input shape as comma-separated")
    parser.add_argument("--compute-unit", default="CPU_AND_NE",
                       choices=["CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "ALL"],
                       help="Compute unit for CoreML")
    parser.add_argument("--target", default="macos13",
                       choices=["macos12", "macos13", "macos14", "ios15", "ios16", "ios17"],
                       help="Minimum deployment target")
    parser.add_argument("--quantize", action="store_true", help="Quantize to FP16")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation")
    parser.add_argument("--compare", action="store_true", help="Compare PyTorch vs CoreML outputs")
    parser.add_argument("--num-tests", type=int, default=10, help="Number of comparison tests")

    args = parser.parse_args()

    # Check dependencies
    if not TORCHREID_AVAILABLE:
        print("❌ torchreid not installed")
        print("   Install: pip install torchreid")
        sys.exit(1)

    if not COREML_AVAILABLE:
        print("❌ coremltools not installed")
        print("   Install: pip install coremltools>=6.4")
        sys.exit(1)

    # Parse input shape
    input_shape = tuple(map(int, args.input_shape.split(",")))
    print(f"Input shape: {input_shape}")

    # Build model
    print(f"Building {args.model}...")
    model = build_osnet_model(args.model)

    # Convert to CoreML
    mlmodel = convert_to_coreml(
        model,
        args.output,
        input_shape=input_shape,
        compute_unit=args.compute_unit,
        minimum_deployment_target=args.target,
        quantize=args.quantize,
    )

    # Validate
    if not args.skip_validation:
        validate_model(mlmodel, input_shape)

    # Compare
    if args.compare:
        compare_pytorch_vs_coreml(model, mlmodel, input_shape, args.num_tests)

    print("\n✅ Conversion complete!")
    print(f"Model saved to: {args.output}")
    print(f"\nTo use in reid_config.json:")
    print(f'  "optimization": {{')
    print(f'    "coreml_reid_enabled": true,')
    print(f'    "coreml_model_path": "{args.output}",')
    print(f'    "coreml_compute_unit": "CPU_AND_NE",')
    print(f'    "coreml_skip_torch": true')
    print(f'  }}')


if __name__ == "__main__":
    main()